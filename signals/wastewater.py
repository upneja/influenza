"""Wastewater surveillance signal: Influenza A RNA concentrations from CDC NWSS.

Crown-jewel leading indicator -- wastewater viral RNA detects community-level
flu spread 1-3 weeks before clinical surveillance catches it.

Primary data source: CDC NWSS (National Wastewater Surveillance System) on
data.cdc.gov (Socrata SODA API, dataset ymmh-divb). This dataset aggregates
all U.S. wastewater surveillance including WastewaterSCAN (Stanford/Verily)
and state/local health department sites.

Key measurement: PMMoV-normalized Influenza A concentration (copies IAV per
copy PMMoV). PMMoV (Pepper Mild Mottle Virus) normalization accounts for
wastewater dilution variability -- PMMoV is shed at a constant rate by humans,
so IAV/PMMoV gives a per-capita-adjusted viral load.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from epiweeks import Week

from config import (
    FLUSURV_STATE_ABBRS,
    RAW_DATA_DIR,
    WASTEWATER_SCAN_BASE,
)
import db
from signals.base import SignalResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CDC_NWSS_SODA_ENDPOINT = "https://data.cdc.gov/resource/ymmh-divb.json"
CDC_NWSS_DATASET_URL = "https://data.cdc.gov/Public-Health-Surveillance/CDC-Wastewater-Data-for-Influenza-A/ymmh-divb"

# Socrata limits: max 50,000 rows per request without an app token, but we
# filter aggressively by state + pcr_target so this is fine.
SODA_PAGE_SIZE = 50_000
SODA_TIMEOUT = 60  # seconds

# FluSurv-NET states (lowercase for matching against wwtp_jurisdiction)
_FLUSURV_JURISDICTIONS = {s.lower() for s in FLUSURV_STATE_ABBRS}

# PCR target identifier for Influenza A in NWSS data
IAV_PCR_TARGET = "fluav"

# Cache directory
CACHE_DIR = RAW_DATA_DIR / "wastewater"

# Trend thresholds: percent-change per week for classification
TREND_RISING_THRESHOLD = 10.0    # >10% increase = rising
TREND_DECLINING_THRESHOLD = -10.0  # <-10% decrease = declining


# ---------------------------------------------------------------------------
# Epiweek helpers
# ---------------------------------------------------------------------------

def _date_to_epiweek(d: date) -> int:
    """Convert a calendar date to CDC MMWR epiweek integer (e.g. 202604)."""
    w = Week.fromdate(d, system="cdc")
    return w.year * 100 + w.week


def _epiweek_to_date_range(epiweek: int) -> tuple[date, date]:
    """Return (start_date, end_date) for a given MMWR epiweek."""
    year = epiweek // 100
    week_num = epiweek % 100
    w = Week(year, week_num, system="cdc")
    return w.startdate(), w.enddate()


def _current_epiweek() -> int:
    return _date_to_epiweek(date.today())


def _prior_epiweek(epiweek: int, n: int = 1) -> int:
    """Return the epiweek that is n weeks before the given epiweek."""
    year = epiweek // 100
    week_num = epiweek % 100
    w = Week(year, week_num, system="cdc")
    prior = w - n
    return prior.year * 100 + prior.week


# ---------------------------------------------------------------------------
# Data fetching -- CDC NWSS SODA API
# ---------------------------------------------------------------------------

def _build_soda_query(
    start_date: str,
    end_date: str,
    jurisdictions: set[str] | None = None,
    offset: int = 0,
) -> dict[str, str]:
    """Build Socrata SODA query parameters for Influenza A wastewater data.

    Filters:
    - pcr_target = 'fluav'
    - wwtp_jurisdiction in FluSurv-NET states
    - sample_collect_date within range
    - Only keep rows with non-null PMMoV-normalized concentration
    """
    states = jurisdictions or _FLUSURV_JURISDICTIONS
    # Validate all state values against the known set to prevent SODA injection
    _ALL_US_STATES = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    }
    safe_states = sorted(s for s in states if s.upper() in _ALL_US_STATES)
    if not safe_states:
        safe_states = sorted(_FLUSURV_JURISDICTIONS)
    state_list = ", ".join(f"'{s}'" for s in safe_states)

    where_clauses = [
        f"pcr_target = '{IAV_PCR_TARGET}'",
        f"wwtp_jurisdiction in ({state_list})",
        f"sample_collect_date >= '{start_date}'",
        f"sample_collect_date <= '{end_date}'",
        "pcr_target_mic_lin IS NOT NULL",
        "pcr_target_mic_lin > 0",
    ]

    return {
        "$where": " AND ".join(where_clauses),
        "$select": (
            "record_id, sewershed_id, wwtp_jurisdiction, source, "
            "county_fips, counties_served, population_served, "
            "sample_collect_date, sample_matrix, sample_location, "
            "pcr_target, pcr_target_avg_conc, pcr_target_units, "
            "pcr_target_mic_lin, hum_frac_target_mic, hum_frac_mic_conc, "
            "lod_sewage, major_lab_method, date_updated"
        ),
        "$order": "sample_collect_date DESC",
        "$limit": str(SODA_PAGE_SIZE),
        "$offset": str(offset),
    }


def _fetch_nwss_data(
    start_date: str,
    end_date: str,
    jurisdictions: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch Influenza A wastewater data from CDC NWSS SODA API.

    Handles pagination automatically. Returns raw records as dicts.
    """
    all_records: list[dict[str, Any]] = []
    offset = 0

    while True:
        params = _build_soda_query(start_date, end_date, jurisdictions, offset)
        try:
            resp = httpx.get(
                CDC_NWSS_SODA_ENDPOINT,
                params=params,
                timeout=SODA_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
            logger.warning("NWSS SODA API request failed: %s", exc)
            break

        batch = resp.json()
        if not batch:
            break

        all_records.extend(batch)
        logger.info("Fetched %d records (offset=%d)", len(batch), offset)

        if len(batch) < SODA_PAGE_SIZE:
            break
        offset += SODA_PAGE_SIZE

    logger.info(
        "Total NWSS records fetched for %s to %s: %d",
        start_date, end_date, len(all_records),
    )
    return all_records


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------

@dataclass
class SiteSample:
    """A single PMMoV-normalized IAV measurement from one site on one date."""
    sewershed_id: str
    state: str
    collect_date: date
    pmmov_normalized: float  # IAV copies / PMMoV copies (unitless ratio)
    raw_conc: float          # copies/L wastewater
    population_served: int
    source: str


def _parse_records(records: list[dict[str, Any]]) -> list[SiteSample]:
    """Parse raw NWSS JSON records into SiteSample objects."""
    samples: list[SiteSample] = []
    for rec in records:
        try:
            mic_lin = float(rec.get("pcr_target_mic_lin", 0))
            if mic_lin <= 0:
                continue

            raw_conc = float(rec.get("pcr_target_avg_conc", 0))
            collect_str = rec.get("sample_collect_date", "")
            if not collect_str:
                continue
            # Socrata dates come as "YYYY-MM-DDT00:00:00.000" or "YYYY-MM-DD"
            collect_date = datetime.fromisoformat(collect_str.split("T")[0]).date()

            pop = int(float(rec.get("population_served", 0)))

            samples.append(SiteSample(
                sewershed_id=str(rec.get("sewershed_id", "")),
                state=str(rec.get("wwtp_jurisdiction", "")).upper(),
                collect_date=collect_date,
                pmmov_normalized=mic_lin,
                raw_conc=raw_conc,
                population_served=max(pop, 1),
                source=str(rec.get("source", "")),
            ))
        except (ValueError, TypeError) as exc:
            logger.debug("Skipping malformed record: %s (%s)", rec.get("record_id"), exc)
            continue

    return samples


def _filter_to_flusurv_states(samples: list[SiteSample]) -> list[SiteSample]:
    """Keep only samples from FluSurv-NET catchment states."""
    return [s for s in samples if s.state in FLUSURV_STATE_ABBRS]


def _assign_epiweeks(samples: list[SiteSample]) -> dict[int, list[SiteSample]]:
    """Group samples by CDC MMWR epiweek."""
    by_week: dict[int, list[SiteSample]] = {}
    for s in samples:
        ew = _date_to_epiweek(s.collect_date)
        by_week.setdefault(ew, []).append(s)
    return by_week


def geometric_mean(values: list[float]) -> float:
    """Compute geometric mean of positive values.

    Uses log-transform to avoid overflow with large viral concentrations.
    Viral concentrations are log-normally distributed, so geometric mean
    is the appropriate central tendency measure.
    """
    if not values:
        return 0.0
    positive = [v for v in values if v > 0]
    if not positive:
        return 0.0
    log_sum = sum(math.log(v) for v in positive)
    return math.exp(log_sum / len(positive))


def population_weighted_geometric_mean(
    samples: list[SiteSample],
) -> float:
    """Compute population-weighted geometric mean of PMMoV-normalized concentrations.

    Each site's log-concentration is weighted by the population it serves.
    This gives larger treatment plants (more representative of population-level
    transmission) proportionally more influence.
    """
    if not samples:
        return 0.0

    # Deduplicate: if a site has multiple samples in the same week, take the
    # latest one per site
    latest_by_site: dict[str, SiteSample] = {}
    for s in samples:
        key = s.sewershed_id
        if key not in latest_by_site or s.collect_date > latest_by_site[key].collect_date:
            latest_by_site[key] = s

    deduped = list(latest_by_site.values())
    positives = [s for s in deduped if s.pmmov_normalized > 0]
    if not positives:
        return 0.0

    total_pop = sum(s.population_served for s in positives)
    if total_pop == 0:
        return geometric_mean([s.pmmov_normalized for s in positives])

    weighted_log_sum = sum(
        s.population_served * math.log(s.pmmov_normalized)
        for s in positives
    )
    return math.exp(weighted_log_sum / total_pop)


def compute_week_metrics(
    weekly_samples: dict[int, list[SiteSample]],
    target_epiweek: int,
) -> dict[str, Any]:
    """Compute derived wastewater metrics for a given epiweek.

    Returns dict with:
    - wastewater_level: population-weighted geometric mean concentration
    - wastewater_delta: week-over-week percent change
    - wastewater_trend: 3-week rolling average direction
    - n_sites: number of reporting sites
    - n_states: number of reporting states
    """
    current_samples = weekly_samples.get(target_epiweek, [])
    current_level = population_weighted_geometric_mean(current_samples)

    # Week-over-week delta
    prior_ew = _prior_epiweek(target_epiweek, 1)
    prior_samples = weekly_samples.get(prior_ew, [])
    prior_level = population_weighted_geometric_mean(prior_samples)

    if prior_level > 0 and current_level > 0:
        delta_pct = ((current_level - prior_level) / prior_level) * 100.0
    else:
        delta_pct = 0.0

    # 3-week rolling trend
    recent_levels = []
    for offset in range(3):
        ew = _prior_epiweek(target_epiweek, offset)
        ew_samples = weekly_samples.get(ew, [])
        level = population_weighted_geometric_mean(ew_samples)
        if level > 0:
            recent_levels.append(level)

    trend = _classify_trend(recent_levels)

    # Site & state counts
    unique_sites = {s.sewershed_id for s in current_samples}
    unique_states = {s.state for s in current_samples}

    return {
        "wastewater_level": current_level,
        "wastewater_delta": round(delta_pct, 2),
        "wastewater_trend": trend,
        "prior_level": prior_level,
        "n_sites": len(unique_sites),
        "n_states": len(unique_states),
        "states_reporting": sorted(unique_states),
    }


def _classify_trend(levels: list[float]) -> str:
    """Classify 3-week trend from a list of levels [current, week-1, week-2].

    Uses average week-over-week percent change across the window.
    """
    if len(levels) < 2:
        return "insufficient_data"

    changes = []
    for i in range(len(levels) - 1):
        # levels[0] is most recent, levels[-1] is oldest
        newer, older = levels[i], levels[i + 1]
        if older > 0:
            changes.append(((newer - older) / older) * 100.0)

    if not changes:
        return "flat"

    avg_change = sum(changes) / len(changes)

    if avg_change > TREND_RISING_THRESHOLD:
        return "rising"
    elif avg_change < TREND_DECLINING_THRESHOLD:
        return "declining"
    else:
        return "flat"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def _cache_path(epiweek: int) -> Path:
    return CACHE_DIR / f"{epiweek}.json"


def _save_cache(epiweek: int, records: list[dict[str, Any]]) -> None:
    """Cache raw API response to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(epiweek)
    path.write_text(json.dumps(records, indent=2, default=str))
    logger.debug("Cached %d records to %s", len(records), path)


def _load_cache(epiweek: int) -> list[dict[str, Any]] | None:
    """Load cached raw data if available and fresh (< 24 hours old)."""
    path = _cache_path(epiweek)
    if not path.exists():
        return None

    age_hours = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
    if age_hours > 24:
        logger.debug("Cache expired for epiweek %d (%.1f hours old)", epiweek, age_hours)
        return None

    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load cache for epiweek %d: %s", epiweek, exc)
        return None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _store_signals(results: list[SignalResult]) -> None:
    """Persist signal results to SQLite."""
    for r in results:
        try:
            db.insert_signal(
                signal_name=r.signal_name,
                epiweek=r.epiweek,
                value=r.value,
                raw_value=r.raw_value,
                unit=r.unit,
                geography=r.geography,
                fetched_at=r.fetched_at,
                source_url=r.source_url,
                metadata=r.metadata,
            )
        except Exception as exc:
            logger.warning("Failed to persist signal %s: %s", r.signal_name, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch(epiweek: int | None = None) -> list[SignalResult]:
    """Fetch wastewater IAV signal data.

    If epiweek is None, fetches the most recent available week.
    Returns a list of SignalResult with:
    - wastewater_iav_level: geometric mean PMMoV-normalized concentration
    - wastewater_iav_delta: week-over-week percent change
    - wastewater_iav_trend: 3-week trend direction

    Never raises on network errors -- returns empty list and logs warning.
    """
    try:
        return _fetch_impl(epiweek)
    except Exception as exc:
        logger.error("Wastewater fetch failed: %s", exc, exc_info=True)
        return []


def _fetch_impl(epiweek: int | None = None) -> list[SignalResult]:
    """Internal implementation of fetch()."""
    target_ew = epiweek or _current_epiweek()
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    # We need 4 weeks of data: target week + 3 prior weeks for trend
    oldest_ew = _prior_epiweek(target_ew, 3)
    start_date, _ = _epiweek_to_date_range(oldest_ew)
    _, end_date = _epiweek_to_date_range(target_ew)

    # Try cache first (for target epiweek only)
    cached = _load_cache(target_ew)
    if cached is not None:
        logger.info("Using cached data for epiweek %d (%d records)", target_ew, len(cached))
        raw_records = cached
    else:
        raw_records = _fetch_nwss_data(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        if not raw_records:
            logger.warning("No NWSS data returned for epiweeks %d-%d", oldest_ew, target_ew)
            return []
        _save_cache(target_ew, raw_records)

    # Parse, filter, group
    samples = _parse_records(raw_records)
    samples = _filter_to_flusurv_states(samples)

    if not samples:
        logger.warning("No FluSurv-NET state samples after filtering")
        return []

    weekly = _assign_epiweeks(samples)
    metrics = compute_week_metrics(weekly, target_ew)

    if metrics["wastewater_level"] == 0.0 and metrics["n_sites"] == 0:
        logger.warning("No data for target epiweek %d", target_ew)
        return []

    # Build SignalResults
    results: list[SignalResult] = []

    results.append(SignalResult(
        signal_name="wastewater_iav_level",
        epiweek=target_ew,
        value=metrics["wastewater_level"],
        raw_value=metrics["wastewater_level"],
        unit="copies_iav/copies_pmmov",
        geography="flusurv_net",
        fetched_at=now_iso,
        source_url=CDC_NWSS_DATASET_URL,
        metadata={
            "n_sites": metrics["n_sites"],
            "n_states": metrics["n_states"],
            "states_reporting": metrics["states_reporting"],
            "aggregation": "population_weighted_geometric_mean",
            "normalization": "pmmov",
        },
    ))

    results.append(SignalResult(
        signal_name="wastewater_iav_delta",
        epiweek=target_ew,
        value=metrics["wastewater_delta"],
        raw_value=metrics["wastewater_delta"],
        unit="percent_change_wow",
        geography="flusurv_net",
        fetched_at=now_iso,
        source_url=CDC_NWSS_DATASET_URL,
        metadata={
            "current_level": metrics["wastewater_level"],
            "prior_level": metrics["prior_level"],
        },
    ))

    results.append(SignalResult(
        signal_name="wastewater_iav_trend",
        epiweek=target_ew,
        value=_trend_to_numeric(metrics["wastewater_trend"]),
        raw_value=_trend_to_numeric(metrics["wastewater_trend"]),
        unit="trend_score",
        geography="flusurv_net",
        fetched_at=now_iso,
        source_url=CDC_NWSS_DATASET_URL,
        metadata={
            "trend_label": metrics["wastewater_trend"],
            "rising_threshold": TREND_RISING_THRESHOLD,
            "declining_threshold": TREND_DECLINING_THRESHOLD,
        },
    ))

    # Persist to DB
    _store_signals(results)

    logger.info(
        "Wastewater epiweek=%d: level=%.2e, delta=%.1f%%, trend=%s, sites=%d, states=%d",
        target_ew,
        metrics["wastewater_level"],
        metrics["wastewater_delta"],
        metrics["wastewater_trend"],
        metrics["n_sites"],
        metrics["n_states"],
    )

    return results


def _trend_to_numeric(trend: str) -> float:
    """Convert trend label to numeric score for model consumption."""
    return {
        "rising": 1.0,
        "flat": 0.0,
        "declining": -1.0,
        "insufficient_data": 0.0,
    }.get(trend, 0.0)


# ---------------------------------------------------------------------------
# Per-state breakdown (useful for downstream analysis)
# ---------------------------------------------------------------------------

def fetch_by_state(epiweek: int | None = None) -> dict[str, dict[str, Any]]:
    """Fetch per-state wastewater metrics for FluSurv-NET states.

    Returns dict keyed by state abbreviation with metrics for each.
    This is not part of the SignalResult contract but useful for the
    nowcasting model to weight states differently.
    """
    target_ew = epiweek or _current_epiweek()

    oldest_ew = _prior_epiweek(target_ew, 3)
    start_date, _ = _epiweek_to_date_range(oldest_ew)
    _, end_date = _epiweek_to_date_range(target_ew)

    raw_records = _fetch_nwss_data(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )

    samples = _parse_records(raw_records)
    samples = _filter_to_flusurv_states(samples)

    # Group by state, then by epiweek within each state
    by_state: dict[str, dict[int, list[SiteSample]]] = {}
    for s in samples:
        by_state.setdefault(s.state, {}).setdefault(
            _date_to_epiweek(s.collect_date), []
        ).append(s)

    state_metrics: dict[str, dict[str, Any]] = {}
    for state, weekly in by_state.items():
        state_metrics[state] = compute_week_metrics(weekly, target_ew)

    return state_metrics


# ---------------------------------------------------------------------------
# CLI entry point for manual testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    ew = int(sys.argv[1]) if len(sys.argv) > 1 else None
    results = fetch(ew)

    if not results:
        print("No data returned.")
        sys.exit(1)

    for r in results:
        print(f"\n{r.signal_name}:")
        print(f"  epiweek:   {r.epiweek}")
        print(f"  value:     {r.value}")
        print(f"  unit:      {r.unit}")
        print(f"  geography: {r.geography}")
        print(f"  metadata:  {r.metadata}")
