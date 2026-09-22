#!/usr/bin/env python3
"""Load bank text extracts into an auditable SQLite source/staging database.

This utility is intentionally independent from Django.  It preserves the bank
table structures described in schema_horizontal.json and adds only technical
lineage columns prefixed with _etl_.  A later, controlled publishing step can
map these source tables into the ALM application's canonical Django models.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import sqlite3
import sys
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


TECHNICAL_COLUMNS = (
    ("_etl_batch_id", "TEXT NOT NULL"),
    ("_etl_source_file", "TEXT NOT NULL"),
    ("_etl_source_row", "INTEGER NOT NULL"),
    ("_etl_loaded_at", "TEXT NOT NULL"),
)
DELIMITER_CANDIDATES = ("|", "\t", ";", ",")
ENCODING_CANDIDATES = ("utf-8-sig", "utf-16", "cp1256", "latin-1")


class LoadValidationError(Exception):
    """A problem in the source file that should be reported to the operator."""


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    nullable: bool


@dataclass(frozen=True)
class SourceTable:
    name: str
    source_file: str
    columns: tuple[Column, ...]


def quote(identifier: str) -> str:
    """Quote a SQLite identifier. Identifiers always come from the schema file."""
    return '"' + identifier.replace('"', '""') + '"'


def normalize(name: str) -> str:
    return "".join(ch for ch in name.strip().upper() if ch.isalnum())


def sqlite_type(source_type: str) -> str:
    # DECIMAL is stored as text deliberately: SQLite REAL would lose bank-value
    # precision. The canonical ALM publish step will parse it with Decimal.
    return {"string": "TEXT", "integer": "INTEGER", "decimal": "TEXT", "boolean": "INTEGER"}[source_type]


def load_schema(path: Path) -> dict[str, SourceTable]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tables: dict[str, SourceTable] = {}
    for raw_table in payload["tables"]:
        columns = tuple(
            Column(column["name"], column["type"], bool(column["nullable"]))
            for column in raw_table["columns"]
        )
        table = SourceTable(raw_table["table_name"], raw_table.get("source_file", ""), columns)
        tables[table.name] = table
    return tables


def schema_hash(schema_file: Path) -> str:
    return hashlib.sha256(schema_file.read_bytes()).hexdigest()


def connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def create_metadata_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS etl_batches (
            batch_id TEXT PRIMARY KEY,
            entity_code TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            mode TEXT NOT NULL,
            schema_hash TEXT NOT NULL,
            input_directory TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            loaded_rows INTEGER NOT NULL DEFAULT 0,
            rejected_rows INTEGER NOT NULL DEFAULT 0,
            message TEXT
        );

        CREATE TABLE IF NOT EXISTS etl_file_loads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL REFERENCES etl_batches(batch_id) ON DELETE CASCADE,
            table_name TEXT NOT NULL,
            source_file TEXT NOT NULL,
            encoding TEXT NOT NULL,
            delimiter TEXT NOT NULL,
            header_json TEXT NOT NULL,
            accepted_rows INTEGER NOT NULL DEFAULT 0,
            rejected_rows INTEGER NOT NULL DEFAULT 0,
            loaded_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS etl_rejections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL REFERENCES etl_batches(batch_id) ON DELETE CASCADE,
            table_name TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            reason TEXT NOT NULL,
            raw_values_json TEXT NOT NULL,
            rejected_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS etl_batches_entity_date_idx
            ON etl_batches(entity_code, as_of_date);
        CREATE INDEX IF NOT EXISTS etl_rejections_batch_idx
            ON etl_rejections(batch_id, table_name);

        CREATE TABLE IF NOT EXISTS etl_exact_duplicates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL REFERENCES etl_batches(batch_id) ON DELETE CASCADE,
            table_name TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            retained_source_row INTEGER NOT NULL,
            record_hash TEXT NOT NULL,
            reason TEXT NOT NULL,
            detected_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS etl_exact_duplicates_batch_idx
            ON etl_exact_duplicates(batch_id, table_name);
        """
    )


