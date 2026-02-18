"""Backfill revision prediction model for FluSurv-NET.

FluSurv-NET cumulative rates are revised upward 15-30% as lagging hospitals
report over subsequent weeks. This module predicts the final rate given a
preliminary rate and the current lag (weeks since first published).

Approach:
  - Compute historical revision ratios: final_rate / rate_at_lag_L
  - Group by lag (and optionally by week-of-season) to build empirical distributions
  - Predict by applying the mean revision ratio with confidence intervals

Cold start: when fewer than MIN_SEASONS historical seasons exist, widen
confidence intervals using a t-distribution correction.
"""

from __future__ import annotations

from __future__ import annotations

import logging
import math
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import DB_PATH, CURRENT_SEASON
from db import get_connection

logger = logging.getLogger(__name__)

# Minimum number of historical epiweeks at a given lag to consider "reliable"
MIN_OBSERVATIONS = 5
# Minimum number of seasons before we trust narrow CIs
MIN_SEASONS = 3
# Default maximum lag beyond which we treat the rate as "final"
DEFAULT_MAX_LAG = 20
# Quantile for 90% confidence interval (two-tailed)
CI_QUANTILE = 0.90
# z-score for 90% CI (normal approximation)
Z_90 = 1.645


@dataclass
class RevisionStats:
    """Statistics for revision ratios at a specific lag."""
    lag: int
    mean_ratio: float
    std_ratio: float
    median_ratio: float
    min_ratio: float
    max_ratio: float
    n_observations: int
    ci_lower: float  # 90% CI lower bound on the ratio
    ci_upper: float  # 90% CI upper bound on the ratio


@dataclass
class BackfillModel:
    """Trained backfill revision model."""
    lag_stats: dict[int, RevisionStats] = field(default_factory=dict)
    week_of_season_stats: dict[int, dict[int, RevisionStats]] = field(default_factory=dict)
    seasons_used: list[int] = field(default_factory=list)
    max_observed_lag: int = 0
    overall_mean_ratio: float = 1.0
    overall_std_ratio: float = 0.0
    trained: bool = False


# Module-level model instance (guarded by lock for thread safety)
import threading
_model_lock = threading.Lock()
_model = BackfillModel()


def _epiweek_to_season(epiweek: int) -> int:
    """Convert epiweek (YYYYWW) to season start year.

    Flu season runs from epiweek 40 to epiweek 39 of the next year.
    Epiweek 202540 through 202639 is the 2025 season.
    """
    year = epiweek // 100
    week = epiweek % 100
    if week >= 40:
        return year
    return year - 1


def _epiweek_to_week_of_season(epiweek: int) -> int:
    """Convert epiweek (YYYYWW) to week-of-season (1-based).

    Week 40 of the start year = week 1 of the season.
    """
    year = epiweek // 100
    week = epiweek % 100
    if week >= 40:
        return week - 39
    # After new year: need to account for weeks in previous year
    # Approximate: most years have 52 weeks, some have 53
    return (52 - 39) + week  # 13 + week


def _load_revision_data(
    seasons: list[int] | None = None,
    geography: str = "network_all",
    db_path: Path = DB_PATH,
) -> dict[int, dict[int, float]]:
    """Load revision data from the database.

    Returns: {epiweek: {lag: cumulative_rate}} for all matching epiweeks.
    """
    query = """
        SELECT epiweek, lag, cumulative_rate
        FROM revisions
        WHERE geography = ?
        ORDER BY epiweek, lag
    """
    params: list[Any] = [geography]

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    # Organize: {epiweek: {lag: rate}}
    data: dict[int, dict[int, float]] = defaultdict(dict)
    for row in rows:
        ew = row["epiweek"]
        if seasons is not None:
            season = _epiweek_to_season(ew)
            if season not in seasons:
                continue
        data[ew][row["lag"]] = row["cumulative_rate"]

    return dict(data)


