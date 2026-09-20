# LCR & NSFR Engine v1

This experimental module calculates LCR and NSFR directly from the saved ALM source portfolio. It does not require a pre-calculated regulatory workbook as input.

## Processing path

Source portfolio -> regulatory mapping -> LCR/NSFR contribution rows -> report totals -> persisted calculation -> drill-down/export.

## LCR v1

- Level 1 HQLA contribution for cash / central-bank balances.
- Detailed Treasury-bond mapping can classify `Marketable Securities & CDs / Tbond` as Level 1 HQLA in the demo configuration.
- Deposit / wholesale funding outflows are factor-driven.
- Loan / financial-institution inflows are factor-driven and can be limited to <=30-day maturity.
- Eligible inflows are capped at 75% of gross outflows.
- Net cash outflows and LCR are calculated and persisted.

## NSFR v1

- Source products map to ASF or RSF lines.
- Factors may be fixed or selected by residual-maturity band: `<6m`, `6-12m`, `>=1y`, `open`.
- ASF, RSF and NSFR are calculated and persisted.

## Auditability

Every contribution persists:

- contract ID
- source product and currency
- converted reporting-currency balance
- report line/code
- factor
- maturity band
- weighted amount
- treatment metadata including source balance, FX rate and days to maturity

The UI lets the user click an LCR/NSFR line and see the contributing contracts.

## Reports

The module produces:

- on-screen LCR report
- on-screen NSFR report
- CSV exports for each metric
- one Excel workbook containing LCR, NSFR, controls/warnings and audit contributions

## Mapping / methodology boundary

The current ALM source records do not contain every regulatory attribute needed for a production LCR/NSFR submission (for example stable-vs-less-stable retail status, operational-deposit status, security credit quality, encumbrance, and all OBS classifications). Therefore these are kept in a configurable regulatory mapping layer rather than invented on individual contracts.

The seeded mapping is an experimental starting point derived from the earlier LCR/NSFR automation design and the current liquidity product catalogue. It is explicitly **not represented as bank- or regulator-approved methodology**. Before production use, the mapping/factors must be reconciled to the current approved bank/CBJ templates and methodology.

## Scope intentionally deferred

- legal-entity consolidation
- significant-currency regulatory views
- transferability restrictions
- Level 2 HQLA composition/caps beyond the current configurable line treatment
- detailed secured-funding/derivative treatment
- full off-balance-sheet classification
- movement analysis and prior-period bridges
- regulatory approval workflow
- AI commentary
