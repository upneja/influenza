# Signals Directory

## Convention
Every signal module must expose:
```python
from dataclasses import dataclass
from datetime import date

@dataclass
class SignalResult:
    signal_name: str        # e.g. "wastewater_iav"
    epiweek: int            # CDC MMWR epiweek number (e.g. 202605)
    value: float            # Normalized signal value
    raw_value: float        # Original value from source
    unit: str               # e.g. "copies/mL/PMMoV", "percent", "rate_per_100k"
    geography: str          # "national", state FIPS, or site ID
    fetched_at: str         # ISO timestamp of when we pulled this
    source_url: str         # URL we pulled from
    metadata: dict          # Any extra info (version, revision_number, etc.)

def fetch(epiweek: int | None = None) -> list[SignalResult]:
    """Fetch signal data. If epiweek is None, fetch most recent available."""
    ...
```

## Rules
- Each module handles its own HTTP requests and parsing
- Cache raw API responses to `data/raw/{signal_name}/{epiweek}.json`
- Store processed results in SQLite via `db.py`
- Never raise on network errors — return empty list and log warning
- All fetches should be idempotent (safe to re-run)

## FluSurv-NET Geography Filter
When a signal provides geographic granularity, filter to these 14 states:
CA, CO, CT, GA, MD, MI, MN, NM, NY, NC, OH, OR, TN, UT
Use FIPS codes from `config.py` for matching.
