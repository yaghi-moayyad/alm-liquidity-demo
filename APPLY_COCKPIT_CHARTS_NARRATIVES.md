# CRO cockpit charts and regulatory movement narratives

Run these commands from the project root (the folder that contains `manage.py` and `frontend`):

```bash
unzip -o ~/Downloads/cockpit-charts-regulatory-narratives.zip
npm --prefix frontend ci
npm --prefix frontend run build
python manage.py check
git add frontend/src/pages/Overview.tsx frontend/src/pages/LiquidityAnalytics.tsx frontend/src/pages/RegulatoryReport.tsx frontend/src/pages/Results.tsx frontend/src/pages/NewCalculation.tsx frontend/src/liquidityMetrics.ts frontend/src/regulatoryNarrative.ts frontend/tests/liquidityMetrics.test.mjs
git commit -m "Enhance liquidity cockpit and bucket editor"
git push origin main
```

The update contains only frontend code. It does not add migrations or change calculations.

What changes:

- Overview: becomes a compact CRO cockpit, without changing its navigation name or removing the detailed LCR, NSFR, stress-testing or ladder pages.
- Overview: replaces the liquidity runway with a full-width regulatory trend, full-width maturity-pressure chart, a principal gap-ratio heat strip, and a calculated LCR stress-resilience view.
- Overview: adds clear LCR and NSFR movement explanations for the latest available month; each is clickable and opens the correct report/month.
- LCR and NSFR: the explanation updates whenever a user selects any historical point from the trend or history table. The wording cites the two deterministic calculated contributors and their percentage-point effect.
- Liquidity Analytics: makes **Scheduled flows and capacity** a full-width chart.
- Maturity ladder: corrects the percentage row to **principal contractual gap including counterbalancing capacity / (as-of total outflow balance + signed as-of off-balance-sheet balance)**. It is not LCR, and it is `N/A` when the signed denominator is not positive.
- New calculation: adds a visual maturity-bucket editor. Users can add, remove and edit upper-day boundaries, see the resulting ranges live, restore the saved entity default and, for staff, save the current profile as the default for future runs. Every submitted run remains tied to its own saved bucket definition.
