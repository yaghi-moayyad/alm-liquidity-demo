# Behavioural Cash-Flow Engine v0.6.0 — Requirement Checklist

- [x] Contractual / Behavioural / Hybrid product treatment
- [x] Separate behavioural cash-flow engine behind the ladder
- [x] NMD runoff curves
- [x] Loan prepayment curves
- [x] Term-deposit early withdrawal
- [x] Term-deposit rollover
- [x] Security liquidation timing + haircut
- [x] Separate persisted behavioural cash-flow events for auditability
- [x] Contractual vs Behavioural ladder comparison
- [x] Behavioural cash-flow profile
- [x] Assumption UI for all v1 behavioural rule types
- [x] Remaining/core NMD balance explicitly preserved
- [x] Principal reconciliation preserved across timing shifts
- [x] Engine version 0.6.0
- [x] Focused automated regression tests passing (7/7 in build sandbox)

## Additional usability/audit improvements

- Staff can change product cash-flow treatment from the Behavioural Engine screen without seeing GL mappings.
- Contract Schedules can toggle Contractual / Behavioural persisted events.
- Behavioural schedule rows show source mechanism and rule title.
- Behavioural cash-flow API and CSV export added.
- Security liquidation is persisted as an audit event while remaining counterbalancing capacity in the ladder, preventing double counting.
- One-click Mac launcher automatically rebuilds changed React sources before startup.
