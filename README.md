# Liquidity Risk & ALM Platform

Django + React/TypeScript liquidity-risk application for contractual and
behavioural cash flows, liquidity ladders, LCR/NSFR and LCR stress testing.

## Run locally

```bash
python -m pip install -r requirements.txt
python manage.py migrate
DEMO_PASSWORD='choose-a-local-demo-password' python manage.py seed_demo --username demo --create-user --replace
python manage.py runserver
```

Open `http://127.0.0.1:8000`. The bundled `Jordan-Mock` entity contains annual-report-aligned but fully synthetic data for testing: JOD/USD lending, deposits, placements, funding and counterbalancing cash.
Choose a local-only demo password before creating the `demo` user. For a deployed demo, set `DEMO_PASSWORD` as a hosting-platform secret.

## Bank-data operation

Use the separate `bank_text_to_sqlite_etl` package to stage the bank's text
extracts and publish approved mappings into the canonical portfolio. The app
does not rely on browser uploads for a bank portfolio. Read
[`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) before loading UAT data.

## Public mock demo

The Render deployment uses synthetic data only and serves the app publicly over HTTPS. It uses inline calculation execution for the small demo workload; bank UAT/production uses PostgreSQL and a separate worker.

For frontend development:

```bash
cd frontend
npm install
npm run dev
```

The packaged Django app already includes a production frontend build in `static/app`.
