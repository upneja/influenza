"""Centralized configuration for FluSight Edge."""

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "flusight.db"

# FluSurv-NET participating states (14 states)
FLUSURV_STATES = {
    "CA": "06", "CO": "08", "CT": "09", "GA": "13",
    "MD": "24", "MI": "26", "MN": "27", "NM": "35",
    "NY": "36", "NC": "37", "OH": "39", "OR": "41",
    "TN": "47", "UT": "49",
}
FLUSURV_FIPS = set(FLUSURV_STATES.values())
FLUSURV_STATE_ABBRS = set(FLUSURV_STATES.keys())

# Current season
CURRENT_SEASON = 2025  # 2025-2026 season (identified by start year)
SEASON_START_EPIWEEK = 202540  # Epiweek 40 of 2025

# Market brackets (typical Polymarket flu hospitalization brackets)
DEFAULT_BRACKETS = ["<30", "30-40", "40-50", "50-60", "60-70", "70+"]

# Trading parameters
KELLY_FRACTION = 0.20
MIN_EDGE_THRESHOLD = 0.03  # 3 cents minimum
MAX_SINGLE_MARKET_EXPOSURE = 0.15  # 15% of capital
MAX_DAILY_TRADES = 4
ORDER_STALE_HOURS = 2
PAPER_TRADE = True  # Set to False for live trading

# Capital
INITIAL_CAPITAL = 5000  # USDC

# API endpoints
DELPHI_EPIDATA_BASE = "https://api.delphi.cmu.edu/epidata"
WASTEWATER_SCAN_BASE = "https://data.wastewaterscan.org"
CDC_NWSS_BASE = "https://www.cdc.gov/nwss"
POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_API = "https://clob.polymarket.com"

# Signal update schedule (cron-style descriptions)
SIGNAL_SCHEDULE = {
    "delphi_epidata": "Friday after CDC FluView release",
    "wastewater": "Weekly, typically Friday",
    "ed_syndromic": "Varies by state, Tue-Thu",
    "google_trends": "Daily",
    "antiviral_rx": "Weekly",
    "flusight": "Weekly, Wednesday",
    "ilinet": "Friday with FluView",
}
