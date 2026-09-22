#!/usr/bin/env python3
"""One guided command for bank text extraction → staging → local ALM publishing."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import etl
import publish_to_alm as publisher


TOTAL_PHASES = 5


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_status(path: Path, status: dict[str, Any]) -> None:
    """Use replace so someone reading the file never sees half-written JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, prefix=".pipeline-status-") as temp:
        json.dump(status, temp, indent=2, ensure_ascii=False)
        temp.write("\n")
        temporary_path = Path(temp.name)
    temporary_path.replace(path)


def update(status: dict[str, Any], status_file: Path, phase: int, state: str, description: str, **details: Any) -> None:
    event = {"at": now(), "phase": phase, "state": state, "description": description, **details}
    status.update({"updated_at": event["at"], "phase": phase, "progress_percent": round(phase / TOTAL_PHASES * 100), "state": state, "description": description})
    status.setdefault("events", []).append(event)
    write_status(status_file, status)
    print(f"\n[{phase}/{TOTAL_PHASES}] {description}")


def etl_arguments(args: argparse.Namespace) -> Namespace:
    return Namespace(
        input_dir=args.input_dir,
        database=args.source_database,
        schema=args.schema,
        entity=args.source_entity,
        as_of_date=args.as_of_date,
        mode=args.mode,
        encoding=args.encoding,
        delimiter=args.delimiter,
        no_header=args.no_header,
        require_all=args.require_all,
        dry_run=False,
    )


def publisher_arguments(args: argparse.Namespace, dry_run: bool) -> Namespace:
    return Namespace(
        source_database=args.source_database,
        mapping=args.mapping,
        django_project=args.django_project,
        app_database=args.app_database,
        source_entity=args.source_entity,
        as_of_date=args.as_of_date,
        source_batch="latest",
        report=args.publish_report,
        dry_run=dry_run,
        allow_rejected=args.allow_rejected,
        require_full_coverage=args.require_full_coverage,
        create_entity=args.create_entity,
    )


def run(args: argparse.Namespace) -> int:
    status_file = Path(args.status_file).expanduser().resolve()
    status: dict[str, Any] = {
        "pipeline": "bank-text-to-alm",
        "started_at": now(),
        "state": "starting",
        "phase": 0,
        "progress_percent": 0,
        "input_directory": str(Path(args.input_dir).expanduser().resolve()),
        "source_database": str(Path(args.source_database).expanduser().resolve()),
        "target_app_database": str(Path(args.app_database).expanduser().resolve()),
        "source_entity": args.source_entity,
        "as_of_date": args.as_of_date,
        "events": [],
    }
    write_status(status_file, status)
    try:
        update(status, status_file, 1, "running", "Checking the approved mapping and local application targets")
        mapping = publisher.read_json(Path(args.mapping).expanduser().resolve())
        mapping_date = str(mapping.get("as_of_date", ""))
        if mapping_date != args.as_of_date:
            raise publisher.PublishError(
                f"The mapping as_of_date ({mapping_date or 'missing'}) must equal --as-of-date ({args.as_of_date})."
            )
        portfolio_rules = mapping.get("portfolio", {}).get("rules", [])
        if not portfolio_rules:
            raise publisher.PublishError("The mapping has no portfolio rules. Run inventory, approve mappings, then add at least one rule.")
        status["target_entity"] = mapping.get("entity_slug")
        update(status, status_file, 2, "running", "Loading bank text extracts into the separate SQLite source/staging database")
        etl.run_load(etl_arguments(args))

        update(status, status_file, 3, "running", "Creating a source inventory: row counts, products, account nature, currencies, and product codes")
        inventory_args = Namespace(
            source_database=args.source_database,
            source_entity=args.source_entity,
            as_of_date=args.as_of_date,
            source_batch="latest",
            output=args.inventory_file,
        )
        publisher.run_inventory(inventory_args)

        update(status, status_file, 4, "running", "Validating the controlled bank-to-ALM mappings, dates, currencies, and reconciliation coverage")
        preflight = publisher.run_publish(publisher_arguments(args, dry_run=True))
        if preflight != 0:
            status["preflight_exit_code"] = preflight
            update(status, status_file, 4, "blocked", "Publication was blocked. Review the publish report; the local ALM app was not changed.")
            return preflight

        if args.validate_only:
            update(status, status_file, 5, "completed_validation", "Validation completed successfully. Publication was intentionally skipped.")
            return 0

        update(status, status_file, 5, "running", "Publishing approved canonical portfolio records and optional LCR snapshot into the local Django ALM application")
        outcome = publisher.run_publish(publisher_arguments(args, dry_run=False))
        if outcome != 0:
            status["publish_exit_code"] = outcome
            update(status, status_file, 5, "failed", "Publishing did not complete. The publish report contains the reason.")
            return outcome
        update(status, status_file, 5, "completed", "Pipeline complete. The local ALM application now contains the approved mapped data.")
        return 0
    except Exception as error:
        update(status, status_file, min(status.get("phase", 1), TOTAL_PHASES), "failed", f"Pipeline stopped: {error}")
        return 2


def cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run text-file staging and controlled local Django ALM publication in one command")
    parser.add_argument("--input-dir", required=True, help="folder containing extensionless bank source files")
    parser.add_argument("--source-database", required=True, help="separate SQLite staging database")
    parser.add_argument("--mapping", required=True, help="approved JSON mapping file")
    parser.add_argument("--django-project", required=True, help="local ALM Django project directory")
    parser.add_argument("--app-database", required=True, help="local ALM Django SQLite database")
    parser.add_argument("--source-entity", default="jordan")
    parser.add_argument("--as-of-date", required=True, help="YYYY-MM-DD; must equal mapping.as_of_date")
    parser.add_argument("--schema", default=Path(__file__).with_name("schema_horizontal.json"))
    parser.add_argument("--mode", choices=("replace-date", "append"), default="replace-date")
    parser.add_argument("--encoding", default="auto")
    parser.add_argument("--delimiter", default="auto")
    parser.add_argument("--no-header", action="store_true")
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--allow-rejected", action="store_true", help="allow a partial but explicitly labelled canonical publication")
    parser.add_argument("--require-full-coverage", action="store_true", help="block publication unless every source row has a mapping rule")
    parser.add_argument("--create-entity", action="store_true", help="create the target entity from mapping.entity_slug when it does not exist")
    parser.add_argument("--validate-only", action="store_true", help="run source loading, inventory, and mapping validation, then stop before Django publication")
    parser.add_argument("--status-file", default="pipeline_status.json", help="live JSON status file")
    parser.add_argument("--inventory-file", default="mapping_inventory.json")
    parser.add_argument("--publish-report", default="alm_publish_report.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(cli().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
