"""Delphi Epidata signal module — FluSurv-NET versioned data and ILINet.

Connects to CMU's Delphi Epidata API to pull:
  - FluSurv-NET cumulative hospitalization rates (with revision history)
  - ILINet outpatient ILI percentages

The revision history is the critical asset: by tracking how the cumulative rate
is revised upward over successive reporting weeks, we can train a backfill model
that predicts the final rate from the initial report.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from epiweeks import Week

from config import (
    CURRENT_SEASON,
    DB_PATH,
    DELPHI_EPIDATA_BASE,
    RAW_DATA_DIR,
    SEASON_START_EPIWEEK,
)
from db import insert_revision, insert_signal
from signals.base import SignalResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLUSURV_ENDPOINT = f"{DELPHI_EPIDATA_BASE}/flusurv/"
FLUVIEW_ENDPOINT = f"{DELPHI_EPIDATA_BASE}/fluview/"

CACHE_DIR = RAW_DATA_DIR / "delphi_epidata"

# Default location for national aggregate
FLUSURV_NATIONAL = "network_all"

# Lag range: how many reporting weeks back to look for versioned data.
# lag 0 = initial report, lag 1 = one week later, etc.
MAX_REVISION_LAG = 12

# HTTP timeout for Delphi API calls
REQUEST_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Load the Delphi Epidata API key from environment (optional)."""
    return os.environ.get("DELPHI_EPIDATA_KEY")


def _epiweek_range(start: int, end: int) -> list[int]:
    """Generate a list of epiweeks from start to end (inclusive).

    Handles the year boundary correctly — CDC epiweeks go up to 52 or 53
    then wrap to 01 of the next year.
    """
    weeks: list[int] = []
    year = start // 100
    week = start % 100

    end_year = end // 100
    end_week = end % 100

    while (year, week) <= (end_year, end_week):
        weeks.append(year * 100 + week)
        week += 1
        # CDC weeks: most years have 52, some have 53.
        # Use 53 as the upper bound; the API will simply return no data for
        # non-existent week 53.
        if week > 53:
            week = 1
            year += 1

    return weeks


def _current_epiweek() -> int:
    """Estimate the current CDC MMWR epiweek from today's date.

    This is an approximation — for production precision, use the epiweeks
    library or CDC's own week lookup. The MMWR week starts on Sunday.
    """
    now = datetime.now(timezone.utc)
    # ISO week is close to CDC MMWR week (both start on Monday/Sunday).
    # Good enough for range generation; the API is tolerant.
    iso_year, iso_week, _ = now.isocalendar()
    return iso_year * 100 + iso_week


def _season_epiweeks(end_epiweek: int | None = None) -> str:
    """Build the epiweek range string for the current season.

    Returns a string like "202540-202610" for the Delphi API.
    """
    end = end_epiweek or _current_epiweek()
    return f"{SEASON_START_EPIWEEK}-{end}"


def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _cache_response(filename: str, data: dict) -> Path:
    """Write a raw API response to the cache directory as JSON."""
    path = _ensure_cache_dir() / filename
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    key = _get_api_key()
    if key:
        headers["Epidata-Auth"] = key
    return headers


def _build_params(base_params: dict) -> dict:
    """Attach the API key as the `auth` query parameter if available."""
    key = _get_api_key()
    if key:
        base_params["auth"] = key
    return base_params


# ---------------------------------------------------------------------------
# API callers
# ---------------------------------------------------------------------------

