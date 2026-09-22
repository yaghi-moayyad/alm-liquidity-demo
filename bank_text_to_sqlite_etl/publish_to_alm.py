#!/usr/bin/env python3
"""Controlled publisher from bank source/staging SQLite into the local ALM app.

The source loader and this publisher are deliberately separate.  This program
does not read the bank's Hive tables or text files: it reads a *completed* ETL
batch in the staging SQLite database and publishes only records covered by an
explicit mapping file into the local Django application's canonical models.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


OPEN_PRODUCTS = {
    "demand_deposit", "cash_central_bank", "undrawn_commitment",
    "undrawn_uncommitted", "trade_finance",
}
DATED_PRODUCTS = {"loan", "bond", "interbank_asset", "term_deposit", "borrowing"}
SUPPORTED_PRODUCTS = OPEN_PRODUCTS | DATED_PRODUCTS
SUPPORTED_CURRENCIES = {"JOD", "USD", "EUR", "GBP"}
LCR_CATEGORIES = {
    "level1_coins", "level1_reserves", "level1_sovereign", "level2a_securities",
    "level2b_equities", "retail_stable", "retail_less_stable",
    "wholesale_operational", "wholesale_non_operational", "secured_funding",
    "other_outflows", "inflow_financial", "inflow_customer",
}
LCR_DIRECTIONS = {"hqla", "outflow", "inflow"}


class PublishError(Exception):
    pass


@dataclass
class Rejection:
    source_table: str
    source_row: int
    source_reference: str
    reason: str
    rule: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_table": self.source_table,
            "source_row": self.source_row,
            "source_reference": self.source_reference,
            "reason": self.reason,
            "rule": self.rule,
        }


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublishError(f"Cannot read mapping file {path}: {error}") from error
    if not isinstance(data, dict):
        raise PublishError("The mapping file must contain one JSON object.")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def source_connection(database: Path) -> sqlite3.Connection:
    if not database.exists():
        raise PublishError(f"Source/staging SQLite database was not found: {database}")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    return connection


def source_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def resolve_batch(connection: sqlite3.Connection, entity: str, as_of_date: str, requested: str = "latest") -> sqlite3.Row:
    if "etl_batches" not in source_tables(connection):
        raise PublishError("This is not an ETL staging database: etl_batches is missing.")
    if requested != "latest":
        row = connection.execute(
            """SELECT * FROM etl_batches WHERE batch_id = ? AND entity_code = ? AND as_of_date = ?
               AND status = 'completed'""",
            (requested, entity, as_of_date),
        ).fetchone()
    else:
        row = connection.execute(
            """SELECT * FROM etl_batches WHERE entity_code = ? AND as_of_date = ?
               AND status = 'completed' ORDER BY finished_at DESC LIMIT 1""",
            (entity, as_of_date),
        ).fetchone()
    if not row:
        raise PublishError(
            f"No completed source load exists for entity={entity!r}, as_of_date={as_of_date!r}. "
            "Run etl.py load first, or select a valid --source-batch."
        )
    return row


def parse_as_of(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise PublishError("as_of_date must use YYYY-MM-DD") from None


def parse_source_date(value: Any, field: str) -> str:
    value = str(value or "").strip()
    for pattern in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise PublishError(f"{field} must be a valid bank date (YYYYMMDD or YYYY-MM-DD), got {value!r}")


def optional_source_date(value: Any) -> str | None:
    """Normalise a date candidate without rejecting the full source row."""
    try:
        return parse_source_date(value, "source date")
    except PublishError:
        return None


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise PublishError(f"{field} must be numeric, got {value!r}") from None
    if not parsed.is_finite():
        raise PublishError(f"{field} must be finite")
    return parsed


def positive_amount(value: Any, field: str) -> str:
    amount = abs(decimal_value(value, field))
    if amount <= 0:
        raise PublishError(f"{field} must be non-zero")
    return format(amount, "f")


def source_reference(row: sqlite3.Row, rule: dict[str, Any] | None = None) -> str:
    """Return a stable source identifier for one published contract.

    A contract reference alone is not unique in EquationJordanAccountContract:
    the same facility/reference can contain more than one account and currency.
    Use the natural compound key there automatically.  ``id_columns`` remains
    available for future table-specific mappings without changing this code.
    """
    id_columns = (rule or {}).get("id_columns") or []
    if not id_columns and (rule or {}).get("source_table") == "EquationJordanAccountContract":
        id_columns = ["CONTRACTREFERENCE", "ACCOUNTREFERENCE", "AB_CODE", "AB_SOURCESYSTEM", "CURRENCY"]

    if id_columns:
        values: list[str] = []
        for column in id_columns:
            if column not in row.keys():
                raise PublishError(f"Identifier column {column!r} is not in the source table")
            value = str(row[column] or "").strip()
            if not value:
                raise PublishError(f"Identifier column {column!r} is empty")
            values.append(value)
        return "-".join(values)

    for column in ("CONTRACTREFERENCE", "ContractReference", "ACCOUNTREFERENCE"):
        if column in row.keys() and str(row[column] or "").strip():
            return str(row[column]).strip()
    return f"row-{row['_etl_source_row']}"


def unique_contract_id(prefix: str, reference: str) -> str:
    clean_prefix = re.sub(r"[^A-Za-z0-9_.-]", "-", prefix).strip("-_") or "SRC"
    clean_reference = re.sub(r"[^A-Za-z0-9_.-]", "-", reference).strip("-_")
    candidate = f"{clean_prefix}-{clean_reference}"
    if clean_reference and len(candidate) <= 64 and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", candidate):
        return candidate
    digest = hashlib.sha1(f"{prefix}|{reference}".encode("utf-8")).hexdigest()[:16]
    return f"{clean_prefix[:42]}-{digest}"


def row_matches(row: sqlite3.Row, where: dict[str, Any]) -> bool:
    for column, expected in where.items():
        if column not in row.keys():
            return False
        choices = expected if isinstance(expected, list) else [expected]
        actual = str(row[column] or "").strip().upper()
        if actual not in {str(choice).strip().upper() for choice in choices}:
            return False
    return True


def required_column(row: sqlite3.Row, column: str, rule_name: str) -> Any:
    if not column:
        raise PublishError(f"Rule {rule_name!r} is missing a required column setting")
    if column not in row.keys():
        raise PublishError(f"Rule {rule_name!r} expects source column {column!r}, but it is not in this table")
    return row[column]


def value_or_default(row: sqlite3.Row, column: str | None, default: Any, rule_name: str) -> Any:
    if column:
        value = required_column(row, column, rule_name)
        if value is not None and str(value).strip() != "":
            return value
    return default


def normalise_rate_type(value: Any) -> str:
    key = str(value or "").strip().lower()
    if any(token in key for token in ("float", "variable", "var")):
        return "floating"
    return "fixed"


def map_contract(row: sqlite3.Row, rule: dict[str, Any], as_of: date) -> dict[str, Any]:
    name = rule.get("name", rule.get("source_table", "unnamed rule"))
    product = rule.get("product")
    if product not in SUPPORTED_PRODUCTS:
        raise PublishError(f"Rule {name!r}: product must be one of {', '.join(sorted(SUPPORTED_PRODUCTS))}")
    reference = source_reference(row, rule)
    prefix = rule.get("id_prefix")
    if not prefix:
        raise PublishError(f"Rule {name!r}: id_prefix is required to avoid source-system ID collisions")
    currency = str(value_or_default(row, rule.get("currency_column", "CURRENCY"), rule.get("currency_default"), name) or "").strip().upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise PublishError(f"Unsupported currency {currency!r}; app currently supports {', '.join(sorted(SUPPORTED_CURRENCIES))}")
    principal = positive_amount(required_column(row, rule.get("principal_column", "BALANCE"), name), "principal")
    liquidity_product = str(value_or_default(row, rule.get("liquidity_product_column"), rule.get("liquidity_product", product), name)).strip()
    liquidity_group = str(rule.get("liquidity_group", product.replace("_", " ").title())).strip()
    contract: dict[str, Any] = {
        "contract_id": unique_contract_id(prefix, reference),
        "product": product,
        "currency": currency,
        "principal": principal,
        "liquidity_product": liquidity_product,
        "liquidity_group": liquidity_group,
        # Retained in the canonical input/run snapshot for audit and
        # reconciliation. These technical fields never drive cash-flow logic.
        "source_table": rule.get("source_table", ""),
        "source_file": str(row["_etl_source_file"] or "") if "_etl_source_file" in row.keys() else "",
        "source_row": int(row["_etl_source_row"]) if "_etl_source_row" in row.keys() else None,
        "source_batch_id": str(row["_etl_batch_id"] or "") if "_etl_batch_id" in row.keys() else "",
        "source_reference": reference,
    }
    if product in OPEN_PRODUCTS:
        return contract

    for config_key in ("accrual_start_column", "next_payment_column", "maturity_column"):
        if not rule.get(config_key):
            raise PublishError(
                f"Rule {name!r}: dated product {product!r} requires {config_key}. "
                "Do not invent a payment date."
            )
    annual_rate = decimal_value(
        value_or_default(row, rule.get("annual_rate_column"), rule.get("annual_rate_default"), name),
        "annual_rate",
    )
    scale = rule.get("annual_rate_scale", "decimal")
    if scale == "percent":
        annual_rate /= Decimal("100")
    elif scale != "decimal":
        raise PublishError(f"Rule {name!r}: annual_rate_scale must be decimal or percent")
    if not Decimal("0") <= annual_rate <= Decimal("1"):
        raise PublishError(f"Rule {name!r}: annual_rate must be between 0 and 1 after scaling")
    rate_type = normalise_rate_type(value_or_default(row, rule.get("rate_type_column"), rule.get("rate_type", "fixed"), name))
    frequency = rule.get("frequency_months")
    if frequency not in (1, 3, 6, 12):
        raise PublishError(f"Rule {name!r}: frequency_months must be one of 1, 3, 6, 12")
    # Preserve useful source-date candidates beside the calculation terms. They
    # let the ALM application offer a governed, calculation-time choice for an
    # exception group after import. Raw bank rows remain unchanged.
    configured_candidates=rule.get("candidate_date_columns") or []
    common_candidates={"NEXTINTERESTPAYMENTDATE","INTERESTBREAKINGDATE","PRINCIPALBREAKINGDATE","MATURITYDATE","ORIGINDATE","BALANCESHEETDATE"}
    candidate_columns=[]
    for column in [*configured_candidates,*[key for key in row.keys() if str(key).upper() in common_candidates]]:
        if column in row.keys() and column not in candidate_columns:
            candidate_columns.append(column)
    candidates={column:normalised for column in candidate_columns if (normalised:=optional_source_date(row[column]))}

    dates={}
    date_errors=[]
    for target,config_key in (("accrual_start","accrual_start_column"),("next_payment","next_payment_column"),("maturity","maturity_column")):
        raw=required_column(row, rule[config_key], name)
        parsed=optional_source_date(raw)
        if parsed:
            dates[target]=parsed
        else:
            date_errors.append(f"{target} is missing or invalid")

    contract.update({
        "annual_rate": format(annual_rate, "f"),
        "rate_type": rate_type,
        "repayment": rule.get("repayment", "bullet"),
        "day_count": rule.get("day_count", "ACT/365F"),
        "frequency_months": frequency,
        "end_of_month": bool(rule.get("end_of_month", False)),
        "source_date_candidates": candidates,
    })
    contract.update(dates)
    if len(dates)==3:
        start = date.fromisoformat(dates["accrual_start"])
        next_payment = date.fromisoformat(dates["next_payment"])
        maturity = date.fromisoformat(dates["maturity"])
        if not start <= as_of < next_payment <= maturity:
            date_errors.append("dates must meet accrual_start ≤ as_of_date < next_payment ≤ maturity")
        elif (next_payment-start).days>370:
            date_errors.append("first accrual period exceeds 370 days")
    if date_errors:
        contract["data_quality"]={
            "status":"needs_resolution",
            "issues":date_errors,
            "source_date_candidates":candidates,
            "mapping_rule":name,
        }
    return contract


def map_lcr_position(row: sqlite3.Row, rule: dict[str, Any]) -> dict[str, Any]:
    name = rule.get("name", rule.get("source_table", "unnamed LCR rule"))
    category = rule.get("lcr_category")
    direction = rule.get("lcr_direction")
    if category not in LCR_CATEGORIES:
        raise PublishError(f"Rule {name!r}: lcr_category must be an approved app LCR category")
    if direction not in LCR_DIRECTIONS:
        raise PublishError(f"Rule {name!r}: lcr_direction must be hqla, outflow, or inflow")
    factor = decimal_value(rule.get("lcr_factor"), "lcr_factor")
    if not Decimal("0") <= factor <= Decimal("1"):
        raise PublishError("lcr_factor must be between 0 and 1")
    reference = source_reference(row)
    product_type = str(value_or_default(row, rule.get("product_type_column"), rule.get("product_type", "Unclassified"), name))
    return {
        "external_id": unique_contract_id(rule.get("id_prefix", "LCR"), reference),
        "gl_code": str(value_or_default(row, rule.get("gl_code_column"), rule.get("gl_code", "PENDING"), name)),
        "product_group": str(rule.get("product_group", "Unclassified")),
        "product_type": product_type,
        "currency": str(value_or_default(row, rule.get("currency_column", "CURRENCY"), rule.get("currency_default"), name)).upper(),
        "balance": positive_amount(required_column(row, rule.get("balance_column", "BALANCE"), name), "balance"),
        "lcr_category": category,
        "lcr_factor": str(factor),
        "lcr_direction": direction,
        "hqla_level": str(rule.get("hqla_level", "")),
        "label": str(rule.get("label", product_type)),
        "source_table": rule["source_table"],
        "source_reference": reference,
    }


def rows_for_rule(connection: sqlite3.Connection, known_tables: set[str], batch_id: str, rule: dict[str, Any]) -> Iterable[sqlite3.Row]:
    table = rule.get("source_table")
    if table not in known_tables:
        raise PublishError(f"Mapping rule points to unavailable source table: {table!r}")
    return connection.execute(f"SELECT * FROM {quote(table)} WHERE _etl_batch_id = ?", (batch_id,))


def map_rules(
    connection: sqlite3.Connection,
    known_tables: set[str],
    batch_id: str,
    rules: list[dict[str, Any]],
    mapper,
    as_of: date | None = None,
) -> tuple[list[dict[str, Any]], list[Rejection], dict[str, int]]:
    mapped: list[dict[str, Any]] = []
    rejected: list[Rejection] = []
    coverage: dict[str, int] = defaultdict(int)
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("source_table"):
            raise PublishError("Every mapping rule must be an object with source_table")
        rule_name = rule.get("name", rule["source_table"])
        for row in rows_for_rule(connection, known_tables, batch_id, rule):
            if not row_matches(row, rule.get("where", {})):
                continue
            coverage[rule["source_table"]] += 1
            try:
                mapped.append(mapper(row, rule, as_of) if as_of else mapper(row, rule))
            except PublishError as error:
                rejected.append(Rejection(rule["source_table"], row["_etl_source_row"], source_reference(row), str(error), rule_name))
    return mapped, rejected, dict(coverage)


def all_source_counts(connection: sqlite3.Connection, batch_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in source_tables(connection):
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({quote(table)})")}
        if "_etl_batch_id" not in columns:
            continue
        counts[table] = connection.execute(f"SELECT COUNT(*) FROM {quote(table)} WHERE _etl_batch_id = ?", (batch_id,)).fetchone()[0]
    return counts


def inventory(connection: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {"batch_id": batch_id, "tables": {}}
    interesting = ("PRODUCTTYPE", "ACCOUNTTYPE", "ACCOUNTNATURE", "CURRENCY", "AB_CODE", "AB_PRODUCTID", "AB_SOURCESYSTEM")
    for table, count in all_source_counts(connection, batch_id).items():
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({quote(table)})")}
        table_info: dict[str, Any] = {"rows": count, "values": {}}
        for column in interesting:
            if column not in columns:
                continue
            values = connection.execute(
                f"""SELECT {quote(column)} AS value, COUNT(*) AS rows FROM {quote(table)}
                WHERE _etl_batch_id = ? GROUP BY {quote(column)} ORDER BY rows DESC LIMIT 250""",
                (batch_id,),
            ).fetchall()
            table_info["values"][column] = [{"value": row["value"], "rows": row["rows"]} for row in values]
        result["tables"][table] = table_info
    return result


def load_django(project: Path, app_database: Path) -> None:
    if not (project / "manage.py").is_file() or not (project / "config" / "settings.py").is_file():
        raise PublishError("--django-project must point to the local ALM Django project (manage.py and config/settings.py)")
    if not app_database.exists():
        raise PublishError("--app-database does not exist. Run `python manage.py migrate` in the local ALM project first.")
    sys.path.insert(0, str(project))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["DATABASE_ENGINE"] = "sqlite"
    os.environ["SQLITE_PATH"] = str(app_database)
    try:
        import django
        django.setup()
    except ModuleNotFoundError as error:
        raise PublishError("Django is not installed in this Python environment. Activate the ALM project virtual environment first.") from error


def publish_to_django(
    project: Path,
    app_database: Path,
    mapping: dict[str, Any],
    as_of: date,
    contracts: list[dict[str, Any]],
    lcr_positions: list[dict[str, Any]],
    create_entity: bool,
) -> dict[str, Any]:
    load_django(project, app_database)
    from django.db import transaction
    from cashflows.engine import DEFAULT_BUCKETS
    from cashflows.models import Entity, EntityConfiguration, PortfolioContract, ProductCatalogueItem, RegulatorySnapshot, RegulatorySourcePosition

    entity_slug = mapping.get("entity_slug")
    if not entity_slug:
        raise PublishError("mapping.entity_slug is required")
    entity = Entity.objects.filter(slug=entity_slug).first()
    if not entity:
        if not create_entity:
            raise PublishError(f"Django entity {entity_slug!r} does not exist. Re-run with --create-entity to create it.")
        entity = Entity.objects.create(
            slug=entity_slug,
            name=mapping.get("entity_name", entity_slug.replace("-", " ").title()),
            country=mapping.get("country", "Jordan"),
            base_currency=mapping.get("base_currency", "JOD"),
            is_mock=False,
        )
        EntityConfiguration.objects.create(entity=entity, as_of_date=as_of, bucket_days=list(DEFAULT_BUCKETS))

    duplicate_ids = [item for item, total in Counter(contract["contract_id"] for contract in contracts).items() if total > 1]
    if duplicate_ids:
        raise PublishError(f"Mapped contracts are not unique; review id_prefix values. Example duplicate: {duplicate_ids[0]}")
    duplicate_regulatory_ids = [item for item, total in Counter(position["external_id"] for position in lcr_positions).items() if total > 1]
    if duplicate_regulatory_ids:
        raise PublishError(f"Mapped LCR positions are not unique; review id_prefix values. Example duplicate: {duplicate_regulatory_ids[0]}")

    portfolio_config = mapping.get("portfolio", {})
    regulatory_config = mapping.get("regulatory", {})
    with transaction.atomic():
        configuration = EntityConfiguration.objects.select_for_update().get(entity=entity)
        if portfolio_config.get("replace_existing", True):
            entity.portfolio_contracts.all().delete()
        PortfolioContract.objects.bulk_create(
            [PortfolioContract(entity=entity, external_id=item["contract_id"], terms=item) for item in contracts],
            batch_size=1_000,
        )
        configuration.as_of_date = as_of
        configuration.revision += 1
        configuration.save(update_fields=["as_of_date", "revision", "updated"])

        if portfolio_config.get("sync_product_catalogue", True):
            catalogued = {(item["liquidity_group"], item["liquidity_product"], item["product"]) for item in contracts}
            for group, product_type, product in catalogued:
                classification = "Asset" if product in {"loan", "bond", "interbank_asset", "cash_central_bank"} else "OffBalanceSheet" if product.startswith("undrawn") or product == "trade_finance" else "Liability"
                ProductCatalogueItem.objects.update_or_create(
                    entity=entity, classification=classification, product_group=group, product_type=product_type,
                    defaults={"general_ledger": "PENDING-CONFIRMATION", "is_temporary_gl": True, "source": "Bank staging SQLite publisher", "active": True},
                )

        if regulatory_config.get("enabled", False):
            if regulatory_config.get("replace_current_positions", True):
                RegulatorySourcePosition.objects.filter(entity=entity).delete()
            RegulatorySourcePosition.objects.bulk_create([
                RegulatorySourcePosition(
                    entity=entity, external_id=item["external_id"], gl_code=item["gl_code"], product_group=item["product_group"],
                    product_type=item["product_type"], currency=item["currency"], balance=item["balance"],
                    lcr_category=item["lcr_category"], lcr_factor=item["lcr_factor"], lcr_direction=item["lcr_direction"], hqla_level=item["hqla_level"], active=True,
                ) for item in lcr_positions
            ], batch_size=1_000)
            source_positions = [{key: value for key, value in item.items() if key not in {"source_table", "source_reference"}} for item in lcr_positions]
            RegulatorySnapshot.objects.update_or_create(
                entity=entity, as_of_date=as_of,
                defaults={
                    "source": "Approved mapped source data from bank staging SQLite",
                    "is_mock": False,
                    "source_data": {"lcr_positions": source_positions, "nsfr_lines": regulatory_config.get("nsfr_lines", [])},
                },
            )
    return {"entity_slug": entity.slug, "entity_name": entity.name, "portfolio_contracts": len(contracts), "lcr_positions": len(lcr_positions)}


def run_inventory(args: argparse.Namespace) -> int:
    as_of = parse_as_of(args.as_of_date)
    with source_connection(Path(args.source_database).expanduser().resolve()) as connection:
        batch = resolve_batch(connection, args.source_entity, as_of.isoformat(), args.source_batch)
        result = inventory(connection, batch["batch_id"])
        result.update({"entity": batch["entity_code"], "as_of_date": batch["as_of_date"], "source_batch": dict(batch)})
    output = Path(args.output).expanduser().resolve()
    write_json(output, result)
    print(f"Inventory written to {output}")
    return 0


def run_publish(args: argparse.Namespace) -> int:
    mapping = read_json(Path(args.mapping).expanduser().resolve())
    as_of = parse_as_of(str(mapping.get("as_of_date", args.as_of_date or "")))
    source_entity = args.source_entity or mapping.get("source_entity", "jordan")
    requested_batch = args.source_batch or mapping.get("source_batch", "latest")
    with source_connection(Path(args.source_database).expanduser().resolve()) as connection:
        batch = resolve_batch(connection, source_entity, as_of.isoformat(), requested_batch)
        known_tables = source_tables(connection)
        portfolio = mapping.get("portfolio", {})
        regulatory = mapping.get("regulatory", {})
        contracts, contract_rejections, contract_coverage = map_rules(
            connection, known_tables, batch["batch_id"], portfolio.get("rules", []), map_contract, as_of
        )
        lcr_positions, lcr_rejections, lcr_coverage = map_rules(
            connection, known_tables, batch["batch_id"], regulatory.get("lcr_rules", []), map_lcr_position
        )
        counts = all_source_counts(connection, batch["batch_id"])

    rejected = [item.as_dict() for item in [*contract_rejections, *lcr_rejections]]
    mapped_by_table: dict[str, int] = defaultdict(int)
    for values in (contract_coverage, lcr_coverage):
        for table, total in values.items():
            mapped_by_table[table] += total
    coverage = {
        table: {"source_rows": total, "covered_by_rule_rows": mapped_by_table.get(table, 0), "not_covered_by_rule_rows": max(total - mapped_by_table.get(table, 0), 0)}
        for table, total in counts.items()
    }
    report: dict[str, Any] = {
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_batch_id": batch["batch_id"],
        "source_entity": source_entity,
        "as_of_date": as_of.isoformat(),
        "target_entity": mapping.get("entity_slug"),
        "mapped_portfolio_contracts": len(contracts),
        "mapped_lcr_positions": len(lcr_positions),
        "rejected_rows": rejected,
        "coverage": coverage,
        "status": "dry_run" if args.dry_run else "pending_publish",
    }
    if rejected and not args.allow_rejected:
        report["status"] = "blocked_rejected_rows"
        report_path = Path(args.report).expanduser().resolve()
        write_json(report_path, report)
        print(f"Publication blocked: {len(rejected)} mapped rows need review. Report: {report_path}", file=sys.stderr)
        return 2
    if args.require_full_coverage:
        uncovered = {table: item["not_covered_by_rule_rows"] for table, item in coverage.items() if item["not_covered_by_rule_rows"]}
        if uncovered:
            report["status"] = "blocked_incomplete_coverage"
            report["uncovered"] = uncovered
            report_path = Path(args.report).expanduser().resolve()
            write_json(report_path, report)
            print(f"Publication blocked: source rows are not covered by an approved mapping. Report: {report_path}", file=sys.stderr)
            return 2
    if args.dry_run:
        report_path = Path(args.report).expanduser().resolve()
        write_json(report_path, report)
        print(f"Dry-run mapping succeeded. Report: {report_path}")
        print(f"Would publish {len(contracts):,} portfolio contracts and {len(lcr_positions):,} LCR positions.")
        return 0

    django_result = publish_to_django(
        Path(args.django_project).expanduser().resolve(),
        Path(args.app_database).expanduser().resolve(),
        mapping, as_of, contracts, lcr_positions, args.create_entity,
    )
    report["status"] = "published_with_explicit_exclusions" if rejected else "published"
    report["django_result"] = django_result
    report_path = Path(args.report).expanduser().resolve()
    write_json(report_path, report)
    print(f"Published {len(contracts):,} portfolio contracts and {len(lcr_positions):,} LCR positions into {django_result['entity_slug']}.")
    print(f"Audit report: {report_path}")
    return 0


def cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled bank staging SQLite → local Django ALM publisher")
    commands = parser.add_subparsers(dest="command", required=True)
    inventory_parser = commands.add_parser("inventory", help="write mapping-relevant source values and counts")
    inventory_parser.add_argument("--source-database", required=True)
    inventory_parser.add_argument("--source-entity", default="jordan")
    inventory_parser.add_argument("--as-of-date", required=True)
    inventory_parser.add_argument("--source-batch", default="latest")
    inventory_parser.add_argument("--output", default="mapping_inventory.json")
    inventory_parser.set_defaults(func=run_inventory)

    publish = commands.add_parser("publish", help="map an approved source batch into the local ALM Django database")
    publish.add_argument("--source-database", required=True)
    publish.add_argument("--mapping", required=True)
    publish.add_argument("--django-project", required=True)
    publish.add_argument("--app-database", required=True)
    publish.add_argument("--source-entity", help="overrides mapping.source_entity")
    publish.add_argument("--as-of-date", help="used only when absent from mapping")
    publish.add_argument("--source-batch", help="overrides mapping.source_batch; default latest")
    publish.add_argument("--report", default="alm_publish_report.json")
    publish.add_argument("--dry-run", action="store_true", help="map and validate without touching Django")
    publish.add_argument("--allow-rejected", action="store_true", help="publish mapped rows while explicitly recording rejected rows")
    publish.add_argument("--require-full-coverage", action="store_true", help="block unless every loaded source row has an approved rule")
    publish.add_argument("--create-entity", action="store_true", help="create mapping.entity_slug in Django if it does not exist")
    publish.set_defaults(func=run_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = cli().parse_args(argv)
    try:
        return args.func(args)
    except PublishError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