def create_source_tables(connection: sqlite3.Connection, tables: Iterable[SourceTable]) -> None:
    for table in tables:
        definitions = [f"{quote(column.name)} {sqlite_type(column.data_type)}" + ("" if column.nullable else " NOT NULL") for column in table.columns]
        definitions.extend(f"{quote(name)} {definition}" for name, definition in TECHNICAL_COLUMNS)
        connection.execute(f"CREATE TABLE IF NOT EXISTS {quote(table.name)} ({', '.join(definitions)})")
        column_names = {row["name"] for row in connection.execute(f"PRAGMA table_info({quote(table.name)})")}
        for column in table.columns:
            if column.name not in column_names:
                raise LoadValidationError(
                    f"Existing table {table.name} does not match the supplied schema. "
                    "Use a new SQLite file for this schema version."
                )
        if "CONTRACTREFERENCE" in {column.name.upper() for column in table.columns}:
            actual = next(column.name for column in table.columns if column.name.upper() == "CONTRACTREFERENCE")
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS {quote('idx_' + table.name + '_contract')} "
                f"ON {quote(table.name)} ({quote(actual)})"
            )
        if "BALANCESHEETDATE" in {column.name.upper() for column in table.columns}:
            actual = next(column.name for column in table.columns if column.name.upper() == "BALANCESHEETDATE")
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS {quote('idx_' + table.name + '_balance_date')} "
                f"ON {quote(table.name)} ({quote(actual)})"
            )


def detect_encoding(path: Path, requested: str) -> str:
    if requested != "auto":
        path.read_text(encoding=requested)
        return requested
    sample = path.read_bytes()[:65_536]
    for encoding in ENCODING_CANDIDATES:
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    raise LoadValidationError(f"Unable to read {path.name} with a supported encoding. Use --encoding explicitly.")


def detect_delimiter(path: Path, encoding: str, requested: str) -> str:
    requested = {
        "tab": "\t", "\\t": "\t", "pipe": "|", "comma": ",", "semicolon": ";"
    }.get(requested.lower(), requested)
    if requested != "auto":
        if len(requested) != 1:
            raise LoadValidationError("--delimiter must be auto, a single character, or one of: tab, pipe, comma, semicolon")
        return requested
    with path.open("r", encoding=encoding, newline="") as source:
        sample = source.read(65_536)
    if not sample.strip():
        raise LoadValidationError(f"{path.name} is empty.")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(DELIMITER_CANDIDATES))
        return dialect.delimiter
    except csv.Error:
        first_line = next((line for line in sample.splitlines() if line.strip()), "")
        return max(DELIMITER_CANDIDATES, key=first_line.count)


def coerce(value: str, column: Column) -> Any:
    value = value.strip()
    if value == "":
        if column.nullable:
            return None
        raise LoadValidationError(f"{column.name} is required but empty")
    if column.data_type == "string":
        return value
    if column.data_type == "integer":
        try:
            number = Decimal(value.replace(",", ""))
            if number != number.to_integral_value():
                raise InvalidOperation
            return int(number)
        except (InvalidOperation, ValueError):
            raise LoadValidationError(f"{column.name} must be an integer, got {value!r}") from None
    if column.data_type == "decimal":
        try:
            return format(Decimal(value.replace(",", "")), "f")
        except InvalidOperation:
            raise LoadValidationError(f"{column.name} must be a decimal, got {value!r}") from None
    if column.data_type == "boolean":
        value_key = value.lower()
        if value_key in {"1", "true", "t", "yes", "y"}:
            return 1
        if value_key in {"0", "false", "f", "no", "n"}:
            return 0
        raise LoadValidationError(f"{column.name} must be boolean (0/1, true/false), got {value!r}")
    raise LoadValidationError(f"Unsupported schema type {column.data_type!r} for {column.name}")


def source_snapshot_date(value: str) -> str:
    """Normalise the bank's integer/text balance-sheet date before filtering."""
    value = str(value or "").strip()
    for pattern in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise LoadValidationError(f"BALANCESHEETDATE must be YYYYMMDD or YYYY-MM-DD, got {value!r}")


def read_rows(path: Path, table: SourceTable, encoding: str, delimiter: str, has_header: bool) -> tuple[list[str], Iterable[tuple[int, list[str]]]]:
    source = path.open("r", encoding=encoding, newline="")
    reader = csv.reader(source, delimiter=delimiter)
    try:
        first = next(reader)
    except StopIteration:
        source.close()
        raise LoadValidationError(f"{path.name} is empty.")
    if has_header:
        headers = [cell.strip() for cell in first]
        if not any(headers):
            source.close()
            raise LoadValidationError(f"{path.name} has an empty header row.")
        source_row_start = 2
    else:
        headers = [column.name for column in table.columns]
        reader = itertools.chain([first], reader)
        source_row_start = 1

    header_keys = [normalize(header) for header in headers]
    if len(header_keys) != len(set(header_keys)):
        source.close()
        raise LoadValidationError(f"{path.name} has duplicate column names in its header.")

    # Return a generator that closes the file even if a row fails validation.
    def values() -> Iterable[tuple[int, list[str]]]:
        try:
            for source_row, row in enumerate(reader, start=source_row_start):
                if not row or not any(cell.strip() for cell in row):
                    continue
                yield source_row, row
        finally:
            source.close()

    return headers, values()


