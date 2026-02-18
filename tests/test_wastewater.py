"""Tests for the wastewater surveillance signal module."""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure project root is on sys.path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signals.base import SignalResult
from signals.wastewater import (
    SiteSample,
    _assign_epiweeks,
    _classify_trend,
    _date_to_epiweek,
    _epiweek_to_date_range,
    _filter_to_flusurv_states,
    _parse_records,
    _prior_epiweek,
    _trend_to_numeric,
    compute_week_metrics,
    fetch,
    geometric_mean,
    population_weighted_geometric_mean,
    CDC_NWSS_SODA_ENDPOINT,
    CDC_NWSS_DATASET_URL,
    IAV_PCR_TARGET,
)


# ---------------------------------------------------------------------------
# Mock data: realistic CDC NWSS SODA API responses
# ---------------------------------------------------------------------------

def _make_nwss_record(
    sewershed_id: str = "100",
    state: str = "ca",
    collect_date: str = "2026-02-01T00:00:00.000",
    mic_lin: float = 0.00003,
    raw_conc: float = 8000.0,
    population: int = 50000,
    source: str = "cdc_verily",
    pcr_target: str = "fluav",
) -> dict:
    return {
        "record_id": f"rec_{sewershed_id}_{collect_date[:10]}",
        "sewershed_id": sewershed_id,
        "wwtp_jurisdiction": state,
        "source": source,
        "county_fips": "06041",
        "counties_served": "Test County",
        "population_served": str(population),
        "sample_collect_date": collect_date,
        "sample_matrix": "raw wastewater",
        "sample_location": "wwtp",
        "pcr_target": pcr_target,
        "pcr_target_avg_conc": str(raw_conc),
        "pcr_target_units": "copies/l wastewater",
        "pcr_target_mic_lin": str(mic_lin),
        "hum_frac_target_mic": "pepper mild mottle virus",
        "hum_frac_mic_conc": str(raw_conc / mic_lin) if mic_lin > 0 else "0",
        "lod_sewage": "1500.0",
        "major_lab_method": "2",
        "date_updated": "2026-02-07T11:00:00.000",
    }


# Sites across different FluSurv-NET states (epiweek 202604 = Jan 25 - Jan 31, 2026)
MOCK_FLUSURV_RECORDS = [
    # California sites
    _make_nwss_record("100", "ca", "2026-01-28T00:00:00.000", 0.00003, 8000, 50000),
    _make_nwss_record("101", "ca", "2026-01-27T00:00:00.000", 0.00005, 12000, 100000),
    # New York site
    _make_nwss_record("200", "ny", "2026-01-29T00:00:00.000", 0.00002, 5000, 200000),
    # Ohio site
    _make_nwss_record("300", "oh", "2026-01-28T00:00:00.000", 0.00004, 10000, 75000),
    # Georgia site
    _make_nwss_record("400", "ga", "2026-01-30T00:00:00.000", 0.00006, 15000, 60000),
]

# Prior week records (epiweek 202603 = Jan 18 - Jan 24, 2026)
MOCK_PRIOR_WEEK_RECORDS = [
    _make_nwss_record("100", "ca", "2026-01-21T00:00:00.000", 0.00002, 5000, 50000),
    _make_nwss_record("101", "ca", "2026-01-20T00:00:00.000", 0.00003, 7000, 100000),
    _make_nwss_record("200", "ny", "2026-01-22T00:00:00.000", 0.000015, 3000, 200000),
    _make_nwss_record("300", "oh", "2026-01-21T00:00:00.000", 0.000025, 6000, 75000),
]

# The target epiweek for tests (Jan 25-31, 2026)
TARGET_EPIWEEK = 202604

# Non-FluSurv-NET state records (should be filtered out)
MOCK_NON_FLUSURV_RECORDS = [
    _make_nwss_record("500", "ia", "2026-01-28T00:00:00.000", 0.00003, 8000, 40000),
    _make_nwss_record("501", "tx", "2026-01-28T00:00:00.000", 0.00004, 10000, 80000),
    _make_nwss_record("502", "fl", "2026-01-28T00:00:00.000", 0.00005, 12000, 90000),
]

# Records with bad/missing data
MOCK_BAD_RECORDS = [
    _make_nwss_record("600", "ca", "2026-01-28T00:00:00.000", 0.0, 0, 50000),  # zero mic_lin
    {  # missing fields
        "record_id": "bad_1",
        "sewershed_id": "601",
        "wwtp_jurisdiction": "ca",
    },
    _make_nwss_record("602", "ca", "", 0.00003, 8000, 50000),  # empty date
]

