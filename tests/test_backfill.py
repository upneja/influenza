"""Tests for the backfill revision prediction model."""

import math
import sqlite3
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import init_db, get_connection
from models import backfill
from models.backfill import (
    BackfillModel,
    _epiweek_to_season,
    _epiweek_to_week_of_season,
    _compute_revision_ratios,
    _fallback_predict,
    train,
    predict,
    get_revision_summary,
    generate_synthetic_revisions,
)


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def populated_db(tmp_db) -> Path:
    """Create a temporary database populated with synthetic revision data."""
    generate_synthetic_revisions(n_seasons=3, weeks_per_season=25, max_lag=15, db_path=tmp_db)
    return tmp_db


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------

class TestEpiweekConversions:
    def test_epiweek_to_season_fall(self):
        assert _epiweek_to_season(202540) == 2025
        assert _epiweek_to_season(202552) == 2025

    def test_epiweek_to_season_spring(self):
        assert _epiweek_to_season(202601) == 2025
        assert _epiweek_to_season(202620) == 2025
        assert _epiweek_to_season(202639) == 2025

    def test_epiweek_to_season_boundary(self):
        # Week 40 starts a new season
        assert _epiweek_to_season(202640) == 2026

    def test_week_of_season_fall(self):
        assert _epiweek_to_week_of_season(202540) == 1
        assert _epiweek_to_week_of_season(202541) == 2
        assert _epiweek_to_week_of_season(202552) == 13

    def test_week_of_season_spring(self):
        assert _epiweek_to_week_of_season(202601) == 14
        assert _epiweek_to_week_of_season(202610) == 23


class TestComputeRevisionRatios:
    def test_simple_ratios(self):
        data = {
            202601: {0: 10.0, 1: 11.0, 5: 12.0, 10: 13.0},
            202602: {0: 20.0, 1: 22.0, 5: 24.0, 10: 25.0},
        }
        ratios = _compute_revision_ratios(data)
        # At lag 0: final (lag 10) / lag 0
        assert 0 in ratios
        assert len(ratios[0]) == 2
        assert ratios[0][0] == pytest.approx(13.0 / 10.0)
        assert ratios[0][1] == pytest.approx(25.0 / 20.0)

    def test_zero_rate_excluded(self):
        data = {202601: {0: 0.0, 5: 10.0}}
        ratios = _compute_revision_ratios(data)
        assert 0 not in ratios  # rate=0 at lag 0 should be excluded

    def test_single_lag_excluded(self):
        data = {202601: {5: 10.0}}
        ratios = _compute_revision_ratios(data)
        # Only one lag = no ratio to compute (can't compare final to itself)
        assert len(ratios) == 0


class TestFallbackPredict:
    def test_lag_zero_higher_revision(self):
        result = _fallback_predict(40.0, lag=0)
        assert result["revision_factor"] > 1.0
        assert result["predicted_final_rate"] > 40.0

    def test_higher_lag_lower_revision(self):
        r0 = _fallback_predict(40.0, lag=0)
        r5 = _fallback_predict(40.0, lag=5)
        r10 = _fallback_predict(40.0, lag=10)
        # More lag = less remaining revision
        assert r0["revision_factor"] > r5["revision_factor"]
        assert r5["revision_factor"] > r10["revision_factor"]

    def test_ci_contains_point_estimate(self):
        result = _fallback_predict(40.0, lag=2)
        assert result["ci_lower"] <= result["predicted_final_rate"]
        assert result["ci_upper"] >= result["predicted_final_rate"]


# ---------------------------------------------------------------------------
# Integration tests: train and predict
# ---------------------------------------------------------------------------

class TestTrainEmpty:
    def test_train_no_data(self, tmp_db):
        model, metrics = train(db_path=tmp_db)
        assert metrics["n_epiweeks"] == 0
        assert metrics["n_seasons"] == 0
        assert "warning" in metrics

    def test_predict_after_empty_train(self, tmp_db):
        model, _ = train(db_path=tmp_db)
        result = predict(epiweek=202601, current_rate=40.0, lag=0, model=model)
        # Should use fallback
        assert result["n_historical"] == 0
        assert result["predicted_final_rate"] > 40.0


