"""Tests for the Delphi Epidata signal module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signals.base import SignalResult
from signals.delphi_epidata import (
    _advance_epiweek,
    _epiweek_range,
    _parse_flusurv_rows,
    _parse_fluview_rows,
    fetch,
    fetch_flusurv_current,
    fetch_flusurv_revisions,
    fetch_ilinet,
)


# ---------------------------------------------------------------------------
# Fixtures: mock API responses
# ---------------------------------------------------------------------------

MOCK_FLUSURV_RESPONSE = {
    "result": 1,
    "message": "success",
    "epidata": [
        {
            "epiweek": 202605,
            "rate_overall": 12.5,
            "rate_age_0": 12.5,
            "issue": 202607,
            "lag": 2,
        },
        {
            "epiweek": 202606,
            "rate_overall": 14.3,
            "rate_age_0": 14.3,
            "issue": 202607,
            "lag": 1,
        },
    ],
}

MOCK_FLUSURV_REVISION_LAG0 = {
    "result": 1,
    "message": "success",
    "epidata": [
        {
            "epiweek": 202605,
            "rate_overall": 10.0,
            "issue": 202605,
            "lag": 0,
        },
    ],
}

MOCK_FLUSURV_REVISION_LAG1 = {
    "result": 1,
    "message": "success",
    "epidata": [
        {
            "epiweek": 202605,
            "rate_overall": 11.2,
            "issue": 202606,
            "lag": 1,
        },
    ],
}

MOCK_FLUSURV_REVISION_LAG2 = {
    "result": 1,
    "message": "success",
    "epidata": [
        {
            "epiweek": 202605,
            "rate_overall": 12.5,
            "issue": 202607,
            "lag": 2,
        },
    ],
}

MOCK_FLUVIEW_RESPONSE = {
    "result": 1,
    "message": "success",
    "epidata": [
        {
            "epiweek": 202605,
            "wili": 3.7,
            "ili": 3.5,
            "num_ili": 25000,
            "num_patients": 675000,
            "num_providers": 2400,
            "region": "nat",
            "issue": 202607,
            "lag": 2,
        },
        {
            "epiweek": 202606,
            "wili": 4.1,
            "ili": 3.9,
            "num_ili": 28000,
            "num_patients": 680000,
            "num_providers": 2350,
            "region": "nat",
            "issue": 202607,
            "lag": 1,
        },
    ],
}

MOCK_EMPTY_RESPONSE = {
    "result": -2,
    "message": "no results",
    "epidata": [],
}

MOCK_ERROR_RESPONSE = {
    "result": -1,
    "message": "server error",
    "epidata": [],
}


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
            signal_name="test",
            epiweek=202605,
            value=1.0,
            raw_value=1.0,
            unit="rate_per_100k",
            geography="national",
            fetched_at="2026-02-18T00:00:00+00:00",
            source_url="https://example.com",
            metadata={"key": "val"},
        )
        assert r.signal_name == "test"
        assert r.epiweek == 202605
        assert isinstance(r.value, float)
        assert isinstance(r.raw_value, float)
        assert isinstance(r.unit, str)
        assert isinstance(r.geography, str)
        assert isinstance(r.fetched_at, str)
        assert isinstance(r.source_url, str)
        assert isinstance(r.metadata, dict)

    def test_signal_result_fields_complete(self):
        """All nine fields from the contract must exist."""
        required = {
            "signal_name", "epiweek", "value", "raw_value",
            "unit", "geography", "fetched_at", "source_url", "metadata",
        }
        from dataclasses import fields

        actual = {f.name for f in fields(SignalResult)}
        assert required == actual


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParsers:
    def test_parse_flusurv_success(self):
        rows = _parse_flusurv_rows(MOCK_FLUSURV_RESPONSE)
        assert len(rows) == 2
        assert rows[0]["epiweek"] == 202605
        assert rows[0]["rate_overall"] == 12.5

    def test_parse_flusurv_empty(self):
        rows = _parse_flusurv_rows(MOCK_EMPTY_RESPONSE)
        assert rows == []

    def test_parse_flusurv_error(self):
        rows = _parse_flusurv_rows(MOCK_ERROR_RESPONSE)
        assert rows == []

    def test_parse_fluview_success(self):
        rows = _parse_fluview_rows(MOCK_FLUVIEW_RESPONSE)
        assert len(rows) == 2
        assert rows[0]["wili"] == 3.7

    def test_parse_fluview_empty(self):
        rows = _parse_fluview_rows(MOCK_EMPTY_RESPONSE)
        assert rows == []


# ---------------------------------------------------------------------------
# Epiweek utility tests
# ---------------------------------------------------------------------------

class TestEpiweekUtils:
    def test_epiweek_range_same_year(self):
        weeks = _epiweek_range(202601, 202605)
        assert weeks == [202601, 202602, 202603, 202604, 202605]

    def test_epiweek_range_cross_year(self):
        weeks = _epiweek_range(202550, 202603)
        assert 202550 in weeks
        assert 202551 in weeks
        assert 202552 in weeks
        # Weeks 202553 may or may not exist (53-week year), but should be
        # included in the range; the API handles non-existent weeks.
        assert 202601 in weeks
        assert 202603 in weeks

    def test_epiweek_range_single(self):
        weeks = _epiweek_range(202605, 202605)
        assert weeks == [202605]

    def test_advance_epiweek_no_wrap(self):
        assert _advance_epiweek(202605, 3) == 202608

    def test_advance_epiweek_year_wrap(self):
        result = _advance_epiweek(202650, 5)
        assert result == 202703

    def test_advance_epiweek_zero(self):
        assert _advance_epiweek(202605, 0) == 202605


# ---------------------------------------------------------------------------
# FluSurv current data tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestFetchFlusurvCurrent:
    @patch("signals.delphi_epidata.insert_signal")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_fetch_current_returns_signal_results(
        self, mock_api, mock_cache, mock_insert
    ):
        mock_api.return_value = MOCK_FLUSURV_RESPONSE
        results = fetch_flusurv_current(epiweek=202605)

        assert len(results) == 2
        assert all(isinstance(r, SignalResult) for r in results)
        assert results[0].signal_name == "flusurv_rate"
        assert results[0].epiweek == 202605
        assert results[0].value == 12.5
        assert results[0].unit == "rate_per_100k"
        assert results[0].geography == "network_all"

    @patch("signals.delphi_epidata.insert_signal")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_fetch_current_stores_to_db(self, mock_api, mock_cache, mock_insert):
        mock_api.return_value = MOCK_FLUSURV_RESPONSE
        fetch_flusurv_current(epiweek=202605)
        assert mock_insert.call_count == 2

    @patch("signals.delphi_epidata.insert_signal")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_fetch_current_empty_response(self, mock_api, mock_cache, mock_insert):
        mock_api.return_value = MOCK_EMPTY_RESPONSE
        results = fetch_flusurv_current(epiweek=202605)
        assert results == []
        mock_insert.assert_not_called()

    @patch("signals.delphi_epidata.insert_signal")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_fetch_current_caches_response(self, mock_api, mock_cache, mock_insert):
        mock_api.return_value = MOCK_FLUSURV_RESPONSE
        fetch_flusurv_current(epiweek=202605)
        mock_cache.assert_called_once()
        args = mock_cache.call_args
        assert "flusurv_current_202605" in args[0][0]


# ---------------------------------------------------------------------------
# FluSurv revision history tests
# ---------------------------------------------------------------------------

class TestFetchFlusurvRevisions:
    @patch("signals.delphi_epidata.insert_revision")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_revision_history_across_lags(self, mock_api, mock_cache, mock_insert):
        """Verify that revisions are fetched at multiple lags and rates increase."""

        def side_effect(epiweeks, location, lag=None, issue=None):
            if lag == 0:
                return MOCK_FLUSURV_REVISION_LAG0
            elif lag == 1:
                return MOCK_FLUSURV_REVISION_LAG1
            elif lag == 2:
                return MOCK_FLUSURV_REVISION_LAG2
            return MOCK_EMPTY_RESPONSE

        mock_api.side_effect = side_effect

        results = fetch_flusurv_revisions(epiweek=202605, max_lag=2)

        # Should have 3 revision observations (lag 0, 1, 2)
        assert len(results) == 3
        assert all(r.signal_name == "flusurv_revision" for r in results)

        # Verify upward revision pattern: 10.0 -> 11.2 -> 12.5
        values = sorted(r.value for r in results)
        assert values == [10.0, 11.2, 12.5]

        # Verify each has the correct lag metadata
        lags = {r.metadata["lag"] for r in results}
        assert lags == {0, 1, 2}

    @patch("signals.delphi_epidata.insert_revision")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_revision_stores_to_revisions_table(
        self, mock_api, mock_cache, mock_insert
    ):
        def side_effect(epiweeks, location, lag=None, issue=None):
            if lag == 0:
                return MOCK_FLUSURV_REVISION_LAG0
            return MOCK_EMPTY_RESPONSE

        mock_api.side_effect = side_effect

        fetch_flusurv_revisions(epiweek=202605, max_lag=0)
        mock_insert.assert_called_once()
        call_kwargs = mock_insert.call_args
        assert call_kwargs[1]["epiweek"] == 202605 or call_kwargs[0][0] == 202605

    @patch("signals.delphi_epidata.insert_revision")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_revision_report_epiweek_from_issue(
        self, mock_api, mock_cache, mock_insert
    ):
        """report_epiweek should come from the API's 'issue' field."""
        mock_api.return_value = MOCK_FLUSURV_REVISION_LAG2
        results = fetch_flusurv_revisions(epiweek=202605, max_lag=2)
        lag2_results = [r for r in results if r.metadata["lag"] == 2]
        assert len(lag2_results) >= 1
        assert lag2_results[0].metadata["report_epiweek"] == 202607