# All records combined (typical API response for 2 weeks)
MOCK_ALL_RECORDS = MOCK_FLUSURV_RECORDS + MOCK_PRIOR_WEEK_RECORDS + MOCK_NON_FLUSURV_RECORDS


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database for testing."""
    db_path = tmp_path / "test.db"
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_path.read_text())
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# SignalResult contract tests
# ---------------------------------------------------------------------------

class TestSignalResultContract:
    """Verify SignalResult satisfies the contract from signals/CLAUDE.md."""

    def test_signal_result_has_required_fields(self):
        r = SignalResult(
            signal_name="wastewater_iav_level",
            epiweek=202604,
            value=0.00003,
            raw_value=0.00003,
            unit="copies_iav/copies_pmmov",
            geography="flusurv_net",
            fetched_at="2026-02-18T00:00:00Z",
            source_url="https://data.cdc.gov",
            metadata={"n_sites": 5},
        )
        assert r.signal_name == "wastewater_iav_level"
        assert r.epiweek == 202604
        assert isinstance(r.value, float)
        assert isinstance(r.raw_value, float)
        assert isinstance(r.unit, str)
        assert isinstance(r.geography, str)
        assert isinstance(r.fetched_at, str)
        assert isinstance(r.source_url, str)
        assert isinstance(r.metadata, dict)

    def test_signal_result_fields_complete(self):
        """All nine fields from the contract must exist."""
        from dataclasses import fields
        required = {
            "signal_name", "epiweek", "value", "raw_value",
            "unit", "geography", "fetched_at", "source_url", "metadata",
        }
        actual = {f.name for f in fields(SignalResult)}
        assert required == actual

    def test_signal_result_default_metadata(self):
        r = SignalResult(
            signal_name="test", epiweek=TARGET_EPIWEEK, value=1.0,
            raw_value=1.0, unit="test", geography="test",
            fetched_at="2026-01-01", source_url="url",
        )
        assert r.metadata == {}


# ---------------------------------------------------------------------------
# Geometric mean tests
# ---------------------------------------------------------------------------

class TestGeometricMean:
    def test_basic_geometric_mean(self):
        # geomean(2, 8) = 4
        assert abs(geometric_mean([2.0, 8.0]) - 4.0) < 1e-10

    def test_single_value(self):
        assert abs(geometric_mean([5.0]) - 5.0) < 1e-10

    def test_identical_values(self):
        assert abs(geometric_mean([3.0, 3.0, 3.0]) - 3.0) < 1e-10

    def test_empty_returns_zero(self):
        assert geometric_mean([]) == 0.0

    def test_filters_non_positive(self):
        # Should ignore zeros and negatives
        result = geometric_mean([0.0, 4.0, 0.0, 16.0])
        assert abs(result - 8.0) < 1e-10

    def test_all_zeros_returns_zero(self):
        assert geometric_mean([0.0, 0.0, 0.0]) == 0.0

    def test_very_small_concentrations(self):
        # Typical PMMoV-normalized values are tiny (e.g. 0.00003)
        vals = [0.00002, 0.00003, 0.00005]
        result = geometric_mean(vals)
        expected = math.exp(sum(math.log(v) for v in vals) / len(vals))
        assert abs(result - expected) < 1e-15

    def test_large_spread_values(self):
        # Viral concentrations can span orders of magnitude
        vals = [100.0, 10000.0, 1000000.0]
        result = geometric_mean(vals)
        expected = (100.0 * 10000.0 * 1000000.0) ** (1.0 / 3.0)
        assert abs(result - expected) < 0.01


class TestPopulationWeightedGeometricMean:
    def test_basic_weighted_mean(self):
        samples = [
            SiteSample("s1", "CA", date(2026, 1, 28), 0.00002, 5000, 100000, "cdc"),
            SiteSample("s2", "NY", date(2026, 1, 28), 0.00004, 10000, 100000, "cdc"),
        ]
        result = population_weighted_geometric_mean(samples)
        # Equal populations -> should equal unweighted geometric mean
        expected = geometric_mean([0.00002, 0.00004])
        assert abs(result - expected) < 1e-15

    def test_population_weighting_effect(self):
        # Large-population site should dominate
        samples = [
            SiteSample("s1", "CA", date(2026, 1, 28), 0.0001, 5000, 1000000, "cdc"),
            SiteSample("s2", "NY", date(2026, 1, 28), 0.00001, 1000, 1000, "cdc"),
        ]
        result = population_weighted_geometric_mean(samples)
        # Result should be much closer to 0.0001 than to 0.00001
        assert result > 0.00005

    def test_deduplicates_by_site(self):
        # Two samples from same site, different dates -- should keep the latest
        samples = [
            SiteSample("s1", "CA", date(2026, 1, 26), 0.0001, 5000, 50000, "cdc"),
            SiteSample("s1", "CA", date(2026, 1, 28), 0.00005, 3000, 50000, "cdc"),
        ]
        result = population_weighted_geometric_mean(samples)
        # Should use only the Jan 28 sample (0.00005)
        assert abs(result - 0.00005) < 1e-15

    def test_empty_returns_zero(self):
        assert population_weighted_geometric_mean([]) == 0.0


# ---------------------------------------------------------------------------
# Record parsing tests
# ---------------------------------------------------------------------------

class TestParseRecords:
    def test_parse_valid_records(self):
        samples = _parse_records(MOCK_FLUSURV_RECORDS)
        assert len(samples) == 5
        assert all(isinstance(s, SiteSample) for s in samples)

    def test_parsed_fields_correct(self):
        samples = _parse_records([MOCK_FLUSURV_RECORDS[0]])
        s = samples[0]
        assert s.sewershed_id == "100"
        assert s.state == "CA"
        assert s.collect_date == date(2026, 1, 28)
        assert abs(s.pmmov_normalized - 0.00003) < 1e-10
        assert s.raw_conc == 8000.0
        assert s.population_served == 50000

    def test_filters_zero_mic_lin(self):
        samples = _parse_records(MOCK_BAD_RECORDS)
        # Only the records with mic_lin > 0 and valid date should parse
        for s in samples:
            assert s.pmmov_normalized > 0

    def test_handles_missing_fields_gracefully(self):
        # Should not raise, just skip bad records
        samples = _parse_records(MOCK_BAD_RECORDS)
        assert isinstance(samples, list)

    def test_state_uppercased(self):
        # API returns lowercase states, we need uppercase for matching
        samples = _parse_records(MOCK_FLUSURV_RECORDS)
        for s in samples:
            assert s.state == s.state.upper()


# ---------------------------------------------------------------------------
# Geographic filtering tests
# ---------------------------------------------------------------------------

class TestGeographicFiltering:
    def test_keeps_flusurv_states(self):
        all_samples = _parse_records(MOCK_ALL_RECORDS)
        filtered = _filter_to_flusurv_states(all_samples)

        flusurv_states = {"CA", "CO", "CT", "GA", "MD", "MI", "MN", "NM",
                          "NY", "NC", "OH", "OR", "TN", "UT"}
        for s in filtered:
            assert s.state in flusurv_states

    def test_removes_non_flusurv_states(self):
        all_samples = _parse_records(MOCK_ALL_RECORDS)
        filtered = _filter_to_flusurv_states(all_samples)

        states_present = {s.state for s in filtered}
        assert "IA" not in states_present
        assert "TX" not in states_present
        assert "FL" not in states_present

    def test_filtering_reduces_count(self):
        all_samples = _parse_records(MOCK_ALL_RECORDS)
        filtered = _filter_to_flusurv_states(all_samples)
        assert len(filtered) < len(all_samples)

    def test_all_14_flusurv_states_accepted(self):
        flusurv_abbrs = ["CA", "CO", "CT", "GA", "MD", "MI", "MN", "NM",
                         "NY", "NC", "OH", "OR", "TN", "UT"]
        records = [
            _make_nwss_record(f"s{i}", state.lower(), "2026-01-28T00:00:00.000",
                              0.00003, 8000, 50000)
            for i, state in enumerate(flusurv_abbrs)
        ]
        samples = _parse_records(records)
        filtered = _filter_to_flusurv_states(samples)
        assert len(filtered) == 14
        states = {s.state for s in filtered}
        assert states == set(flusurv_abbrs)

    def test_empty_input(self):
        assert _filter_to_flusurv_states([]) == []


# ---------------------------------------------------------------------------
# Epiweek tests
# ---------------------------------------------------------------------------

class TestEpiweekHelpers:
    def test_date_to_epiweek(self):
        # Jan 28, 2026 is in MMWR epiweek 202604 (Jan 25 - Jan 31)
        ew = _date_to_epiweek(date(2026, 1, 28))
        assert ew == 202604

    def test_epiweek_to_date_range(self):
        start, end = _epiweek_to_date_range(202604)
        assert start <= date(2026, 1, 28) <= end
        # MMWR weeks are Sunday-Saturday (7 days)
        assert (end - start).days == 6

    def test_prior_epiweek_same_year(self):
        result = _prior_epiweek(TARGET_EPIWEEK, 1)
        assert result == 202603

    def test_prior_epiweek_cross_year(self):
        result = _prior_epiweek(202601, 1)
        # Should wrap to last week of 2025
        assert result // 100 == 2025
        assert result % 100 >= 50

    def test_prior_epiweek_multiple(self):
        result = _prior_epiweek(TARGET_EPIWEEK, 3)
        assert result == 202601

    def test_assign_epiweeks(self):
        samples = _parse_records(MOCK_ALL_RECORDS)
        filtered = _filter_to_flusurv_states(samples)
        weekly = _assign_epiweeks(filtered)
        assert isinstance(weekly, dict)
        for ew, week_samples in weekly.items():
            assert isinstance(ew, int)
            assert len(week_samples) > 0


# ---------------------------------------------------------------------------
# Trend classification tests
# ---------------------------------------------------------------------------

class TestTrendClassification:
    def test_rising_trend(self):
        # Current is much higher than prior weeks
        levels = [100.0, 50.0, 25.0]  # doubling each week
        assert _classify_trend(levels) == "rising"

    def test_declining_trend(self):
        # Current is much lower than prior weeks
        levels = [25.0, 50.0, 100.0]  # halving each week
        assert _classify_trend(levels) == "declining"

    def test_flat_trend(self):
        levels = [100.0, 99.0, 101.0]  # ~1% change
        assert _classify_trend(levels) == "flat"

    def test_insufficient_data_single(self):
        assert _classify_trend([100.0]) == "insufficient_data"

    def test_insufficient_data_empty(self):
        assert _classify_trend([]) == "insufficient_data"

    def test_two_week_trend(self):
        # Should work with just 2 data points
        levels = [200.0, 100.0]  # 100% increase
        assert _classify_trend(levels) == "rising"


class TestTrendToNumeric:
    def test_rising(self):
        assert _trend_to_numeric("rising") == 1.0

    def test_flat(self):
        assert _trend_to_numeric("flat") == 0.0

    def test_declining(self):
        assert _trend_to_numeric("declining") == -1.0

    def test_insufficient_data(self):
        assert _trend_to_numeric("insufficient_data") == 0.0

    def test_unknown(self):
        assert _trend_to_numeric("bogus") == 0.0


# ---------------------------------------------------------------------------
# Week metrics computation tests
# ---------------------------------------------------------------------------

class TestComputeWeekMetrics:
    def test_basic_metrics(self):
        samples = _parse_records(MOCK_ALL_RECORDS)
        filtered = _filter_to_flusurv_states(samples)
        weekly = _assign_epiweeks(filtered)

        # Find a week that has data
        target_ew = max(weekly.keys())
        metrics = compute_week_metrics(weekly, target_ew)

        assert "wastewater_level" in metrics
        assert "wastewater_delta" in metrics
        assert "wastewater_trend" in metrics
        assert "n_sites" in metrics
        assert "n_states" in metrics
        assert metrics["wastewater_level"] > 0
        assert isinstance(metrics["wastewater_delta"], float)
        assert metrics["wastewater_trend"] in ("rising", "flat", "declining", "insufficient_data")

    def test_no_data_week(self):
        # Use a valid epiweek that simply has no samples in the dict
        metrics = compute_week_metrics({}, 202650)
        assert metrics["wastewater_level"] == 0.0
        assert metrics["n_sites"] == 0

    def test_delta_calculation(self):
        # Build samples with known values for two consecutive weeks
        current_samples = [
            SiteSample("s1", "CA", date(2026, 1, 28), 0.0002, 5000, 100000, "cdc"),
        ]
        prior_samples = [
            SiteSample("s1", "CA", date(2026, 1, 21), 0.0001, 2500, 100000, "cdc"),
        ]
        ew_current = _date_to_epiweek(date(2026, 1, 28))
        ew_prior = _prior_epiweek(ew_current, 1)

        weekly = {
            ew_current: current_samples,
            ew_prior: prior_samples,
        }
        metrics = compute_week_metrics(weekly, ew_current)
        # 0.0002 is 100% higher than 0.0001
        assert abs(metrics["wastewater_delta"] - 100.0) < 0.1


# ---------------------------------------------------------------------------
# Fetch function tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestFetch:
    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_returns_signal_results(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        assert isinstance(results, list)
        assert all(isinstance(r, SignalResult) for r in results)

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_returns_three_signals(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        names = {r.signal_name for r in results}
        assert "wastewater_iav_level" in names
        assert "wastewater_iav_delta" in names
        assert "wastewater_iav_trend" in names

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_level_signal_has_correct_unit(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        level = [r for r in results if r.signal_name == "wastewater_iav_level"][0]
        assert level.unit == "copies_iav/copies_pmmov"
        assert level.geography == "flusurv_net"
        assert level.value > 0

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_delta_signal(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        delta = [r for r in results if r.signal_name == "wastewater_iav_delta"][0]
        assert delta.unit == "percent_change_wow"
        assert isinstance(delta.value, float)

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_trend_signal(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        trend = [r for r in results if r.signal_name == "wastewater_iav_trend"][0]
        assert trend.unit == "trend_score"
        assert trend.value in (-1.0, 0.0, 1.0)
        assert "trend_label" in trend.metadata

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_persists_to_db(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        fetch(epiweek=TARGET_EPIWEEK)
        mock_store.assert_called_once()

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_caches_raw_data(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        fetch(epiweek=TARGET_EPIWEEK)
        mock_save.assert_called_once()

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache")
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_uses_cache_when_available(self, mock_api, mock_save, mock_load, mock_store):
        mock_load.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        # API should NOT be called when cache is available
        mock_api.assert_not_called()
        assert len(results) > 0

    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_never_raises_on_network_error(self, mock_api):
        mock_api.side_effect = Exception("Connection refused")
        results = fetch(epiweek=TARGET_EPIWEEK)
        assert results == []

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_empty_api_response(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = []
        results = fetch(epiweek=TARGET_EPIWEEK)
        assert results == []

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_metadata_includes_site_count(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        level = [r for r in results if r.signal_name == "wastewater_iav_level"][0]
        assert "n_sites" in level.metadata
        assert "n_states" in level.metadata
        assert level.metadata["n_sites"] > 0

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_source_url_set(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        for r in results:
            assert r.source_url == CDC_NWSS_DATASET_URL

    @patch("signals.wastewater._store_signals")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_fetch_epiweek_set_correctly(self, mock_api, mock_save, mock_load, mock_store):
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        for r in results:
            assert r.epiweek == TARGET_EPIWEEK


# ---------------------------------------------------------------------------
# SODA API interaction tests (mocked requests)
# ---------------------------------------------------------------------------

class TestSODAQuery:
    @patch("signals.wastewater.httpx.get")
    def test_api_call_filters_by_pcr_target(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_FLUSURV_RECORDS
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from signals.wastewater import _fetch_nwss_data
        _fetch_nwss_data("2026-01-01", "2026-02-01")

        # Verify the API was called with correct filtering
        call_args = mock_get.call_args
        params = call_args[1].get("params") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["params"]
        where_clause = params.get("$where", "")
        assert "fluav" in where_clause

    @patch("signals.wastewater.httpx.get")
    def test_api_call_filters_by_state(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_FLUSURV_RECORDS
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from signals.wastewater import _fetch_nwss_data
        _fetch_nwss_data("2026-01-01", "2026-02-01")

        call_args = mock_get.call_args
        params = call_args[1].get("params") or call_args[1]["params"]
        where_clause = params.get("$where", "")
        # Should contain FluSurv-NET state abbreviations
        assert "'ca'" in where_clause
        assert "'ny'" in where_clause

    @patch("signals.wastewater.httpx.get")
    def test_api_call_uses_correct_endpoint(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from signals.wastewater import _fetch_nwss_data
        _fetch_nwss_data("2026-01-01", "2026-02-01")

        call_url = mock_get.call_args[0][0]
        assert call_url == CDC_NWSS_SODA_ENDPOINT

    @patch("signals.wastewater.httpx.get")
    def test_api_handles_http_error(self, mock_get):
        mock_get.side_effect = Exception("Connection timeout")

        from signals.wastewater import _fetch_nwss_data
        result = _fetch_nwss_data("2026-01-01", "2026-02-01")
        assert result == []


# ---------------------------------------------------------------------------
# Caching tests
# ---------------------------------------------------------------------------

class TestCaching:
    def test_save_and_load_cache(self, tmp_path):
        from signals.wastewater import _save_cache, _load_cache, CACHE_DIR

        with patch("signals.wastewater.CACHE_DIR", tmp_path):
            from signals import wastewater
            old_cache = wastewater.CACHE_DIR
            wastewater.CACHE_DIR = tmp_path
            try:
                _save_cache(TARGET_EPIWEEK, MOCK_FLUSURV_RECORDS)
                loaded = _load_cache(TARGET_EPIWEEK)
                assert loaded is not None
                assert len(loaded) == len(MOCK_FLUSURV_RECORDS)
            finally:
                wastewater.CACHE_DIR = old_cache

    def test_cache_miss_returns_none(self, tmp_path):
        from signals import wastewater
        old_cache = wastewater.CACHE_DIR
        wastewater.CACHE_DIR = tmp_path
        try:
            result = wastewater._load_cache(999999)
            assert result is None
        finally:
            wastewater.CACHE_DIR = old_cache


# ---------------------------------------------------------------------------
# Integration-style: end-to-end with mocked HTTP
# ---------------------------------------------------------------------------

class TestEndToEnd:
    @patch("signals.wastewater.db.insert_signal")
    @patch("signals.wastewater._load_cache", return_value=None)
    @patch("signals.wastewater._save_cache")
    @patch("signals.wastewater._fetch_nwss_data")
    def test_full_pipeline(self, mock_api, mock_save, mock_load, mock_insert):
        # Provide enough data for 2 weeks so delta can be computed
        mock_api.return_value = MOCK_ALL_RECORDS
        results = fetch(epiweek=TARGET_EPIWEEK)

        # Should get 3 signal results
        assert len(results) == 3
        signal_names = {r.signal_name for r in results}
        assert signal_names == {
            "wastewater_iav_level",
            "wastewater_iav_delta",
            "wastewater_iav_trend",
        }

        # Level should be positive (we have data)
        level = [r for r in results if r.signal_name == "wastewater_iav_level"][0]
        assert level.value > 0
        assert level.metadata["aggregation"] == "population_weighted_geometric_mean"
        assert level.metadata["normalization"] == "pmmov"

        # All results should have consistent epiweek
        for r in results:
            assert r.epiweek == TARGET_EPIWEEK

        # DB should have been called 3 times (once per signal)
        assert mock_insert.call_count == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_site_single_week(self):
        records = [
            _make_nwss_record("100", "ca", "2026-01-28T00:00:00.000", 0.00005, 12000, 50000),
        ]
        samples = _parse_records(records)
        filtered = _filter_to_flusurv_states(samples)
        weekly = _assign_epiweeks(filtered)
        ew = list(weekly.keys())[0]
        metrics = compute_week_metrics(weekly, ew)

        assert metrics["n_sites"] == 1
        assert metrics["n_states"] == 1
        assert abs(metrics["wastewater_level"] - 0.00005) < 1e-15

    def test_all_below_detection_limit(self):
        records = [
            _make_nwss_record("100", "ca", "2026-01-28T00:00:00.000", 0.0, 0, 50000),
            _make_nwss_record("101", "ca", "2026-01-28T00:00:00.000", 0.0, 0, 50000),
        ]
        samples = _parse_records(records)
        # All have mic_lin = 0, so they should be filtered out during parsing
        assert len(samples) == 0

    def test_duplicate_site_same_week(self):
        # Same site, two samples in same week -- should deduplicate
        records = [
            _make_nwss_record("100", "ca", "2026-01-26T00:00:00.000", 0.0001, 5000, 50000),
            _make_nwss_record("100", "ca", "2026-01-28T00:00:00.000", 0.00005, 3000, 50000),
        ]
        samples = _parse_records(records)
        result = population_weighted_geometric_mean(samples)
        # Should use the latest (Jan 28) value only
        assert abs(result - 0.00005) < 1e-15

    def test_mix_of_sources(self):
        records = [
            _make_nwss_record("100", "ca", "2026-01-28T00:00:00.000", 0.00003, 8000, 50000, source="cdc_verily"),
            _make_nwss_record("101", "ny", "2026-01-28T00:00:00.000", 0.00004, 10000, 75000, source="state_lab"),
        ]
        samples = _parse_records(records)
        assert len(samples) == 2
        sources = {s.source for s in samples}
        assert "cdc_verily" in sources
        assert "state_lab" in sources