class TestTrainWithSyntheticData:
    def test_train_returns_metrics(self, populated_db):
        model, metrics = train(db_path=populated_db)
        assert metrics["n_epiweeks"] > 0
        assert metrics["n_seasons"] == 3
        assert len(metrics["lag_stats"]) > 0
        assert metrics["overall_mean_ratio"] > 1.0
        assert model.trained

    def test_predict_basic(self, populated_db):
        model, _ = train(db_path=populated_db)
        result = predict(epiweek=202601, current_rate=40.0, lag=0, model=model)
        assert result["predicted_final_rate"] > 40.0
        assert result["revision_factor"] > 1.0
        assert result["n_historical"] > 0

    def test_predict_zero_rate(self, populated_db):
        model, _ = train(db_path=populated_db)
        result = predict(epiweek=202601, current_rate=0.0, lag=0, model=model)
        assert result["predicted_final_rate"] == 0.0
        assert result["revision_factor"] == 1.0

    def test_revision_factor_decreases_with_lag(self, populated_db):
        """More lag = rate is more final = smaller revision expected."""
        model, _ = train(db_path=populated_db)
        factors = []
        for lag in [0, 2, 5, 8, 12]:
            result = predict(epiweek=202601, current_rate=40.0, lag=lag, model=model)
            factors.append(result["revision_factor"])
        # Should be monotonically non-increasing (more lag = less revision)
        for i in range(len(factors) - 1):
            assert factors[i] >= factors[i + 1] - 0.01, (
                f"Revision factor at lag {[0,2,5,8,12][i]} ({factors[i]:.4f}) "
                f"should be >= factor at lag {[0,2,5,8,12][i+1]} ({factors[i+1]:.4f})"
            )

    def test_ci_contains_prediction(self, populated_db):
        model, _ = train(db_path=populated_db)
        result = predict(epiweek=202601, current_rate=40.0, lag=0, model=model)
        assert result["ci_lower"] <= result["predicted_final_rate"]
        assert result["ci_upper"] >= result["predicted_final_rate"]

    def test_ci_wider_at_low_lag(self, populated_db):
        """Earlier lags should have wider CIs (more uncertainty)."""
        model, _ = train(db_path=populated_db)
        r0 = predict(epiweek=202601, current_rate=40.0, lag=0, model=model)
        r10 = predict(epiweek=202601, current_rate=40.0, lag=10, model=model)
        ci_width_0 = r0["ci_upper"] - r0["ci_lower"]
        ci_width_10 = r10["ci_upper"] - r10["ci_lower"]
        assert ci_width_0 >= ci_width_10 - 1.0, (
            f"CI width at lag 0 ({ci_width_0:.2f}) should be >= "
            f"CI width at lag 10 ({ci_width_10:.2f})"
        )

    def test_train_with_season_filter(self, populated_db):
        from config import CURRENT_SEASON
        # Train only on one season
        single_season = [CURRENT_SEASON - 3]
        model, metrics = train(seasons=single_season, db_path=populated_db)
        assert metrics["n_seasons"] == 1
        assert metrics["seasons"] == single_season


class TestRevisionSummary:
    def test_summary_populated(self, populated_db):
        summary = get_revision_summary(db_path=populated_db)
        assert summary["n_epiweeks"] > 0
        assert len(summary["seasons"]) == 3
        assert len(summary["lags"]) > 0
        # Check that mean revision ratios are > 1.0 at early lags
        if 0 in summary["lags"]:
            assert summary["lags"][0]["mean_ratio"] > 1.0

    def test_summary_empty(self, tmp_db):
        summary = get_revision_summary(db_path=tmp_db)
        assert summary["n_epiweeks"] == 0


class TestSyntheticDataGeneration:
    def test_generates_data(self, tmp_db):
        generate_synthetic_revisions(n_seasons=2, weeks_per_season=10, max_lag=5, db_path=tmp_db)
        with get_connection(tmp_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM revisions").fetchone()[0]
        assert count > 0

    def test_data_has_multiple_lags(self, tmp_db):
        generate_synthetic_revisions(n_seasons=1, weeks_per_season=10, max_lag=5, db_path=tmp_db)
        with get_connection(tmp_db) as conn:
            lags = conn.execute("SELECT DISTINCT lag FROM revisions ORDER BY lag").fetchall()
        lag_values = [r[0] for r in lags]
        assert 0 in lag_values
        assert len(lag_values) > 1


class TestModelNotTrained:
    def test_predict_before_train_raises(self, tmp_db):
        # Pass an untrained model explicitly
        untrained = BackfillModel()
        with pytest.raises(RuntimeError, match="not trained"):
            predict(epiweek=202601, current_rate=40.0, lag=0, model=untrained)


# ---------------------------------------------------------------------------
# Property-based checks
# ---------------------------------------------------------------------------

class TestProperties:
    def test_higher_current_rate_higher_prediction(self, populated_db):
        """Predicted final rate should scale with current rate."""
        model, _ = train(db_path=populated_db)
        r_low = predict(epiweek=202601, current_rate=20.0, lag=0, model=model)
        r_high = predict(epiweek=202601, current_rate=60.0, lag=0, model=model)
        assert r_high["predicted_final_rate"] > r_low["predicted_final_rate"]

    def test_same_revision_factor_different_rates(self, populated_db):
        """Revision factor should be independent of the rate magnitude."""
        model, _ = train(db_path=populated_db)
        r1 = predict(epiweek=202601, current_rate=20.0, lag=0, model=model)
        r2 = predict(epiweek=202601, current_rate=60.0, lag=0, model=model)
        assert r1["revision_factor"] == pytest.approx(r2["revision_factor"], abs=0.001)