def resolve_input_files(input_dir: Path, tables: dict[str, SourceTable]) -> tuple[dict[str, Path], list[Path]]:
    if not input_dir.is_dir():
        raise LoadValidationError(f"Input directory does not exist: {input_dir}")
    candidates = [path for path in input_dir.iterdir() if path.is_file() and not path.name.startswith(".")]
    matched: dict[str, Path] = {}
    for table_name in tables:
        # Bank extracts are commonly named like
        # ``AFSJordanContract.AFSContractImport``.  The first filename segment
        # is the bank table name; a bare table name remains supported too.
        options = [path for path in candidates if path.name == table_name or path.name.split('.', 1)[0] == table_name]
        if len(options) > 1:
            raise LoadValidationError(f"More than one source file matches table {table_name}: {', '.join(path.name for path in options)}")
        if options:
            matched[table_name] = options[0]
            candidates.remove(options[0])
    return matched, sorted(candidates)


def duplicate_fingerprint(table: SourceTable, values: list[Any], data_columns: list[str]) -> tuple[str, str]:
    """Return the governed duplicate identity and its human-readable reason.

    The account extract has a known bank-side duplication case.  Operations
    agreed that the first row is retained and later rows with the same
    five-field business identity are ignored but audited.  Other tables keep
    the safer exact-row behaviour until their natural keys are approved.
    """
    row = dict(zip(data_columns, values, strict=True))
    account_key = ("CONTRACTREFERENCE", "ACCOUNTREFERENCE", "AB_CODE", "AB_SOURCESYSTEM", "CURRENCY")
    if table.name == "EquationJordanAccountContract" and all(column in row and str(row[column] or "").strip() for column in account_key):
        identity = {column: str(row[column]).strip().upper() for column in account_key}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return digest, "Duplicate five-field account business key excluded; first occurrence retained."
    digest = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return digest, "Exact duplicate business row excluded; first occurrence retained."


def clear_entity_date(connection: sqlite3.Connection, entity_code: str, as_of_date: str, tables: Iterable[SourceTable]) -> None:
    batch_ids = [row["batch_id"] for row in connection.execute(
        "SELECT batch_id FROM etl_batches WHERE entity_code = ? AND as_of_date = ?", (entity_code, as_of_date)
    )]
    for batch_id in batch_ids:
        for table in tables:
            connection.execute(f"DELETE FROM {quote(table.name)} WHERE _etl_batch_id = ?", (batch_id,))
        connection.execute("DELETE FROM etl_batches WHERE batch_id = ?", (batch_id,))