def _fetch_flusurv(
    epiweeks: str,
    location: str = FLUSURV_NATIONAL,
    issue: int | None = None,
    lag: int | None = None,
) -> dict:
    """Call the Delphi Epidata /flusurv/ endpoint.

    Args:
        epiweeks: Epiweek range string, e.g. "202540-202610" or single "202605".
        location: FluSurv-NET location code — "network_all" for national.
        issue: If set, retrieve data as it was published on this epiweek (versioned).
        lag: If set, retrieve data at this specific reporting lag.

    Returns:
        Raw JSON response dict from the API.
    """
    params: dict = {
        "epiweeks": epiweeks,
        "locations": location,
    }
    if issue is not None:
        params["issues"] = str(issue)
    if lag is not None:
        params["lag"] = str(lag)
    params = _build_params(params)

    try:
        resp = httpx.get(
            FLUSURV_ENDPOINT,
            params=params,
            headers=_build_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Delphi FluSurv HTTP error %s: %s", exc.response.status_code, exc)
        return {"result": -1, "message": str(exc), "epidata": []}
    except httpx.RequestError as exc:
        logger.warning("Delphi FluSurv request error: %s", exc)
        return {"result": -1, "message": str(exc), "epidata": []}


def _fetch_fluview(
    epiweeks: str,
    regions: str = "nat",
    issue: int | None = None,
    lag: int | None = None,
) -> dict:
    """Call the Delphi Epidata /fluview/ endpoint for ILINet data.

    Args:
        epiweeks: Epiweek range string.
        regions: ILINet region — "nat" for national.
        issue: Versioned retrieval epiweek.
        lag: Reporting lag.

    Returns:
        Raw JSON response dict from the API.
    """
    params: dict = {
        "epiweeks": epiweeks,
        "regions": regions,
    }
    if issue is not None:
        params["issues"] = str(issue)
    if lag is not None:
        params["lag"] = str(lag)
    params = _build_params(params)

    try:
        resp = httpx.get(
            FLUVIEW_ENDPOINT,
            params=params,
            headers=_build_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Delphi FluView HTTP error %s: %s", exc.response.status_code, exc)
        return {"result": -1, "message": str(exc), "epidata": []}
    except httpx.RequestError as exc:
        logger.warning("Delphi FluView request error: %s", exc)
        return {"result": -1, "message": str(exc), "epidata": []}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_flusurv_rows(data: dict) -> list[dict]:
    """Extract rows from a FluSurv API response.

    The Delphi API returns {"result": 1, "epidata": [...]} on success.
    result == 1 means data found; result == -2 means no results.
    """
    result_code = data.get("result", -1)
    if result_code not in (1,):
        msg = data.get("message", "unknown error")
        if result_code != -2:  # -2 is "no results" which is expected
            logger.warning("FluSurv API result=%s: %s", result_code, msg)
        return []
    return data.get("epidata", [])


def _parse_fluview_rows(data: dict) -> list[dict]:
    """Extract rows from a FluView (ILINet) API response."""
    result_code = data.get("result", -1)
    if result_code not in (1,):
        msg = data.get("message", "unknown error")
        if result_code != -2:
            logger.warning("FluView API result=%s: %s", result_code, msg)
        return []
    return data.get("epidata", [])


# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------

def fetch_flusurv_current(
    epiweek: int | None = None,
    location: str = FLUSURV_NATIONAL,
    db_path: Path = DB_PATH,
) -> list[SignalResult]:
    """Fetch the most recent (latest-issue) FluSurv-NET data for the season.

    This gives the current best-known cumulative hospitalization rates.
    """
    epiweek_range = str(epiweek) if epiweek else _season_epiweeks()
    fetched_at = _now_iso()
    source_url = FLUSURV_ENDPOINT

    raw = _fetch_flusurv(epiweeks=epiweek_range, location=location)
    _cache_response(f"flusurv_current_{epiweek or 'season'}.json", raw)

    rows = _parse_flusurv_rows(raw)
    results: list[SignalResult] = []

    for row in rows:
        ew = int(row.get("epiweek", 0))

        # Try multiple fields for the cumulative rate
        rate = 0.0
        for field in ("rate_overall", "rate_age_0", "rate"):
            if field in row and row[field] is not None:
                rate = float(row[field])
                break

        result = SignalResult(
            signal_name="flusurv_rate",
            epiweek=ew,
            value=rate,
            raw_value=rate,
            unit="rate_per_100k",
            geography=location,
            fetched_at=fetched_at,
            source_url=source_url,
            metadata={
                "issue": row.get("issue"),
                "lag": row.get("lag"),
                "season": CURRENT_SEASON,
                "location": location,
            },
        )
        results.append(result)

        insert_signal(
            signal_name=result.signal_name,
            epiweek=result.epiweek,
            value=result.value,
            raw_value=result.raw_value,
            unit=result.unit,
            geography=result.geography,
            fetched_at=result.fetched_at,
            source_url=result.source_url,
            metadata=result.metadata,
            db_path=db_path,
        )

    logger.info("FluSurv current: fetched %d rows", len(results))
    return results


def fetch_flusurv_revisions(
    epiweek: int | None = None,
    location: str = FLUSURV_NATIONAL,
    max_lag: int = MAX_REVISION_LAG,
    db_path: Path = DB_PATH,
) -> list[SignalResult]:
    """Fetch versioned FluSurv-NET data to build revision history.

    For each epiweek in the season, queries the API at each lag (0..max_lag)
    to see how the reported rate changed over time. This is the data that
    drives the backfill prediction model.

    If a single epiweek is specified, only fetch revisions for that week.
    Otherwise, fetch for all weeks in the current season.
    """
    fetched_at = _now_iso()
    source_url = FLUSURV_ENDPOINT
    results: list[SignalResult] = []

    if epiweek:
        target_weeks = [epiweek]
    else:
        end_ew = _current_epiweek()
        target_weeks = _epiweek_range(SEASON_START_EPIWEEK, end_ew)

    all_revision_data: list[dict] = []

    for lag in range(0, max_lag + 1):
        epiweek_str = (
            str(epiweek)
            if epiweek
            else f"{SEASON_START_EPIWEEK}-{target_weeks[-1]}"
        )
        raw = _fetch_flusurv(epiweeks=epiweek_str, location=location, lag=lag)

        rows = _parse_flusurv_rows(raw)
        for row in rows:
            row["_queried_lag"] = lag
            all_revision_data.append(row)

    _cache_response(f"flusurv_revisions_{epiweek or 'season'}.json", all_revision_data)

    for row in all_revision_data:
        ew = int(row.get("epiweek", 0))
        lag = int(row.get("_queried_lag", row.get("lag", 0)))

        rate = 0.0
        for field in ("rate_overall", "rate_age_0", "rate"):
            if field in row and row[field] is not None:
                rate = float(row[field])
                break

        # Compute report_epiweek (the epiweek when this version was published)
        # report_epiweek = epiweek + lag
        issue = row.get("issue")
        if issue is not None:
            report_ew = int(issue)
        else:
            report_ew = _advance_epiweek(ew, lag)

        # Weekly rate may or may not be present
        weekly_rate: float | None = None
        for wfield in ("rate_overall_weekly", "weekly_rate"):
            if wfield in row and row[wfield] is not None:
                weekly_rate = float(row[wfield])
                break

        result = SignalResult(
            signal_name="flusurv_revision",
            epiweek=ew,
            value=rate,
            raw_value=rate,
            unit="rate_per_100k",
            geography=location,
            fetched_at=fetched_at,
            source_url=source_url,
            metadata={
                "lag": lag,
                "report_epiweek": report_ew,
                "issue": issue,
                "season": CURRENT_SEASON,
                "location": location,
            },
        )
        results.append(result)

        # Store in revisions table for the backfill model
        insert_revision(
            epiweek=ew,
            report_epiweek=report_ew,
            lag=lag,
            cumulative_rate=rate,
            weekly_rate=weekly_rate,
            geography=location,
            fetched_at=fetched_at,
            db_path=db_path,
        )

    logger.info("FluSurv revisions: fetched %d versioned observations", len(results))
    return results


def fetch_ilinet(
    epiweek: int | None = None,
    region: str = "nat",
    db_path: Path = DB_PATH,
) -> list[SignalResult]:
    """Fetch ILINet outpatient ILI percentage from the /fluview/ endpoint.

    This is Signal 7 in the pipeline — the percentage of outpatient visits
    that are for influenza-like illness.
    """
    epiweek_range = str(epiweek) if epiweek else _season_epiweeks()
    fetched_at = _now_iso()
    source_url = FLUVIEW_ENDPOINT

    raw = _fetch_fluview(epiweeks=epiweek_range, regions=region)
    _cache_response(f"ilinet_{epiweek or 'season'}.json", raw)

    rows = _parse_fluview_rows(raw)
    results: list[SignalResult] = []

    for row in rows:
        ew = int(row.get("epiweek", 0))

        # ILINet returns weighted ILI (wili) and unweighted ILI (ili)
        wili = row.get("wili")
        ili = row.get("ili")
        ili_value = float(wili if wili is not None else (ili or 0))

        # Total patients and ILI patients for context
        num_ili = row.get("num_ili", 0)
        num_patients = row.get("num_patients", 0)
        num_providers = row.get("num_providers", 0)

        result = SignalResult(
            signal_name="ilinet_ili",
            epiweek=ew,
            value=ili_value,
            raw_value=ili_value,
            unit="percent",
            geography="national" if region == "nat" else region,
            fetched_at=fetched_at,
            source_url=source_url,
            metadata={
                "wili": wili,
                "ili": ili,
                "num_ili": num_ili,
                "num_patients": num_patients,
                "num_providers": num_providers,
                "region": region,
                "issue": row.get("issue"),
                "lag": row.get("lag"),
            },
        )
        results.append(result)

        insert_signal(
            signal_name=result.signal_name,
            epiweek=result.epiweek,
            value=result.value,
            raw_value=result.raw_value,
            unit=result.unit,
            geography=result.geography,
            fetched_at=result.fetched_at,
            source_url=result.source_url,
            metadata=result.metadata,
            db_path=db_path,
        )

    logger.info("ILINet: fetched %d rows", len(results))
    return results


# ---------------------------------------------------------------------------
# Epiweek arithmetic
# ---------------------------------------------------------------------------

def _advance_epiweek(epiweek: int, weeks: int) -> int:
    """Advance an epiweek by a given number of weeks.

    Uses the epiweeks library for correct handling of 53-week years.
    """
    year = epiweek // 100
    week_num = epiweek % 100
    w = Week(year, week_num, system="cdc")
    advanced = w + weeks
    return advanced.year * 100 + advanced.week


# ---------------------------------------------------------------------------
# Main entry point: fetch()
# ---------------------------------------------------------------------------

def fetch(epiweek: int | None = None) -> list[SignalResult]:
    """Fetch all Delphi Epidata signals for the given epiweek (or current season).

    Returns a combined list of SignalResult from:
      1. FluSurv-NET current rates
      2. FluSurv-NET revision history
      3. ILINet ILI percentages

    On any network error, returns whatever partial results were obtained
    (never raises).
    """
    results: list[SignalResult] = []

    # 1. FluSurv-NET current
    try:
        flusurv = fetch_flusurv_current(epiweek=epiweek)
        results.extend(flusurv)
    except Exception:
        logger.exception("Failed to fetch FluSurv-NET current data")

    # 2. FluSurv-NET revisions
    try:
        revisions = fetch_flusurv_revisions(epiweek=epiweek)
        results.extend(revisions)
    except Exception:
        logger.exception("Failed to fetch FluSurv-NET revision history")

    # 3. ILINet
    try:
        ilinet = fetch_ilinet(epiweek=epiweek)
        results.extend(ilinet)
    except Exception:
        logger.exception("Failed to fetch ILINet data")

    logger.info(
        "Delphi Epidata fetch complete: %d total signals (%s)",
        len(results),
        ", ".join(
            f"{name}={count}"
            for name, count in _count_by_signal(results).items()
        ),
    )
    return results


def _count_by_signal(results: list[SignalResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.signal_name] = counts.get(r.signal_name, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from db import init_db

    init_db()
    results = fetch()
    for r in results:
        print(f"  {r.signal_name} | ew={r.epiweek} | val={r.value:.2f} | geo={r.geography}")
    print(f"\nTotal: {len(results)} signal observations")