# ---------------------------------------------------------------------------
# ILINet tests
# ---------------------------------------------------------------------------

class TestFetchILINet:
    @patch("signals.delphi_epidata.insert_signal")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_fluview")
    def test_ilinet_returns_signal_results(self, mock_api, mock_cache, mock_insert):
        mock_api.return_value = MOCK_FLUVIEW_RESPONSE
        results = fetch_ilinet(epiweek=202605)

        assert len(results) == 2
        assert all(isinstance(r, SignalResult) for r in results)
        assert results[0].signal_name == "ilinet_ili"
        assert results[0].value == 3.7
        assert results[0].unit == "percent"
        assert results[0].geography == "national"

    @patch("signals.delphi_epidata.insert_signal")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_fluview")
    def test_ilinet_uses_wili_over_ili(self, mock_api, mock_cache, mock_insert):
        """Should prefer weighted ILI (wili) when available."""
        mock_api.return_value = MOCK_FLUVIEW_RESPONSE
        results = fetch_ilinet(epiweek=202605)
        # wili=3.7 vs ili=3.5 — should use 3.7
        assert results[0].value == 3.7

    @patch("signals.delphi_epidata.insert_signal")
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_fluview")
    def test_ilinet_metadata_contains_patient_counts(
        self, mock_api, mock_cache, mock_insert
    ):
        mock_api.return_value = MOCK_FLUVIEW_RESPONSE
        results = fetch_ilinet(epiweek=202605)
        meta = results[0].metadata
        assert "num_ili" in meta
        assert "num_patients" in meta
        assert meta["num_ili"] == 25000


