# FluSight Edge

A quantitative trading system that exploits informational lags in CDC epidemiological data to trade flu hospitalization bracket markets on [Polymarket](https://polymarket.com/). Built as a full-stack research-to-execution pipeline: signal ingestion, statistical modeling, position sizing, and operational monitoring — all in Python.

---

## The Edge

Polymarket runs weekly prediction markets on U.S. influenza hospitalization rates (e.g., "Will the cumulative rate be 60–70 per 100K by end of season?"). These markets resolve on **final** CDC FluSurv-NET data, but early-season prices reflect **preliminary** numbers that are systematically revised upward 15–30% as lagging hospitals report over subsequent weeks.

FluSight Edge exploits this by:

1. **Backfill arbitrage** — Modeling FluSurv-NET revision patterns to predict final rates from preliminary reports
2. **Multi-signal fusion** — Combining 7 leading indicators that move 1–3 weeks ahead of official hospitalization counts
3. **Calibrated bracket probabilities** — Converting point estimates into properly calibrated probability distributions over market brackets
4. **Fractional Kelly sizing** — Position sizing at 0.20x Kelly to account for model uncertainty
5. **SPRT monitoring** — Sequential probability ratio test to detect edge degradation and trigger kill switches

---

## Signal Sources

| Signal | Source | Lead Time | Status |
|--------|--------|-----------|--------|
| Wastewater IAV RNA | CDC NWSS via Socrata SODA API | 1–3 weeks | Implemented |
| FluSurv-NET revision history | Delphi Epidata API | Baseline | Implemented |
| ILINet outpatient ILI | Delphi Epidata API | ~1 week | Implemented |
| FluSight ensemble forecasts | CDC FluSight Hub | 0–3 weeks | Planned |
| ED syndromic surveillance | NSSP | ~1 week | Planned |
| Google Trends (flu queries) | pytrends | 0–1 weeks | Planned |
| Antiviral Rx volume | GoodRx / IQVIA | ~1 week | Planned |

Wastewater surveillance is the crown-jewel signal: PMMoV-normalized influenza A RNA (copies IAV per copy PMMoV) detects community spread 1–3 weeks before clinical systems register it.

---

## Architecture

```
flusight-edge/
├── signals/            # One module per data source — each exposes fetch() → SignalResult
│   ├── base.py         # Shared SignalResult dataclass (the signal contract)
│   ├── wastewater.py   # CDC NWSS: wastewater IAV RNA (69 tests)
│   └── delphi_epidata.py  # CMU Delphi: FluSurv-NET + ILINet (29 tests)
├── models/
│   ├── backfill.py     # Revision prediction model — lag → revision ratio (27 tests)
│   ├── nowcast.py      # Elastic net ensemble → bracket probability distribution [planned]
│   └── calibration.py  # EMOS calibration [planned]
├── trading/
│   ├── polymarket.py   # Gamma + CLOB API scraper (52 tests)
│   ├── kelly.py        # Fractional Kelly position sizing [planned]
│   └── executor.py     # CLOB limit order management [planned]
├── monitoring/
│   ├── pnl.py          # P&L tracking [planned]
│   └── alerter.py      # Telegram alerts + SPRT kill switches [planned]
├── config.py           # All constants, thresholds, API endpoints
├── db.py               # SQLite helpers (WAL mode, parameterized queries)
└── schema.sql          # Full database schema
```

### Data Flow

```
CDC NWSS / Delphi APIs
        ↓
  signals/*.fetch()        ← standardized SignalResult dataclass
        ↓
    SQLite (signals table)
        ↓
  models/backfill.train()  ← revision ratio model per lag
  models/nowcast.predict() ← elastic net → point estimate
  models/calibration       ← EMOS → bracket probabilities
        ↓
  trading/kelly.size()     ← fractional Kelly (0.20x)
  trading/executor         ← CLOB limit orders
        ↓
  monitoring/pnl + SPRT    ← P&L tracking, edge monitoring
```

---

## Database Schema

SQLite with WAL mode. Six tables:

| Table | Purpose |
|-------|---------|
| `signals` | Raw signal observations, one row per (signal, epiweek, geography) |
| `revisions` | FluSurv-NET revision history — preliminary rates at each lag |
| `predictions` | Model bracket probabilities per epiweek |
| `markets` | Polymarket market metadata and resolution state |
| `market_prices` | Order book snapshots (bid/ask/last/volume) |
| `trades` | Full audit log of all trades (paper and live) |

---

## Key Findings

Several research findings discovered during development affect the strategy:

1. **FluSurv-NET versioned data unavailable via API** — The Delphi API's `lag`/`issues` parameters for FluSurv return empty. Revision history must be collected prospectively or reconstructed from CDC FluView archives.

2. **Extreme liquidity constraints** — Flu brackets carry ~$10K liquidity per bracket. A $2K order moves the price 13+ cents. Max viable position: $500–$1K per bracket.

3. **No trading fees** — Polymarket flu markets have `feesEnabled=false`.

4. **CDC methodology change (2024–25)** — FluSurv-NET shifted from 100% chart abstraction to variable sampling (1–100%). This may alter historical backfill revision patterns. Under investigation.

5. **UMA oracle risk** — Markets resolve via the UMA Optimistic Oracle. Boundary-case resolutions (rate lands exactly on a bracket edge) can be disputed; capital is locked for ~5 days during the dispute window.

See [`gemini_outputs/edge.md`](gemini_outputs/edge.md) for the full edge durability analysis.

---

## Test Coverage

**177 tests, all passing.**

| Module | Tests | What's covered |
|--------|-------|----------------|
| `signals/wastewater.py` | 69 | Parsing, PMMoV normalization, FIPS filtering, caching, error handling |
| `trading/polymarket.py` | 52 | Gamma API scraper, CLOB order book parsing, bracket regex extraction |
| `signals/delphi_epidata.py` | 29 | FluSurv-NET + ILINet ingestion, revision tracking, edge cases |
| `models/backfill.py` | 27 | Revision ratio statistics, lag interpolation, cold-start fallback, t-distribution widening |

```bash
pytest tests/ -v
# 177 passed in ~2s
```

---

## Quick Start

**Requirements:** Python 3.11+

```bash
# Clone and install
git clone https://github.com/upneja/influenza.git
cd influenza
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Or with uv (faster)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Initialize the database
python -c "from db import init_db; init_db()"

# Run tests
pytest tests/ -v

# Snapshot current Polymarket flu market prices
python -m trading.polymarket

# Analyze backfill revision patterns (uses synthetic data if DB is empty)
python scripts/analyze_revisions.py --synthetic
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Key constants in `config.py` (no restart needed to adjust):

```python
PAPER_TRADE = True              # Default: no real orders placed
KELLY_FRACTION = 0.20           # 1/5 Kelly (conservative)
MIN_EDGE_THRESHOLD = 0.03       # Minimum 3-cent edge to trade
MAX_SINGLE_MARKET_EXPOSURE = 0.15  # Max 15% of capital per market
INITIAL_CAPITAL = 5000          # Starting bankroll (USDC)
```

---

## Current Status

**Phase 1 complete** — all data pipelines, the backfill model, and market scraper are production-ready with full test coverage.

| Component | Status |
|-----------|--------|
| Wastewater signal pipeline | Done |
| Delphi Epidata pipeline | Done |
| FluSurv-NET backfill model | Done |
| Polymarket scraper (Gamma + CLOB) | Done |
| Mathematical model spec (731 lines) | Done |
| Edge durability research report | Done |

**Phase 2 in progress** — nowcast ensemble, EMOS calibration, Kelly sizing, order executor, SPRT monitoring.

---

## Research Documents

| Document | Description |
|----------|-------------|
| [Model Design Spec](docs/research/model_design_spec.md) | Mathematical specification: log-linear backfill model, elastic net ensemble, EMOS calibration, Kelly sizing, SPRT monitoring (731 lines) |
| [API Validation Report](docs/research/api_validation_report.md) | Live testing of all 8 API endpoints |
| [Polymarket Analysis](docs/research/polymarket_analysis_report.md) | Market mechanics, order book depth, fee structure, resolution process |
| [Historical Data Report](docs/research/historical_data_report.md) | Backtesting data availability across all signal sources |
| [Edge Durability Analysis](gemini_outputs/edge.md) | Gemini Deep Research: liquidity constraints, competition risk, CDC methodology change, UMA oracle vulnerabilities |

---

## Domain Context

- **FluSurv-NET** covers 14 states: CA, CO, CT, GA, MD, MI, MN, NM, NY, NC, OH, OR, TN, UT
- Cumulative hospitalization rate = total season hospitalizations per 100,000 population
- Markets resolve on the **final** FluSurv-NET rate, not the initial preliminary print
- CDC publishes FluView reports on Fridays; epiweeks use CDC MMWR numbering (Sunday–Saturday)
- Flu season runs epiweek 40 (~October) through epiweek 20 (~May)
- Epiweek format: `YYYYWW` — e.g., `202605` = Week 5 of 2026

---

## Stack

Python 3.11 · PyTorch · scikit-learn · SQLite · httpx · pytest · CDC NWSS API · Delphi Epidata API · Polymarket CLOB API

---

## License

MIT
