# FluSight Edge

Quantitative trading system for [Polymarket](https://polymarket.com/) flu hospitalization bracket markets. Fuses 7 real-time epidemiological surveillance signals to predict where the CDC's final FluSurv-NET cumulative hospitalization rate will land relative to market-implied brackets.

## The Edge

Polymarket runs weekly prediction markets on U.S. influenza hospitalization rates (e.g., "Will the cumulative rate be 60-70 per 100K?"). These markets resolve based on **final** CDC FluSurv-NET data, but traders price them using **preliminary** numbers that are systematically revised upward by 15-30% as lagging hospitals report over subsequent weeks.

We exploit this by:
1. **Backfill arbitrage** -- Modeling FluSurv-NET revision patterns to predict final rates from preliminary reports
2. **Multi-signal fusion** -- Combining 7 leading indicators that move 1-3 weeks ahead of hospitalization data
3. **Calibrated bracket probabilities** -- Converting point estimates into properly calibrated probability distributions over market brackets
4. **Fractional Kelly sizing** -- Position sizing at 0.20x Kelly to account for model uncertainty

## Signals

| Signal | Source | Lead Time | Module |
|--------|--------|-----------|--------|
| Wastewater IAV RNA | CDC NWSS (SODA API) | 1-2 weeks | `signals/wastewater.py` |
| FluSurv-NET rates | Delphi Epidata API | Baseline | `signals/delphi_epidata.py` |
| ILINet outpatient ILI | Delphi Epidata API | ~1 week | `signals/delphi_epidata.py` |
| FluSight ensemble forecasts | CDC FluSight Hub | 0-3 weeks | Planned |
| ED syndromic surveillance | NSSP | ~1 week | Planned |
| Google Trends (flu queries) | pytrends | 0-1 weeks | Planned |
| Antiviral Rx volume | GoodRx/IQVIA | ~1 week | Planned |

## Architecture

```
signals/            Data ingestion (one module per source, each exposes fetch() -> SignalResult)
models/             Prediction (backfill revision model, nowcast ensemble, EMOS calibration)
trading/            Market interaction (Polymarket scraper, Kelly sizing, order execution)
monitoring/         Operational (P&L tracking, SPRT edge monitoring, alerting)
config.py           All constants, thresholds, API endpoints
db.py               SQLite helpers (WAL mode, parameterized queries)
schema.sql          Database schema
```

## Quick Start

```bash
# Clone and set up
git clone https://github.com/upneja/influenza.git
cd influenza
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Or with uv
uv venv && source .venv/bin/activate
uv pip install httpx requests pandas numpy scikit-learn scipy epiweeks matplotlib pytest

# Initialize database
python -c "from db import init_db; init_db()"

# Run tests (177 passing)
pytest tests/ -v

# Analyze revision patterns (with synthetic data)
python scripts/analyze_revisions.py --synthetic

# Snapshot current Polymarket flu prices
python -m trading.polymarket
```

## Configuration

Copy `.env.example` to `.env` and add any API keys:

```bash
cp .env.example .env
```

Key settings in `config.py`:
- `PAPER_TRADE = True` (default) -- no real orders placed
- `KELLY_FRACTION = 0.20` -- conservative 1/5 Kelly sizing
- `MIN_EDGE_THRESHOLD = 0.03` -- minimum 3-cent edge to trade
- `MAX_SINGLE_MARKET_EXPOSURE = 0.15` -- max 15% of capital per market
- `INITIAL_CAPITAL = 5000` -- starting bankroll in USDC

## Current Status

**Phase 1: Complete** (177 tests passing)

| Component | Status | Tests |
|-----------|--------|-------|
| Delphi Epidata pipeline | Done | 29 |
| Wastewater pipeline (CDC NWSS) | Done | 69 |
| Backfill revision model | Done | 27 |
| Polymarket scraper (Gamma + CLOB) | Done | 52 |
| Mathematical model spec | Done | [731 lines](docs/research/model_design_spec.md) |
| Research reports | Done | [4 reports](docs/research/) |

**Phase 2: Not started**

- Nowcast ensemble (elastic net, 21 features)
- EMOS bracket probability calibration
- Kelly bet sizing
- CLOB order executor
- SPRT edge monitoring + kill switches
- Pipeline orchestrator

## Key Findings

Several research findings impact the strategy:

1. **FluSurv-NET versioned data unavailable** -- The Delphi API's `lag`/`issues` parameters for FluSurv return empty. We cannot retrieve historical revision data programmatically. Workarounds: collect prospectively, reconstruct from CDC archives, or use ILINet backfill as proxy.

2. **Extreme liquidity constraints** -- Polymarket flu brackets have ~$10K liquidity per bracket. A $2K order moves the price 13+ cents. Max viable position: $500-1K per bracket.

3. **No trading fees** -- Polymarket flu markets have `feesEnabled=false`.

4. **CDC methodology change** -- Starting 2024-25, FluSurv-NET shifted from 100% chart abstraction to variable sampling (1-100%). This may alter the backfill revision patterns that the strategy depends on. Under investigation.

See [`gemini_outputs/edge.md`](gemini_outputs/edge.md) for the full Gemini Deep Research analysis on edge durability.

## Research Documents

| Document | Description |
|----------|-------------|
| [Model Design Spec](docs/research/model_design_spec.md) | Mathematical specification: elastic net, EMOS calibration, Kelly sizing, SPRT monitoring |
| [API Validation](docs/research/api_validation_report.md) | Testing all 8 API endpoints with live data |
| [Polymarket Analysis](docs/research/polymarket_analysis_report.md) | Market mechanics, order book depth, fee structure, resolution process |
| [Historical Data](docs/research/historical_data_report.md) | Backtesting data availability across all signal sources |

## Domain Context

- **FluSurv-NET** covers 14 states: CA, CO, CT, GA, MD, MI, MN, NM, NY, NC, OH, OR, TN, UT
- Cumulative hospitalization rate = total season hospitalizations per 100,000 population
- CDC publishes FluView reports on Fridays; markets resolve on final reported rate
- Epiweeks use CDC MMWR numbering (Sunday-Saturday), e.g., `202605` = Week 5 of 2026
- Flu season runs from epiweek 40 (~October) through epiweek 20 (~May)

## License

Private. Not for redistribution.
