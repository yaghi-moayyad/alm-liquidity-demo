# Overview and Liquidity Analytics update

This ZIP overlays the recovered `alm-liquidity-demo-working-baseline` project. It does not push, deploy, delete data or introduce a Django migration. It changes only the seven files listed below plus this guide.

From your **Django project root** (the folder containing `manage.py` and `frontend/`), run:

```bash
unzip -o ~/Downloads/liquidity-cockpit-analytics-update.zip
npm --prefix frontend ci
npm --prefix frontend run build
node --experimental-strip-types --test frontend/tests/liquidityMetrics.test.mjs
python manage.py check
```

Then inspect with `git diff` and `git status --short` before committing and pushing. Render's existing build will rebuild the frontend on deployment; no new migrations are required. If running locally, `python start_local.py` uses the normal Django setup. Do not run `unzip` from inside `frontend/`.

Changed files:

- `frontend/src/liquidityMetrics.ts`: ladder-backed calculations, cushion percentage, comparison and export.
- `frontend/src/pages/Overview.tsx`: dated CRO/ALCO liquidity snapshot and drill-through.
- `frontend/src/pages/LiquidityAnalytics.tsx`: linked interactive charts, bucket breakdown, previous-run bridge, product-line detail and CSV.
- `frontend/src/pages/Results.tsx`: selected bucket/line deep-link, plus the management gap percentage row.
- `frontend/tests/liquidityMetrics.test.mjs`: deterministic checks of the reported mathematics.
- `render_start.sh` and `start_local.py`: idempotent provisioning of the requested `adel` demo superuser.

The new gap percentage is **bucket gap after counterbalancing capacity ÷ (bucket outflows + off-balance-sheet obligations)**. It shows N/A for a zero denominator and is **not LCR**. This does not validate capacity eligibility, encumbrance, funding fungibility or the bank's risk-appetite thresholds. Historical cash-flow comparison requires a compatible saved run at an earlier reporting date.

Security: both the old `osama` demo account and the newly requested `adel` demo account have known, full-administrator credentials in this public demonstration build. Remove them, their startup commands and the synthetic-data seed before connecting any actual bank data or using the system beyond an isolated mock demo.
