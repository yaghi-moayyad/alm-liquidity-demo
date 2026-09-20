# Behavioural Cash-Flow Engine v1 — Experimental Local Build

This package is the complete Liquidity MVP plus the experimental behavioural cash-flow engine. It is intended for local review only and does not connect to or modify GitHub/Render.

## Included in v0.6.0

1. **Contractual / Behavioural / Hybrid product treatment**
   - Editable from the Behavioural Cash-Flow Engine screen for staff users.
   - GL mappings remain hidden from normal application views and stay in Django administration.
2. **Separate behavioural cash-flow engine** in `cashflows/behavioral_engine.py`.
3. **NMD runoff curves** using cumulative runoff points.
4. **Loan prepayment curves** using cumulative prepayment points.
5. **Term-deposit early withdrawal** using cumulative early-withdrawal points.
6. **Term-deposit rollover** using rollover percentage and tenor.
7. **Security liquidation timing + haircut** as behavioural counterbalancing-capacity events.
8. **Persisted `BehavioralCashFlow` events** with source rule ID/title for run-level auditability.
9. **Contractual vs Behavioural ladder comparison** from the same saved run.
10. **Behavioural cash-flow profile** using the saved calculation boundaries.
11. **Updated assumption editor** for runoff, prepayment, early withdrawal, rollover, liquidation timing and haircut.
12. **Explicit NMD residual/core balance** when the runoff curve does not reach 100%; no maturity is invented.
13. **Principal reconciliation** when prepayment, withdrawal or rollover moves dated principal.
14. **Engine version `0.6.0`.**
15. **Focused regression tests** for the behavioural engine.

## Extra auditability added in the complete build

The Contract Schedules screen can switch between Contractual and Behavioural events. Behavioural rows show the behavioural source and saved rule title. Separate API/CSV endpoints expose the persisted behavioural event stream.

## Behavioural mechanisms

### NMD runoff
A cumulative curve is converted into incremental dated outflows. Any portion not run off remains an explicit residual/core balance without an invented maturity date.

### Loan prepayment
The curve moves principal from later legal payments to earlier expected dates. V1 reduces the furthest contractual principal first to preserve nearer scheduled instalments.

### Term-deposit early withdrawal
The curve moves a portion of maturity principal into earlier behavioural outflows.

### Term-deposit rollover
A configured portion of remaining maturity principal is moved beyond original maturity by the selected rollover tenor.

### Security liquidation and haircut
Approved liquidation timing and haircut create counterbalancing-capacity events. The contractual security repayment is omitted from the behavioural ladder when the security is assumed liquidated earlier, preventing double counting.

## Product treatment meaning

- **Contractual** — behavioural timing rules are ignored.
- **Behavioural** — intended for products such as NMDs whose expected maturity is primarily driven by behaviour.
- **Hybrid** — the legal schedule remains the baseline and approved behavioural assumptions shift part of its timing.

For dated instruments, v1 behavioural mechanisms are timing adjustments to the contractual principal schedule. A later fully behavioural replacement model can be added without changing the ladder/reporting architecture.

## Interest limitation in v1

Behavioural rules currently change **principal timing only**. Contractual interest remains unchanged. Interest should only be recalculated after the bank agrees the required methodology for prepayment, withdrawal penalties, term reduction versus instalment reduction, and repricing.

## ML / statistical calibration

No machine learning is required to run the engine. A future calibration module can estimate runoff, prepayment, early-withdrawal, rollover or core-balance parameters from historical data. Approved parameters then feed this same execution engine.

## Validation performed in this environment

- Python source compilation: passed.
- Behavioural engine regression tests: **7/7 passed**.
- TypeScript/TSX syntax parsing of the modified frontend files: passed.
- Full Django integration tests could not be executed because this sandbox cannot download the pinned Python dependencies.
- A full Vite build could not be completed because this sandbox cannot download npm dependencies. The local launcher automatically installs dependencies and rebuilds the frontend on your machine when source changes.

## One-click Mac startup

Double-click `START_MVP.command`, or from Terminal:

```bash
./START_MVP.command
```

The launcher creates the Python virtual environment, installs backend dependencies, installs/builds the React frontend when needed, applies migrations, creates an admin account on first use, seeds the demo safely, and starts Django plus the local calculation worker.
