# Project FluSight Edge

## What This Is
Automated trading bot that exploits the 1-3 week informational lag between real-time epidemiological surveillance signals and CDC's official FluSurv-NET hospitalization reports — the sole resolution source for Polymarket's weekly flu hospitalization markets.

## Core Thesis
Polymarket flu markets are priced by retail participants who rely on last week's CDC report. By fusing 7 leading indicators (wastewater, ED syndromic, Google Trends, antiviral Rx, FluSight ensemble, Delphi versioned data, ILINet), we predict next week's cumulative rate within a tighter interval than the market implies.

## Coding Conventions
- Python 3.11+
- Use `httpx` for async HTTP, `requests` for sync
- SQLite for all data storage (single `data/flusight.db` file)
- All signals return a standardized `SignalResult` dataclass (see signals/CLAUDE.md)
- Type hints everywhere, but no docstrings unless logic is non-obvious
- Tests use `pytest`
- Config via `config.py` (not env vars, except for secrets in `.env`)
- Epiweeks use CDC MMWR week numbering (Sunday-Saturday)

## Key Domain Knowledge
- **FluSurv-NET** covers only 14 states: CA, CO, CT, GA, MD, MI, MN, NM, NY, NC, OH, OR, TN, UT
- Cumulative hospitalization rate = total season hospitalizations per 100,000 population
- Markets resolve on **final** reported rate, not initial (backfill revisions are 15-30% upward)
- CDC publishes FluView reports on Fridays
- Epiweek 1 of 2026 started Dec 29, 2025

## Architecture
```
signals/     → One module per data source, each exposes fetch() → SignalResult
models/      → backfill.py (revision prediction), nowcast.py (bracket probabilities), calibration.py
trading/     → polymarket.py (API), kelly.py (sizing), executor.py (order management)
monitoring/  → alerter.py (Telegram), pnl.py (P&L tracking)
config.py    → All constants, thresholds, FluSurv-NET state lists
db.py        → SQLite helpers
schema.sql   → Database schema
```

## Important Files
- `config.py` — single source of truth for all constants
- `schema.sql` — database schema, run to initialize
- `db.py` — all database operations go through here
- `signals/*.py` — each signal module is independent and testable in isolation
