# Bank-data readiness

## What this release changes

- The React browser no longer receives the saved portfolio to calculate it.
  New calculations use the selected entity's server-side canonical terms.
- Each saved-portfolio calculation copies immutable contract terms into
  database `RunContract` rows before queueing.  A later daily ETL refresh
  cannot alter a historical result.
- The Portfolio page is server-paginated (50 records at a time) and read-only.
  Approved ETL mappings, not ad-hoc browser edits, are the production source
  of canonical terms.
- The maturity proxy is entity Settings policy: a bank maturity always wins;
  otherwise the approved proxy date is copied only into the run snapshot and
  marked `proxy`.
- The cash-flow engine accepts either an approved explicit bank payment
  schedule (`cashflows`) or a generated schedule from complete contractual
  terms.  Explicit bank schedules have priority.  Missing dated terms remain
  visible exceptions; the engine does not invent a schedule.
- The text-file stage recognises `TableName.ImportName` extracts and keeps the
  first known duplicate account business key, with the later record recorded
  in `etl_exact_duplicates`.

## Daily bank-data flow

```text
Bank text / Hive / Oracle source
        -> immutable staging batch + rejects / duplicate audit
        -> approved versioned product mapping
        -> canonical PortfolioContract + regulatory source snapshots
        -> immutable RunContract snapshot
        -> queued calculation worker
        -> liquidity ladder, LCR/NSFR, stress tests and exports
```

## Deployment profile

| Environment | Database | Execution |
| --- | --- | --- |
| Local presentation | SQLite | `python start_local.py` starts Django and one safe database worker |
| Bank UAT / Production | PostgreSQL | Celery worker + RabbitMQ (the included `compose.yaml` starts web, worker, PostgreSQL and RabbitMQ) |
| Source data | Bank staging / warehouse | Controlled ETL publisher; never direct browser upload |

SQLite can hold much more than 100 MB, so a one-day local Jordan presentation
file is fine. It is not the production store for daily multi-entity banking
data or concurrent workers. Use PostgreSQL before UAT with recurring loads.

## Mandatory source-mapping gates before UAT

1. Confirm every product's contractual direction, principal balance, currency,
   maturity and product / GL mapping.
2. For dated products, map either the bank's future payment schedule or all
   contractual schedule terms: next payment date, accrual start, frequency,
   day-count, rate and repayment method.
3. Reconcile canonical balances, LCR/NSFR source lines and excluded records to
   the bank's signed control totals for each reporting date.
4. Approve the proxy-maturity policy and behavioural assumption version per
   entity; both are retained with every run.
5. Run PostgreSQL/Celery in UAT with representative daily volumes before
   enabling a second entity.

## Deliberate current boundary

This release makes the present 110k-contract local demonstration path safe and
auditable. A 2–3 million-contract production workload still requires the UAT
profile above plus partitioned source/run tables and streaming calculation
aggregation. That is an infrastructure and performance phase, not something
that should be hidden behind a SQLite demo switch.
