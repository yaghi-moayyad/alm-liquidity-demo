# Bank text files → SQLite source ETL

This is a **standalone ingestion tool**, intentionally outside the Django/React project and outside Git.
It is the safe first half of the future bank integration:

`bank text extracts → SQLite source/staging database → approved mapping/publish step → ALM application`

It does **not** modify the Django application's SQLite database, GitHub repository, Render deployment, or bank Hive tables.

## Simplest temporary Jordan demonstration

Unzip the `bank_text_to_sqlite_etl` folder **inside** the local `alm-liquidity-demo` folder, beside `manage.py`. Then the only command needed is:

```bash
python3 bank_text_to_sqlite_etl/run_demo.py "/path/to/bank-files" --as-of-date 2026-09-15
```

It automatically finds the local Django project and its SQLite database, uses Jordan defaults, creates `jordan-bank-demo` if needed, and tracks progress in `pipeline_status.json`. When `--as-of-date` is supplied, every table with a `BALANCESHEETDATE` column is filtered to that date; older rows in the same extract are skipped rather than blocking the demonstration.

On the first run it automatically creates `jordan_mapping.json` with temporary, table-name-based demonstration mappings, then performs the full staging → validation → Django publication sequence. You do not need to edit it. `mapping_inventory.json` and `alm_publish_report.json` show what was mapped, excluded, or treated as uncertain.

The automatic demonstration mapping includes customer call accounts, undrawn commitments, loans/overdrafts, Exim/FinOne/commercial lending, and available-for-sale securities. For dated products it uses a clearly labelled **principal-at-reported-maturity** profile until the bank contractual cash-flow schedule mapping is validated. Derivatives, FX, swaps, party/rating tables, GL, and treasury tables whose asset/liability direction cannot be established safely remain excluded and visible in the report.

This is a convenience wrapper for the temporary local demonstration only. The explicit commands below remain the future-ready option for Hive, PostgreSQL, Oracle, and controlled production integration.

## One-command guided pipeline (explicit mode)

For the bank demonstration, use `run_pipeline.py`. It runs the full controlled sequence and prints a clear description of the active step:

1. Check the approved mapping and local paths.
2. Load bank text files into separate source/staging SQLite.
3. Create a mapping inventory.
4. Validate mappings, dates, currencies, rejected rows, and coverage.
5. Publish canonical portfolio data and approved LCR positions into the local Django ALM application.

It also updates `pipeline_status.json` after every phase, so the status is visible even if a long load or a validation error occurs.

```bash
python3 run_pipeline.py \
  --input-dir "/path/to/bank-files" \
  --source-database "./jordan_bank_source.sqlite3" \
  --mapping "./jordan_mapping.json" \
  --django-project "/path/to/alm-liquidity-demo" \
  --app-database "/path/to/alm-liquidity-demo/data/db.sqlite3" \
  --source-entity jordan \
  --as-of-date 2026-09-21 \
  --create-entity
```

For the first attempt, add `--validate-only`. It completes source loading, inventory, and mapping validation but deliberately stops before changing the local Django application:

```bash
python3 run_pipeline.py \
  --input-dir "/path/to/bank-files" \
  --source-database "./jordan_bank_source.sqlite3" \
  --mapping "./jordan_mapping.json" \
  --django-project "/path/to/alm-liquidity-demo" \
  --app-database "/path/to/alm-liquidity-demo/data/db.sqlite3" \
  --source-entity jordan \
  --as-of-date 2026-09-21 \
  --create-entity \
  --validate-only
```

The live files created beside the command are:

| File | Meaning |
|---|---|
| `pipeline_status.json` | Current phase, percentage, description, and full event history |
| `mapping_inventory.json` | Source-product and account-nature inventory for the approved mapping |
| `alm_publish_report.json` | Canonical mapping coverage, excluded rows, and publication outcome |

The one command still requires a completed, approved `jordan_mapping.json`. It will not guess product treatment, payment timing, or regulatory classification merely to finish the pipeline.

## What it accepts

Put the bank extracts in one folder. Each filename must be the exact `table_name` in `schema_horizontal.json`, with **no extension**. For example:

```text
bank_extract_2026_09_21/
├── EquationJordanAccountContract
├── EquationJordanLoanContract
├── TreasuryJordanDataMMContract
├── TreasuryJordanDataCFLContract
└── GLJordanContract
```

Text files may be pipe-delimited, tab-delimited, comma-separated, or semicolon-separated. The loader detects the delimiter and one of UTF-8, UTF-16, CP1256, or Latin-1 automatically. By default it expects a header row, matches headers case-insensitively, and permits harmless spaces/underscores differences. If auto-detection is ever wrong, add, for example, `--delimiter pipe` or `--delimiter tab`.

## Run it locally

From the `bank_text_to_sqlite_etl` directory:

```bash
python3 etl.py load \
  --input-dir "/path/to/bank_extract_2026_09_21" \
  --database "./jordan_bank_source.sqlite3" \
  --entity jordan \
  --as-of-date 2026-09-21
```

