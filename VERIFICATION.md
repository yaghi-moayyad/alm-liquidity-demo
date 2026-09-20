# Verification — React + Django v0.3

## Executed

- React + TypeScript + Material UI dependencies installed and compiled with Vite. Strict TypeScript checking passed; prebuilt hashed frontend assets are included.
- Django system checks passed. Entity/portfolio/configuration migrations applied successfully, and no model/migration drift was found.
- **36 Django tests passed**: financial examples, dates, principal closure, bucket/currency segregation, ORM persistence, worker execution, authentication, CSRF, user-scoped runs, tokens, idempotency, exports, entity creation, saved portfolio separation, stale revision conflicts, staff-only writes, historical snapshot preservation and idempotent Jordan-Mock setup.
- Generated OpenAPI schema validated with warnings treated as errors.
- **Actual Chromium/Playwright browser testing passed against real Django and a separate calculation worker**:
  - Django login and React dashboard with Jordan-Mock's preloaded baseline.
  - Search, edit a contract, save the portfolio.
  - Configure → Validate → Calculate workflow.
  - Results, individual contract schedules and reconciliation controls.
  - CSV download.
  - Add Egypt-Test, confirm its portfolio is empty, then switch back to Jordan-Mock without mixing data.
  - Mobile navigation and no document-level horizontal overflow at 390px.
- Desktop (1536px), tablet (1024px) and mobile (390px) screenshots captured. Desktop and mobile screenshots visually reviewed. No browser JavaScript errors during the tested workflow.
- Chart animations disabled so reported profiles render deterministically and are immediately visible.

## Limits

- The frontend build reports an advisory for a main chunk above 500 kB; page routes are split, and the main chunk is approximately 187 kB compressed. This does not prevent the build or local use.
- Docker/PostgreSQL/RabbitMQ end-to-end transport was not run because Docker is unavailable in the build environment. Celery's task/service integration is covered by tests.
- Windows/macOS launchers were not executed; tests ran on Linux/Python 3.12 with Node 24 for frontend building.
- This remains a functionality prototype, capped at 2,000 contracts per run, pending the bank's product catalogue and full portfolio performance testing.

No runtime database, test credentials, session tokens, generated secrets, node_modules or Python virtual environment is included in the ZIP. Synthetic data is installed by migrations; the initial user-owned result is generated during guided startup.