def _compute_revision_ratios(
    data: dict[int, dict[int, float]],
    max_lag: int = DEFAULT_MAX_LAG,
) -> dict[int, list[float]]:
    """Compute revision ratios at each lag.

    For each epiweek, the revision ratio at lag L = final_rate / rate_at_lag_L.
    "Final" rate = rate at the maximum observed lag for that epiweek.

    Returns: {lag: [list of revision ratios across epiweeks]}
    """
    ratios: dict[int, list[float]] = defaultdict(list)

    for epiweek, lag_rates in data.items():
        if not lag_rates:
            continue

        # Final rate = rate at highest available lag
        max_available_lag = max(lag_rates.keys())
        final_rate = lag_rates[max_available_lag]

        if final_rate <= 0:
            continue

        for lag, rate in lag_rates.items():
            if lag >= max_available_lag:
                continue  # Don't compare final to itself
            if rate <= 0:
                continue
            if lag > max_lag:
                continue
            ratio = final_rate / rate
            ratios[lag].append(ratio)

    return dict(ratios)


def _compute_revision_ratios_by_week_of_season(
    data: dict[int, dict[int, float]],
    max_lag: int = DEFAULT_MAX_LAG,
) -> dict[int, dict[int, list[float]]]:
    """Compute revision ratios grouped by week-of-season and lag.

    Returns: {week_of_season: {lag: [ratios]}}
    """
    ratios: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    for epiweek, lag_rates in data.items():
        if not lag_rates:
            continue

        wos = _epiweek_to_week_of_season(epiweek)
        max_available_lag = max(lag_rates.keys())
        final_rate = lag_rates[max_available_lag]

        if final_rate <= 0:
            continue

        for lag, rate in lag_rates.items():
            if lag >= max_available_lag:
                continue
            if rate <= 0:
                continue
            if lag > max_lag:
                continue
            ratio = final_rate / rate
            ratios[wos][lag].append(ratio)

    return {wos: dict(lags) for wos, lags in ratios.items()}


def _stats_from_ratios(lag: int, ratios: list[float], n_seasons: int) -> RevisionStats:
    """Compute RevisionStats from a list of revision ratios."""
    n = len(ratios)
    if n == 0:
        return RevisionStats(
            lag=lag, mean_ratio=1.0, std_ratio=0.0, median_ratio=1.0,
            min_ratio=1.0, max_ratio=1.0, n_observations=0,
            ci_lower=1.0, ci_upper=1.0,
        )

    mean_r = statistics.mean(ratios)
    std_r = statistics.stdev(ratios) if n > 1 else 0.0
    median_r = statistics.median(ratios)

    # Compute 90% CI for the prediction (not the mean)
    # Use wider intervals when we have few seasons
    if n_seasons < MIN_SEASONS and n > 1:
        # Use t-distribution correction for small samples
        # Approximate: inflate z-score by sqrt(1 + 1/n) and use larger multiplier
        inflation = math.sqrt(1.0 + 1.0 / n)
        # Rough t-value for small df at 90% CI
        t_val = Z_90 * inflation * (1.5 if n_seasons <= 1 else 1.2)
    else:
        t_val = Z_90

    ci_lower = mean_r - t_val * std_r
    ci_upper = mean_r + t_val * std_r

    # Revision ratios should never be below 1.0 in expectation
    # (rates don't typically get revised downward)
    ci_lower = max(ci_lower, min(ratios) * 0.95)

    return RevisionStats(
        lag=lag,
        mean_ratio=mean_r,
        std_ratio=std_r,
        median_ratio=median_r,
        min_ratio=min(ratios),
        max_ratio=max(ratios),
        n_observations=n,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
    )