def load_table(
    connection: sqlite3.Connection,
    table: SourceTable,
    source_file: Path,
    batch_id: str,
    loaded_at: str,
    encoding: str,
    delimiter: str,
    has_header: bool,
    as_of_date: str | None = None,
) -> tuple[int, int, int, int]:
    headers, rows = read_rows(source_file, table, encoding, delimiter, has_header)
    positions = {normalize(header): index for index, header in enumerate(headers)}
    expected = {normalize(column.name): column for column in table.columns}
    unknown_headers = [header for header in headers if normalize(header) not in expected]
    missing_required = [column.name for column in table.columns if not column.nullable and normalize(column.name) not in positions]
    if missing_required:
        raise LoadValidationError(f"{source_file.name} is missing required columns: {', '.join(missing_required)}")

    data_columns = [column.name for column in table.columns]
    target_columns = [*data_columns, *(name for name, _ in TECHNICAL_COLUMNS)]
    placeholders = ", ".join("?" for _ in target_columns)
    insert_sql = f"INSERT INTO {quote(table.name)} ({', '.join(quote(column) for column in target_columns)}) VALUES ({placeholders})"
    accepted = 0
    rejected = 0
    filtered = 0
    duplicates = 0
    # Technical ETL lineage fields are deliberately excluded.  Where an
    # approved natural key exists we use it; otherwise only byte-for-byte
    # business duplicates are excluded.
    retained_rows_by_identity: dict[str, int] = {}
    batch_values: list[tuple[Any, ...]] = []
    balance_sheet_date_column = next((column.name for column in table.columns if normalize(column.name) == "BALANCESHEETDATE"), None)
    balance_sheet_date_position = positions.get(normalize(balance_sheet_date_column)) if balance_sheet_date_column else None

    def flush() -> None:
        nonlocal batch_values
        if batch_values:
            connection.executemany(insert_sql, batch_values)
            batch_values = []

    try:
        for source_row, row in rows:
            raw = {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
            try:
                if as_of_date and balance_sheet_date_position is not None:
                    raw_date = row[balance_sheet_date_position] if balance_sheet_date_position < len(row) else ""
                    if source_snapshot_date(raw_date) != as_of_date:
                        filtered += 1
                        continue
                values: list[Any] = []
                for column in table.columns:
                    position = positions.get(normalize(column.name))
                    raw_value = row[position] if position is not None and position < len(row) else ""
                    values.append(coerce(raw_value, column))
                record_hash, duplicate_reason = duplicate_fingerprint(table, values, data_columns)
                retained_source_row = retained_rows_by_identity.get(record_hash)
                if retained_source_row is not None:
                    duplicates += 1
                    connection.execute(
                        """INSERT INTO etl_exact_duplicates
                        (batch_id, table_name, source_file, source_row, retained_source_row,
                         record_hash, reason, detected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            batch_id, table.name, source_file.name, source_row, retained_source_row,
                            record_hash, duplicate_reason, loaded_at,
                        ),
                    )
                    continue
                retained_rows_by_identity[record_hash] = source_row
                values.extend((batch_id, source_file.name, source_row, loaded_at))
                batch_values.append(tuple(values))
                accepted += 1
                if len(batch_values) >= 1_000:
                    flush()
            except LoadValidationError as error:
                rejected += 1
                connection.execute(
                    """INSERT INTO etl_rejections
                    (batch_id, table_name, source_file, source_row, reason, raw_values_json, rejected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (batch_id, table.name, source_file.name, source_row, str(error), json.dumps(raw), loaded_at),
                )
        flush()
    finally:
        close = getattr(rows, "close", None)
        if close:
            close()

    connection.execute(
        """INSERT INTO etl_file_loads
        (batch_id, table_name, source_file, encoding, delimiter, header_json, accepted_rows, rejected_rows, loaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (batch_id, table.name, source_file.name, encoding, delimiter, json.dumps(headers), accepted, rejected, loaded_at),
    )
    if unknown_headers:
        print(f"  warning: {table.name}: ignored unknown source columns: {', '.join(unknown_headers)}", file=sys.stderr)
    return accepted, rejected, filtered, duplicates


def run_load(args: argparse.Namespace) -> int:
    schema_file = Path(args.schema).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    database = Path(args.database).expanduser().resolve()
    tables = load_schema(schema_file)
    try:
        datetime.strptime(args.as_of_date, "%Y-%m-%d")
    except ValueError:
        raise LoadValidationError("--as-of-date must use YYYY-MM-DD, for example 2026-09-21") from None
    matched, extras = resolve_input_files(input_dir, tables)
    missing = sorted(set(tables) - set(matched))
    if not matched:
        raise LoadValidationError("No schema-matching source files found. A file may be named TableName or TableName.ImportName; the segment before the first dot must be the source table name.")
    if args.require_all and missing:
        raise LoadValidationError("Missing required source files: " + ", ".join(missing))

    print(f"Input: {input_dir}")
    print(f"Database: {database}")
    print(f"Matched: {len(matched)} of {len(tables)} schema tables")
    if missing:
        print("Not supplied: " + ", ".join(missing))
    if extras:
        print("Ignored files: " + ", ".join(path.name for path in extras))
    if args.dry_run:
        print("Dry run complete: no database was written.")
        return 0

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batch_id = str(uuid.uuid4())
    total_loaded = 0
    total_rejected = 0
    total_duplicates = 0
    with closing(connect(database)) as connection:
        try:
            with connection:
                create_metadata_tables(connection)
                create_source_tables(connection, tables.values())
                if args.mode == "replace-date":
                    clear_entity_date(connection, args.entity, args.as_of_date, tables.values())
                connection.execute(
                    """INSERT INTO etl_batches
                    (batch_id, entity_code, as_of_date, mode, schema_hash, input_directory, status, started_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'running', ?)""",
                    (batch_id, args.entity, args.as_of_date, args.mode, schema_hash(schema_file), str(input_dir), started_at),
                )
                for table_name, source_file in matched.items():
                    table = tables[table_name]
                    encoding = detect_encoding(source_file, args.encoding)
                    delimiter = detect_delimiter(source_file, encoding, args.delimiter)
                    loaded, rejected, filtered, duplicates = load_table(
                        connection, table, source_file, batch_id, started_at, encoding, delimiter, not args.no_header, args.as_of_date
                    )
                    total_loaded += loaded
                    total_rejected += rejected
                    total_duplicates += duplicates
                    message = f"  {table_name}: {loaded:,} loaded, {rejected:,} rejected"
                    if filtered:
                        message += f", {filtered:,} skipped for a different balance-sheet date"
                    if duplicates:
                        message += f", {duplicates:,} duplicate rows excluded and audited"
                    print(message)
                finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                connection.execute(
                    """UPDATE etl_batches SET status = 'completed', finished_at = ?, loaded_rows = ?, rejected_rows = ?
                    WHERE batch_id = ?""",
                    (finished_at, total_loaded, total_rejected, batch_id),
                )
        except Exception as error:
            connection.rollback()
            # A failed batch must not appear as a partial published snapshot.
            # The source is still untouched because the entire run is one transaction.
            raise LoadValidationError(f"Load failed; no rows were published: {error}") from error

    print(
        f"Completed batch {batch_id}: {total_loaded:,} loaded, {total_rejected:,} rejected, "
        f"{total_duplicates:,} duplicate rows excluded"
    )
    print("Next: review ETL audit tables and add the approved bank-to-ALM mapping/publish step.")
    return 0


def show_report(args: argparse.Namespace) -> int:
    database = Path(args.database).expanduser().resolve()
    if not database.exists():
        raise LoadValidationError(f"Database does not exist: {database}")
    with closing(connect(database)) as connection:
        rows = connection.execute(
            """SELECT batch_id, entity_code, as_of_date, status, started_at, loaded_rows, rejected_rows
               FROM etl_batches ORDER BY started_at DESC LIMIT ?""",
            (args.limit,),
        ).fetchall()
        if not rows:
            print("No ETL batches found.")
            return 0
        print("batch_id                             entity       as_of       status       loaded   rejected")
        for row in rows:
            print(
                f"{row['batch_id']}  {row['entity_code']:<11} {row['as_of_date']:<11} "
                f"{row['status']:<12} {row['loaded_rows']:>8,} {row['rejected_rows']:>10,}"
            )
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Bank text extract → auditable SQLite source/staging ETL")
    subparsers = cli.add_subparsers(dest="command", required=True)
    load = subparsers.add_parser("load", help="load table-named text files into SQLite")
    load.add_argument("--input-dir", required=True, help="directory containing files named exactly after source tables")
    load.add_argument("--database", required=True, help="SQLite database to create or update")
    load.add_argument("--schema", default=Path(__file__).with_name("schema_horizontal.json"), help="schema JSON file")
    load.add_argument("--entity", default="jordan", help="entity code recorded in ETL lineage")
    load.add_argument("--as-of-date", required=True, help="snapshot date recorded in ETL lineage, YYYY-MM-DD")
    load.add_argument("--mode", choices=("replace-date", "append"), default="replace-date", help="replace an existing entity/date load or retain it")
    load.add_argument("--encoding", default="auto", help="auto, utf-8-sig, utf-16, cp1256, or another Python encoding")
    load.add_argument("--delimiter", default="auto", help="auto, |, tab, ;, or ,")
    load.add_argument("--no-header", action="store_true", help="use schema column order when files do not contain headers")
    load.add_argument("--require-all", action="store_true", help="fail if any of the 25 schema files is missing")
    load.add_argument("--dry-run", action="store_true", help="validate file discovery without writing SQLite")
    load.set_defaults(func=run_load)
    report = subparsers.add_parser("report", help="show recent ETL batches")
    report.add_argument("--database", required=True, help="SQLite database to inspect")
    report.add_argument("--limit", type=int, default=20)
    report.set_defaults(func=show_report)
    return cli


def main_with_args(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except LoadValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def main() -> int:
    return main_with_args()


if __name__ == "__main__":
    raise SystemExit(main())
