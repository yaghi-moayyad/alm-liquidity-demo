# Apply: calculation-time data readiness

Run these commands from the ALM project root. The archive also updates the
separate `bank_text_to_sqlite_etl` folder beside the Django project.

```bash
unzip -o ~/Downloads/data-readiness-calculation-time-update.zip
npm --prefix frontend ci
npm --prefix frontend run build
python manage.py migrate
python manage.py test cashflows.tests.test_engine cashflows.tests.test_entities
python manage.py check
git add .
git commit -m "Add calculation-time data readiness workflow"
git push origin main
```

## What changes

- The publisher keeps dated contracts with missing, invalid, or overly long
  first-accrual dates in the canonical portfolio instead of dropping them.
- It retains safe date candidates such as `NEXTINTERESTPAYMENTDATE` alongside
  the imported canonical terms.
- **New calculation → Review data readiness** groups only problematic
  contracts by source table, product, and issue.
- A user applies one run-only treatment to a whole group: use a supplied bank
  date, enter one next-payment date, derive from reporting date plus frequency,
  apply proxy maturity, or exclude and disclose.
- The selected rule is retained in the immutable run snapshot. It never edits
  the bank files or the current portfolio.

## Important operational flow

Re-publish the bank snapshot after applying this update so the app receives
`source_date_candidates`. Existing imported contracts still support the
manual-date and derive-from-reporting-date options, but cannot expose source
date fields that were not retained in their earlier import.