def train(
    seasons: list[int] | None = None,
    geography: str = "network_all",
    db_path: Path = DB_PATH,
) -> dict:
    """Train the backfill model on historical revision data.

    Args:
        seasons: List of season start years to train on. None = all available.
        geography: Geography filter for revisions (default: network_all).
        db_path: Path to SQLite database.

    Returns:
        Tuple of (BackfillModel, metrics_dict). The metrics dict has keys:
          - n_epiweeks: number of unique epiweeks used
          - n_seasons: number of unique seasons
          - seasons: list of season years
          - lag_stats: summary of revision stats at each lag
          - overall_mean_ratio: grand mean of all revision ratios

        Also sets the module-level model for backward compatibility.
    """
    global _model

    data = _load_revision_data(seasons=seasons, geography=geography, db_path=db_path)

    if not data:
        logger.warning("No revision data found. Model will use fallback heuristics.")
        new_model = BackfillModel(trained=True)
        with _model_lock:
            _model = new_model
        return new_model, {
            "n_epiweeks": 0,
            "n_seasons": 0,
            "seasons": [],
            "lag_stats": {},
            "overall_mean_ratio": 1.0,
            "warning": "No data - using fallback heuristics",
        }

    # Identify seasons present
    season_set = set()
    for ew in data:
        season_set.add(_epiweek_to_season(ew))
    seasons_list = sorted(season_set)
    n_seasons = len(seasons_list)

    # Compute revision ratios by lag
    lag_ratios = _compute_revision_ratios(data)

    # Compute stats at each lag
    lag_stats: dict[int, RevisionStats] = {}
    for lag in sorted(lag_ratios.keys()):
        lag_stats[lag] = _stats_from_ratios(lag, lag_ratios[lag], n_seasons)

    # Compute stats by week-of-season
    wos_ratios = _compute_revision_ratios_by_week_of_season(data)
    wos_stats: dict[int, dict[int, RevisionStats]] = {}
    for wos, lag_dict in wos_ratios.items():
        wos_stats[wos] = {}
        for lag in sorted(lag_dict.keys()):
            wos_stats[wos][lag] = _stats_from_ratios(lag, lag_dict[lag], n_seasons)

    # Overall stats
    all_ratios = [r for rs in lag_ratios.values() for r in rs]
    overall_mean = statistics.mean(all_ratios) if all_ratios else 1.0
    overall_std = statistics.stdev(all_ratios) if len(all_ratios) > 1 else 0.0
    max_observed = max(lag_ratios.keys()) if lag_ratios else 0

    new_model = BackfillModel(
        lag_stats=lag_stats,
        week_of_season_stats=wos_stats,
        seasons_used=seasons_list,
        max_observed_lag=max_observed,
        overall_mean_ratio=overall_mean,
        overall_std_ratio=overall_std,
        trained=True,
    )
    with _model_lock:
        _model = new_model

    metrics = {
        "n_epiweeks": len(data),
        "n_seasons": n_seasons,
        "seasons": seasons_list,
        "lag_stats": {
            lag: {
                "mean_ratio": s.mean_ratio,
                "std_ratio": s.std_ratio,
                "median_ratio": s.median_ratio,
                "n_observations": s.n_observations,
                "ci_lower": s.ci_lower,
                "ci_upper": s.ci_upper,
            }
            for lag, s in lag_stats.items()
        },
        "overall_mean_ratio": overall_mean,
    }

    logger.info(
        "Backfill model trained: %d epiweeks, %d seasons, %d lag levels",
        len(data), n_seasons, len(lag_stats),
    )
    return new_model, metrics


def predict(epiweek: int, current_rate: float, lag: int = 0,
            model: BackfillModel | None = None) -> dict:
    """Predict the final cumulative rate given a preliminary rate.

    Args:
        epiweek: The epiweek for which the rate is reported (YYYYWW).
        current_rate: The current preliminary cumulative rate.
        lag: Number of weeks since this epiweek was first published.
        model: Optional trained BackfillModel. If None, uses module-level model.

    Returns:
        Dictionary with:
          - predicted_final_rate: best estimate of final rate
          - revision_factor: multiplicative adjustment (predicted / current)
          - ci_lower: 90% CI lower bound on final rate
          - ci_upper: 90% CI upper bound on final rate
          - n_historical: number of historical observations at this lag
    """
    m = model or _model
    if not m.trained:
        raise RuntimeError(
            "Backfill model not trained. Call train() first."
        )

    if current_rate <= 0:
        return {
            "predicted_final_rate": 0.0,
            "revision_factor": 1.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "n_historical": 0,
        }

    # Try week-of-season specific stats first (more granular)
    wos = _epiweek_to_week_of_season(epiweek)
    stats = None

    if wos in m.week_of_season_stats:
        wos_lag_stats = m.week_of_season_stats[wos]
        if lag in wos_lag_stats and wos_lag_stats[lag].n_observations >= MIN_OBSERVATIONS:
            stats = wos_lag_stats[lag]

    # Fall back to lag-only stats
    if stats is None and lag in m.lag_stats:
        stats = m.lag_stats[lag]

    # Fall back to nearest available lag
    if stats is None and m.lag_stats:
        available_lags = sorted(m.lag_stats.keys())
        # Find closest lag
        nearest = min(available_lags, key=lambda l: abs(l - lag))
        stats = m.lag_stats[nearest]
        logger.debug(
            "No stats for lag %d, using nearest lag %d", lag, nearest
        )

    # Cold start fallback: no data at all
    if stats is None or stats.n_observations == 0:
        return _fallback_predict(current_rate, lag)

    revision_factor = stats.mean_ratio
    predicted_final = current_rate * revision_factor
    ci_lower_rate = current_rate * stats.ci_lower
    ci_upper_rate = current_rate * stats.ci_upper

    return {
        "predicted_final_rate": round(predicted_final, 2),
        "revision_factor": round(revision_factor, 4),
        "ci_lower": round(ci_lower_rate, 2),
        "ci_upper": round(ci_upper_rate, 2),
        "n_historical": stats.n_observations,
    }


