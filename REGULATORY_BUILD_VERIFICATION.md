# Regulatory build verification

Validated in the build sandbox:

- Python syntax compilation: passed for `cashflows` and `config`.
- Regulatory engine focused arithmetic check: passed (HQLA/outflow/inflow, 75% inflow cap, LCR ratio, NSFR factor calculation).
- TypeScript/TSX parse check: passed for Regulatory page, router, shell, API and type definitions.
- Existing behavioral v0.6.0 code preserved as the baseline.

Not fully executable in this sandbox:

- Django test suite / migrations: Django packages are not installed in the sandbox runtime.
- Fresh Vite production build: npm dependency installation timed out in this sandbox.

`START_MVP.command` is designed to install the pinned backend/frontend dependencies, build React, apply migration `0013_regulatory_lcr_nsfr`, seed the demo and start the local application on the user's Mac.
