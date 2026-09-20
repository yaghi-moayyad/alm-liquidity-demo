# Verification — Experimental Behavioural Engine v0.6.0

## Passed in this build environment

- Python source compilation for Django/config/engine modules.
- Behavioural engine regression suite: **7 tests passed**.
- Modified TypeScript/TSX files parsed successfully using the TypeScript compiler API.
- Mac launcher shell syntax checked.

### Behavioural regression coverage

- Dated-principal conservation after behavioural timing shifts.
- NMD runoff generation plus explicit residual/core balance.
- Term-deposit rollover beyond original maturity.
- Term-deposit early-withdrawal event and rule audit metadata.
- Security liquidation + haircut with no ladder double counting.
- Contractual product treatment bypasses behavioural timing rules.
- Contractual calculation basis bypasses the behavioural engine.

## Not executable in this sandbox

This environment has no package-network access. Therefore it could not download the pinned Django/npm dependency trees for a complete Django integration test or fresh Vite production build.

`START_MVP.command` handles this on the local machine: it installs dependencies, rebuilds React when source changes, applies migrations, seeds the demo safely and launches the application.