def _fallback_predict(current_rate: float, lag: int) -> dict:
    """Fallback prediction when no historical data is available.

    Uses a simple heuristic: earlier lags have more revision potential.
    Based on domain knowledge that FluSurv-NET revisions are typically 15-30%.
    """
    # Heuristic revision factors by lag
    # lag 0: rate is very preliminary, expect ~25% upward revision
    # lag 5: partially revised, expect ~15%
    # lag 10+: mostly finalized, expect ~5%
    if lag <= 0:
        factor = 1.25
        std = 0.15
    elif lag <= 2:
        factor = 1.20
        std = 0.12
    elif lag <= 5:
        factor = 1.12
        std = 0.08
    elif lag <= 10:
        factor = 1.05
        std = 0.05
    else:
        factor = 1.02
        std = 0.03

    predicted = current_rate * factor
    # Wide CIs for fallback
    ci_lower = current_rate * (factor - Z_90 * std * 1.5)
    ci_upper = current_rate * (factor + Z_90 * std * 1.5)

    return {
        "predicted_final_rate": round(predicted, 2),
        "revision_factor": round(factor, 4),
        "ci_lower": round(max(ci_lower, current_rate * 0.95), 2),
        "ci_upper": round(ci_upper, 2),
        "n_historical": 0,
    }