# ---------------------------------------------------------------------------
# Main fetch() function tests
# ---------------------------------------------------------------------------

class TestFetch:
    @patch("signals.delphi_epidata.fetch_ilinet")
    @patch("signals.delphi_epidata.fetch_flusurv_revisions")
    @patch("signals.delphi_epidata.fetch_flusurv_current")
    def test_fetch_combines_all_sources(self, mock_current, mock_rev, mock_ili):
        mock_current.return_value = [
            SignalResult("flusurv_rate", 202605, 12.5, 12.5, "rate_per_100k",
                         "network_all", "2026-01-01", "url", {}),
        ]
        mock_rev.return_value = [
            SignalResult("flusurv_revision", 202605, 10.0, 10.0, "rate_per_100k",
                         "network_all", "2026-01-01", "url", {"lag": 0}),
        ]
        mock_ili.return_value = [
            SignalResult("ilinet_ili", 202605, 3.7, 3.7, "percent",
                         "national", "2026-01-01", "url", {}),
        ]

        results = fetch(epiweek=202605)
        assert len(results) == 3
        names = {r.signal_name for r in results}
        assert names == {"flusurv_rate", "flusurv_revision", "ilinet_ili"}

    @patch("signals.delphi_epidata.fetch_ilinet")
    @patch("signals.delphi_epidata.fetch_flusurv_revisions")
    @patch("signals.delphi_epidata.fetch_flusurv_current")
    def test_fetch_returns_list(self, mock_current, mock_rev, mock_ili):
        mock_current.return_value = []
        mock_rev.return_value = []
        mock_ili.return_value = []
        results = fetch(epiweek=202605)
        assert isinstance(results, list)

    @patch("signals.delphi_epidata.fetch_ilinet")
    @patch("signals.delphi_epidata.fetch_flusurv_revisions")
    @patch("signals.delphi_epidata.fetch_flusurv_current")
    def test_fetch_never_raises_on_error(self, mock_current, mock_rev, mock_ili):
        """The convention says: never raise on network errors, return empty."""
        mock_current.side_effect = Exception("network down")
        mock_rev.side_effect = Exception("timeout")
        mock_ili.side_effect = Exception("DNS failure")

        results = fetch(epiweek=202605)
        assert results == []

    @patch("signals.delphi_epidata.fetch_ilinet")
    @patch("signals.delphi_epidata.fetch_flusurv_revisions")
    @patch("signals.delphi_epidata.fetch_flusurv_current")
    def test_fetch_partial_failure_returns_partial_results(
        self, mock_current, mock_rev, mock_ili
    ):
        mock_current.return_value = [
            SignalResult("flusurv_rate", 202605, 12.5, 12.5, "rate_per_100k",
                         "network_all", "2026-01-01", "url", {}),
        ]
        mock_rev.side_effect = Exception("timeout")
        mock_ili.return_value = [
            SignalResult("ilinet_ili", 202605, 3.7, 3.7, "percent",
                         "national", "2026-01-01", "url", {}),
        ]

        results = fetch(epiweek=202605)
        assert len(results) == 2
        names = {r.signal_name for r in results}
        assert "flusurv_rate" in names
        assert "ilinet_ili" in names


