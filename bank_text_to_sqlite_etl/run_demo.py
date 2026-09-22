#!/usr/bin/env python3
"""The intentionally simple Jordan demonstration runner.

Run from inside an ALM Django project after unzipping this directory there:
    python3 bank_text_to_sqlite_etl/run_demo.py /path/to/bank-text-files

The detailed etl.py, publish_to_alm.py, and run_pipeline.py remain available
for later Hive/PostgreSQL/Oracle integration. This wrapper is only a temporary
local demonstration convenience layer.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

import etl
import publish_to_alm as publisher
import run_pipeline


PACKAGE_DIR = Path(__file__).resolve().parent


class DemoError(Exception):
    pass


def find_django_project() -> Path:
    candidates = [Path.cwd(), *Path.cwd().parents, PACKAGE_DIR.parent, *PACKAGE_DIR.parent.parents]
    for candidate in candidates:
        if (candidate / "manage.py").is_file() and (candidate / "config" / "settings.py").is_file():
            return candidate
    raise DemoError(
        "Could not find the local ALM Django project. Unzip bank_text_to_sqlite_etl inside the "
        "alm-liquidity-demo folder, beside manage.py, then run this command again."
    )


def input_files(input_dir: Path, tables: dict[str, etl.SourceTable]) -> Iterable[tuple[etl.SourceTable, Path]]:
    matched, _ = etl.resolve_input_files(input_dir, tables)
    if not matched:
        raise DemoError("No recognised bank files were found. Each file must be named after its source table, without an extension.")
    return ((tables[name], path) for name, path in matched.items())


def detected_as_of_date(input_dir: Path, schema: Path) -> str:
    """Read every populated BALANCESHEETDATE and fail if the extracts are mixed-date."""
    tables = etl.load_schema(schema)
    dates: set[str] = set()
    for table, path in input_files(input_dir, tables):
        date_column = next((column.name for column in table.columns if etl.normalize(column.name) == "BALANCESHEETDATE"), None)
        if not date_column:
            continue
        encoding = etl.detect_encoding(path, "auto")
        delimiter = etl.detect_delimiter(path, encoding, "auto")
        with path.open("r", encoding=encoding, newline="") as source:
            reader = csv.reader(source, delimiter=delimiter)
            try:
                header = next(reader)
            except StopIteration:
                continue
            positions = {etl.normalize(value): index for index, value in enumerate(header)}
            position = positions.get(etl.normalize(date_column))
            if position is None:
                raise DemoError(f"{path.name} has no BALANCESHEETDATE header, so the demonstration date cannot be detected.")
            for row in reader:
                if not row or position >= len(row) or not row[position].strip():
                    continue
                try:
                    dates.add(publisher.parse_source_date(row[position], "BALANCESHEETDATE"))
                except Exception as error:
                    raise DemoError(f"{path.name}: {error}") from error
                if len(dates) > 1:
                    raise DemoError(f"The input folder contains more than one balance-sheet date: {', '.join(sorted(dates))}.")
    if not dates:
        raise DemoError("No BALANCESHEETDATE value was found in the supplied files.")
    return next(iter(dates))


def automatic_mapping(schema_path: Path) -> dict:
    """Generate transparent, table-name-based demo mappings without user JSON work.

    It deliberately maps only classes with a defensible source-table identity.
    Derivatives, FX, swaps, GL, ratings, parties, and treasury tables with an
    unknown asset/liability direction remain outside the published portfolio and
    are exposed as not-covered rows in the audit report.
    """
    schema = etl.load_schema(schema_path)
    available = set(schema)
    rules: list[dict] = []

    def add_open(table: str, product: str, group: str, prefix: str, principal: str = "BALANCE") -> None:
        if table not in available:
            return
        columns = {column.name for column in schema[table].columns}
        rules.append({
            "name": f"Auto-mapped for demonstration · {table}",
            "source_table": table,
            "id_prefix": prefix,
            "product": product,
            "principal_column": principal if principal in columns else "BALANCE",
            "currency_column": "CURRENCY",
            "liquidity_group": group,
            "liquidity_product_column": "PRODUCTTYPE",
        })

    def add_dated(table: str, product: str, group: str, prefix: str) -> None:
        if table not in available:
            return
        columns = {column.name for column in schema[table].columns}
        maturity = "MATURITYDATE" if "MATURITYDATE" in columns else None
        if not maturity:
            return
        # A temporary principal-at-maturity profile is explicit. It does not
        # manufacture coupon schedules from periodicity fields we have not yet
        # validated against the bank's contractual cash-flow extract.
        rules.append({
            "name": f"Auto-mapped for demonstration · {table} · principal at reported maturity; coupon schedule pending validation",
            "source_table": table,
            "id_prefix": prefix,
            "product": product,
            "principal_column": "PRINCIPAL" if "PRINCIPAL" in columns else "BALANCE",
            "currency_column": "CURRENCY",
            "liquidity_group": group,
            "liquidity_product_column": "PRODUCTTYPE",
            "annual_rate_default": "0",
            "annual_rate_scale": "decimal",
            "rate_type": "fixed",
            "repayment": "bullet",
            "day_count": "ACT/365F",
            "frequency_months": 12,
            "accrual_start_column": "ORIGINDATE" if "ORIGINDATE" in columns else "BALANCESHEETDATE",
            "next_payment_column": maturity,
            "maturity_column": maturity,
        })

    add_open("EquationJordanAccountContract", "demand_deposit", "Customer call accounts", "EQ-AC")
    add_open("UndrawnCommitmentJordanContract", "undrawn_commitment", "Undrawn commitments", "UDC", "PRINCIPAL")
    add_dated("EquationJordanLoanContract", "loan", "Loans", "EQ-LN")
    add_dated("EquationJordanOverdrawnOverdraftContract", "loan", "Overdrafts", "EQ-OD")
    add_dated("CommercialLendingJordanContract", "loan", "Commercial lending", "CL")
    add_dated("FinOneJordanContract", "loan", "FinOne lending", "FN")
    add_dated("EximbillsJordanContract", "loan", "Exim bills", "EX")
    add_dated("AFSJordanContract", "bond", "Available-for-sale securities", "AFS")

    return {
        "version": "demo-auto-1.0",
        "auto_mapping": True,
        "mapping_status": "Auto-mapped for temporary demonstration; product treatment and contractual coupon schedules require bank validation before Hive/production integration.",
        "source_entity": "jordan",
        "entity_slug": "jordan-bank-demo",
        "entity_name": "Jordan Bank Data Demo",
        "country": "Jordan",
        "base_currency": "JOD",
        "as_of_date": "AUTO",
        "source_batch": "latest",
        "portfolio": {"replace_existing": True, "sync_product_catalogue": True, "rules": rules},
        "regulatory": {"enabled": False, "replace_current_positions": True, "lcr_rules": [], "nsfr_lines": []},
    }


def create_mapping_if_missing(mapping_path: Path, schema_path: Path) -> bool:
    """Create demo rules automatically; never overwrite a later manual mapping."""
    if mapping_path.exists():
        existing = json.loads(mapping_path.read_text(encoding="utf-8"))
        if existing.get("portfolio", {}).get("rules"):
            return False
    mapping = automatic_mapping(schema_path)
    mapping_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def resolved_mapping(mapping_path: Path, as_of_date: str) -> Path:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    configured_date = str(mapping.get("as_of_date", "AUTO"))
    if configured_date not in {"AUTO", as_of_date}:
        # The mapping describes product rules rather than a historical data set.
        # For this temporary daily demonstration, resolve the current date without
        # overwriting the approved rule file.
        print(f"Mapping date {configured_date} was replaced with detected source date {as_of_date} for this run.")
    mapping["as_of_date"] = as_of_date
    mapping["source_entity"] = "jordan"
    mapping.setdefault("entity_slug", "jordan-bank-demo")
    mapping.setdefault("entity_name", "Jordan Bank Data Demo")
    target = PACKAGE_DIR / ".resolved_jordan_mapping.json"
    target.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def has_portfolio_rules(mapping_path: Path) -> bool:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    return bool(mapping.get("portfolio", {}).get("rules", []))


def simple_setup(input_dir: Path, schema: Path, source_database: Path, as_of_date: str, inventory_file: Path, status_file: Path) -> int:
    """Stage and inventory the data, then stop until product mapping is reviewed."""
    status = {"pipeline": "bank-text-to-alm-demo", "state": "starting", "as_of_date": as_of_date, "events": []}
    run_pipeline.write_status(status_file, status)
    try:
        run_pipeline.update(status, status_file, 1, "running", "Detected one Jordan balance-sheet date from the bank files", as_of_date=as_of_date)
        run_pipeline.update(status, status_file, 2, "running", "Loading the bank text files into the separate local source SQLite database")
        etl.run_load(run_pipeline.etl_arguments(argparse.Namespace(
            input_dir=str(input_dir), source_database=str(source_database), schema=str(schema), source_entity="jordan",
            as_of_date=as_of_date, mode="replace-date", encoding="auto", delimiter="auto", no_header=False, require_all=False,
        )))
        run_pipeline.update(status, status_file, 3, "running", "Creating a product, account-nature, currency, and product-code inventory")
        publisher.run_inventory(argparse.Namespace(
            source_database=str(source_database), source_entity="jordan", as_of_date=as_of_date,
            source_batch="latest", output=str(inventory_file),
        ))
        run_pipeline.update(status, status_file, 4, "awaiting_mapping", "Setup is ready. Fill jordan_mapping.json using mapping_inventory.json, then run the same command again.")
        return 0
    except Exception as error:
        run_pipeline.update(status, status_file, status.get("phase", 1), "failed", f"Setup stopped: {error}")
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-command temporary Jordan bank-data demo")
    parser.add_argument("input_dir", help="folder containing the extensionless Jordan bank text files")
    parser.add_argument("--as-of-date", help="only use rows whose BALANCESHEETDATE equals this YYYY-MM-DD date")
    args = parser.parse_args(argv)
    try:
        input_dir = Path(args.input_dir).expanduser().resolve()
        if not input_dir.is_dir():
            raise DemoError(f"Input folder does not exist: {input_dir}")
        project = find_django_project()
        schema = PACKAGE_DIR / "schema_horizontal.json"
        if args.as_of_date:
            try:
                as_of_date = date.fromisoformat(args.as_of_date).isoformat()
            except ValueError:
                raise DemoError("--as-of-date must use YYYY-MM-DD, for example 2026-09-15") from None
            print(f"Using only source rows with BALANCESHEETDATE = {as_of_date}.")
        else:
            as_of_date = detected_as_of_date(input_dir, schema)
        source_database = PACKAGE_DIR / "jordan_bank_source.sqlite3"
        mapping_path = PACKAGE_DIR / "jordan_mapping.json"
        status_file = PACKAGE_DIR / "pipeline_status.json"
        inventory_file = PACKAGE_DIR / "mapping_inventory.json"
        publish_report = PACKAGE_DIR / "alm_publish_report.json"
        created = create_mapping_if_missing(mapping_path, schema)
        if created:
            print("Created jordan_mapping.json with automatic temporary demonstration mappings.")
        mapping_for_run = resolved_mapping(mapping_path, as_of_date)
        return run_pipeline.main([
            "--input-dir", str(input_dir),
            "--source-database", str(source_database),
            "--mapping", str(mapping_for_run),
            "--django-project", str(project),
            "--app-database", str(project / "data" / "db.sqlite3"),
            "--source-entity", "jordan",
            "--as-of-date", as_of_date,
            "--create-entity",
            "--allow-rejected",
            "--status-file", str(status_file),
            "--inventory-file", str(inventory_file),
            "--publish-report", str(publish_report),
        ])
    except DemoError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