def get_revision_summary(
    geography: str = "network_all",
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Get a summary of revision data in the database.

    Useful for diagnostics and the analyze_revisions script.
    """
    data = _load_revision_data(geography=geography, db_path=db_path)
    if not data:
        return {"n_epiweeks": 0, "seasons": [], "lags": {}}

    season_set = set()
    for ew in data:
        season_set.add(_epiweek_to_season(ew))

    lag_ratios = _compute_revision_ratios(data)

    summary: dict[str, Any] = {
        "n_epiweeks": len(data),
        "seasons": sorted(season_set),
        "epiweek_range": (min(data.keys()), max(data.keys())),
        "lags": {},
    }

    for lag in sorted(lag_ratios.keys()):
        ratios = lag_ratios[lag]
        summary["lags"][lag] = {
            "n": len(ratios),
            "mean_ratio": round(statistics.mean(ratios), 4),
            "std_ratio": round(statistics.stdev(ratios), 4) if len(ratios) > 1 else 0.0,
            "median_ratio": round(statistics.median(ratios), 4),
            "min_ratio": round(min(ratios), 4),
            "max_ratio": round(max(ratios), 4),
            "mean_magnitude": round(
                statistics.mean([(r - 1.0) for r in ratios]) * 100, 2
            ),  # as percentage
        }

    return summary


# ---------------------------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------------------------

def plot_revision_curves(
    epiweeks: list[int] | None = None,
    geography: str = "network_all",
    db_path: Path = DB_PATH,
    save_path: str | None = None,
) -> Any:
    """Plot revision curves: cumulative rate vs. lag for multiple epiweeks.

    Each line shows how a single epiweek's rate evolved as revisions came in.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.error("matplotlib not installed. Cannot plot.")
        return None

    data = _load_revision_data(geography=geography, db_path=db_path)
    if not data:
        logger.warning("No revision data to plot.")
        return None

    if epiweeks is not None:
        data = {ew: lags for ew, lags in data.items() if ew in epiweeks}

    fig, ax = plt.subplots(figsize=(12, 6))

    for ew in sorted(data.keys()):
        lag_rates = data[ew]
        lags = sorted(lag_rates.keys())
        rates = [lag_rates[l] for l in lags]
        season = _epiweek_to_season(ew)
        ax.plot(lags, rates, marker="o", markersize=3, label=f"{ew} (S{season})", alpha=0.6)

    ax.set_xlabel("Lag (weeks since first published)")
    ax.set_ylabel("Cumulative Rate (per 100k)")
    ax.set_title("FluSurv-NET Revision Curves")
    ax.legend(fontsize=7, ncol=3, loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
        logger.info("Saved revision curves plot to %s", save_path)

    return fig


def plot_revision_factor_distribution(
    geography: str = "network_all",
    db_path: Path = DB_PATH,
    save_path: str | None = None,
) -> Any:
    """Plot distribution of revision factors at each lag.

    Box plot showing the spread of final_rate / rate_at_lag for each lag.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.error("matplotlib not installed. Cannot plot.")
        return None

    data = _load_revision_data(geography=geography, db_path=db_path)
    if not data:
        logger.warning("No revision data to plot.")
        return None

    lag_ratios = _compute_revision_ratios(data)
    if not lag_ratios:
        logger.warning("No revision ratios to plot.")
        return None

    lags_sorted = sorted(lag_ratios.keys())
    ratio_data = [lag_ratios[l] for l in lags_sorted]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Box plot
    bp = ax1.boxplot(ratio_data, labels=[str(l) for l in lags_sorted], patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("lightblue")
    ax1.axhline(y=1.0, color="red", linestyle="--", alpha=0.5, label="No revision")
    ax1.set_xlabel("Lag (weeks)")
    ax1.set_ylabel("Revision Factor (final / preliminary)")
    ax1.set_title("Revision Factor Distribution by Lag")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Mean revision factor curve
    means = [statistics.mean(lag_ratios[l]) for l in lags_sorted]
    stds = [statistics.stdev(lag_ratios[l]) if len(lag_ratios[l]) > 1 else 0.0 for l in lags_sorted]
    ax2.errorbar(lags_sorted, means, yerr=[s * Z_90 for s in stds],
                 fmt="o-", capsize=4, color="darkblue")
    ax2.axhline(y=1.0, color="red", linestyle="--", alpha=0.5)
    ax2.set_xlabel("Lag (weeks)")
    ax2.set_ylabel("Mean Revision Factor")
    ax2.set_title("Mean Revision Factor with 90% CI")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
        logger.info("Saved revision factor distribution plot to %s", save_path)

    return fig


# ---------------------------------------------------------------------------
# Convenience: train from synthetic data (for testing / cold start)
# ---------------------------------------------------------------------------

def generate_synthetic_revisions(
    n_seasons: int = 3,
    weeks_per_season: int = 25,
    max_lag: int = 15,
    db_path: Path = DB_PATH,
) -> None:
    """Generate synthetic revision data for testing.

    Creates realistic-looking revision curves where:
    - Cumulative rate grows over the season
    - Early lags undercount by 15-30%, converging to final over ~10-15 weeks
    """
    import random
    random.seed(42)

    base_season = CURRENT_SEASON - n_seasons

    with get_connection(db_path) as conn:
        for s in range(n_seasons):
            season_year = base_season + s
            # Season severity multiplier
            severity = random.uniform(0.8, 1.5)

            for week_idx in range(1, weeks_per_season + 1):
                # Epiweek: season starts at week 40
                if week_idx <= 13:
                    ew = (season_year * 100) + 39 + week_idx
                else:
                    ew = ((season_year + 1) * 100) + (week_idx - 13)

                # "True" final cumulative rate: grows sigmoidally over the season
                t = week_idx / weeks_per_season
                final_rate = severity * 65.0 * (1.0 / (1.0 + math.exp(-8 * (t - 0.4))))
                final_rate = max(final_rate, 0.1)

                for lag in range(0, min(max_lag + 1, weeks_per_season - week_idx + 1)):
                    # Revision curve: starts at ~75% of final, converges
                    completeness = 0.70 + 0.30 * (1.0 - math.exp(-0.3 * lag))
                    noise = random.gauss(0, 0.02)
                    rate_at_lag = final_rate * max(completeness + noise, 0.5)

                    report_ew = ew + lag  # simplified
                    # Adjust for year boundary
                    report_year = report_ew // 100
                    report_week = report_ew % 100
                    if report_week > 52:
                        report_year += 1
                        report_week -= 52
                    report_ew = report_year * 100 + report_week

                    conn.execute(
                        """INSERT OR IGNORE INTO revisions
                           (epiweek, report_epiweek, lag, cumulative_rate,
                            weekly_rate, geography, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (ew, report_ew, lag, round(rate_at_lag, 2),
                         None, "network_all", "2026-01-01T00:00:00"),
                    )