The default mode is `replace-date`: rerunning an extract for the same entity and date replaces only the prior source staging load for that date. Use `--mode append` only when you explicitly want to retain multiple versions of the same date.

Before a live load, you can confirm that names match the schema:

```bash
python3 etl.py load \
  --input-dir "/path/to/bank_extract_2026_09_21" \
  --database "./jordan_bank_source.sqlite3" \
  --entity jordan \
  --as-of-date 2026-09-21 \
  --dry-run
```

To require all 25 source files:

```bash
python3 etl.py load --input-dir "/path/to/extract" --database "./jordan_bank_source.sqlite3" \
  --entity jordan --as-of-date 2026-09-21 --require-all
```

To inspect ETL history:

```bash
python3 etl.py report --database "./jordan_bank_source.sqlite3"
```

## What it creates

The SQLite database has one source table for each table in the supplied schema, preserving every named source column. Each source row also receives four technical lineage columns:

| Column | Purpose |
|---|---|
| `_etl_batch_id` | Exact load batch that produced the row |
| `_etl_source_file` | Original input filename |
| `_etl_source_row` | Original row number |
| `_etl_loaded_at` | UTC load timestamp |

It also creates audit tables:

| Table | Purpose |
|---|---|
| `etl_batches` | One record for each load, date, entity, status, and totals |
| `etl_file_loads` | File-level row counts, encoding, delimiter, and headers |
| `etl_rejections` | Invalid source rows and the precise reason they were rejected |

Decimal amounts are stored as **TEXT** in source staging so SQLite cannot silently round bank values. Source dates remain as supplied by the schema (currently integer fields such as `YYYYMMDD`).

## Presentation flow

For the bank presentation, use one approved Jordan as-of date and show:

1. The source extract folder and the successful ETL batch.
2. `etl_batches` / `etl_file_loads` as data lineage and reconciliation evidence.
3. The mapped ALM application results only after the bank-to-ALM product and regulatory mappings are approved.

## Publish approved data into the local ALM application

`publish_to_alm.py` is the controlled second step. It reads only a **completed ETL batch** and writes canonical records into a local copy of the Django ALM application. It does not access text extracts, Hive, GitHub, Render, or production.

### 1. Build an inventory inside the bank environment

This records only source table names, row counts, and mapping-relevant distinct values such as product, account nature, currency, and product code.

```bash
python3 publish_to_alm.py inventory \
  --source-database "./jordan_bank_source.sqlite3" \
  --source-entity jordan \
  --as-of-date 2026-09-21 \
  --output "./mapping_inventory.json"
```

### 2. Create an approved mapping file

Copy `mapping_template.json` to `jordan_mapping.json`, then fill it using the inventory. `mapping_example.json` shows the required shape, but its conditions and regulatory categories are **illustrative only** and must not be used until confirmed. When using these explicit commands rather than `run_demo.py`, replace the template's `"as_of_date": "AUTO"` with the actual `YYYY-MM-DD` reporting date.

Every source rule explicitly specifies its table, product, direction implied by product, balance field, currency field, and—where a product is dated—the contractual schedule fields. The publisher refuses to invent payment dates, rate conventions, or LCR categories.

### 3. Validate the mapping first

Activate the same Python virtual environment used by the local Django app, then run:

```bash
python3 publish_to_alm.py publish \
  --source-database "./jordan_bank_source.sqlite3" \
  --mapping "./jordan_mapping.json" \
  --django-project "/path/to/alm-liquidity-demo" \
  --app-database "/path/to/alm-liquidity-demo/data/db.sqlite3" \
  --dry-run \
  --report "./alm_publish_report.json"
```

The report shows source coverage and every excluded row with a precise reason. By default, even one mapped-row rejection blocks publication. `--allow-rejected` permits a partial, explicitly labelled publication; `--require-full-coverage` blocks publication until every source row has an approved mapping.

### 4. Publish to the local application

Remove `--dry-run` only after reviewing the report. For a new local entity, add `--create-entity`:

```bash
python3 publish_to_alm.py publish \
  --source-database "./jordan_bank_source.sqlite3" \
  --mapping "./jordan_mapping.json" \
  --django-project "/path/to/alm-liquidity-demo" \
  --app-database "/path/to/alm-liquidity-demo/data/db.sqlite3" \
  --create-entity \
  --report "./alm_publish_report.json"
```

The publisher creates or replaces the target entity's canonical portfolio, updates its as-of date, synchronizes a temporary product catalogue (GL remains admin-only), and—when approved `lcr_rules` are enabled—publishes LCR source positions and a dated regulatory snapshot.

### Important current boundary

The current Django calculation engine accepts at most 2,000 contracts in one interactive calculation and generates schedules from canonical terms. This publisher can load a larger mapped portfolio, but it does **not** invent schedules for products whose dates/repayment conventions are not supplied. Streaming calculation for millions of contracts and direct ingestion of full contractual schedule rows are the next application-engine enhancement after this mapping is proven.

## Safety

- Run the tool against exported text files or a read-only copy only.
- Do not place customer files in Git or upload them outside the bank environment.
- The tool uses only Python's standard library; no package installation or network access is required.
