# Apply the bank-data hardening update

Run these commands from the ALM project root — the folder that contains
`manage.py` and `frontend`.

```bash
unzip -o ~/Downloads/alm-bank-data-hardening-complete.zip
python manage.py migrate
npm --prefix frontend ci
npm --prefix frontend run build
python manage.py test cashflows.tests.test_engine cashflows.tests.test_entities
python manage.py check
git add .
git commit -m "Harden bank portfolio calculations and ETL"
git push origin main
```

Then start locally in the usual way:

```bash
python start_local.py
```

For a bank extract, rerun the ETL pipeline after applying the update. Its
loader now accepts both `TableName` and `TableName.ImportName` file names. The
existing `jordan_mapping.json`, SQLite source database and audit/report files
are not included in this update and are not replaced.

The new entity Settings card is **Proxy maturity for undated positions**. It
uses the bank maturity whenever present; only blank maturities receive the
approved proxy date in a new calculation snapshot.
