# Liquidity Cash Flow MVP — Behavioural Engine Experimental Build

Complete local Django + React/TypeScript Liquidity MVP with contractual and behavioural cash-flow views. Engine version: **0.6.0**.

## Fastest way to run on macOS

Double-click `START_MVP.command`, or open Terminal in this folder and run:

```bash
./START_MVP.command
```

The launcher will automatically:

- create `.venv` if needed;
- install the pinned Python requirements;
- install npm dependencies when needed;
- rebuild the React frontend when frontend source changes;
- run Django migrations;
- ask you to create a local administrator on first use;
- seed/preserve the synthetic Jordan demo;
- start Django and the local calculation worker;
- open `http://127.0.0.1:8000/`.

`start_mac.command` continues to work as well and uses the same launcher logic.

## Behavioural cash-flow engine

The experimental behavioural engine supports:

- Contractual / Behavioural / Hybrid product treatment;
- NMD runoff curves and explicit residual/core balance;
- loan prepayment curves;
- term-deposit early withdrawal and rollover;
- security liquidation timing and haircut;
- persisted behavioural cash-flow events;
- contractual vs behavioural ladder and profile comparison;
- contract-level audit view showing behavioural source/rule;
- versioned saved behavioural assumptions.

See `BEHAVIORAL_ENGINE_V1.md` for methodology, validation and current limitations.

## Manual development commands

Backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runlocal
```

Frontend build after editing React/TypeScript:

```bash
cd frontend
npm ci
npm run build
```

The Vite build writes the production bundle to `static/app`, which Django serves.

## Experimental LCR & NSFR source-data engine

This local build includes a new **LCR & NSFR** module in the left navigation. It calculates directly from the saved portfolio, persists contract-level regulatory contributions, provides line drill-down and exports a combined Excel workbook. See `REGULATORY_ENGINE_V1.md` for scope and methodology boundaries.