# ---------------------------------------------------------------------------
# Integration-style test with real DB (but mocked HTTP)
# ---------------------------------------------------------------------------

class TestDatabaseIntegration:
    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_flusurv_current_writes_to_signals_table(
        self, mock_api, mock_cache, tmp_db
    ):
        mock_api.return_value = MOCK_FLUSURV_RESPONSE

        results = fetch_flusurv_current(epiweek=202605, db_path=tmp_db)
        assert len(results) == 2

        # Verify data is in the DB
        from db import get_signals

        signals = get_signals("flusurv_rate", db_path=tmp_db)
        assert len(signals) == 2

    @patch("signals.delphi_epidata._cache_response")
    @patch("signals.delphi_epidata._fetch_flusurv")
    def test_revisions_write_to_revisions_table(self, mock_api, mock_cache, tmp_db):
        def side_effect(epiweeks, location, lag=None, issue=None):
            if lag == 0:
                return MOCK_FLUSURV_REVISION_LAG0
            elif lag == 1:
                return MOCK_FLUSURV_REVISION_LAG1
            return MOCK_EMPTY_RESPONSE

        mock_api.side_effect = side_effect

        fetch_flusurv_revisions(epiweek=202605, max_lag=1, db_path=tmp_db)

        from db import get_revisions

        revisions = get_revisions(epiweek=202605, db_path=tmp_db)
        assert len(revisions) == 2
        rates = [r["cumulative_rate"] for r in revisions]
        assert 10.0 in rates
        assert 11.2 in rates
