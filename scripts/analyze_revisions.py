#!/usr/bin/env python3
"""Analyze FluSurv-NET revision data from the database.

Prints summary statistics about how cumulative rates are revised upward
over time. Useful for manual verification and generating research prompts.

Usage:
    python scripts/analyze_revisions.py [--synthetic] [--plot]
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH
from db import init_db
from models.backfill import (
    get_revision_summary,
    generate_synthetic_revisions,
    train,
    predict,
)


def print_separator(char: str = "=", width: int = 70) -> None:
    print(char * width)


def print_header(title: str) -> None:
    print()
    print_separator()
    print(f"  {title}")
    print_separator()


def analyze(db_path: Path = DB_PATH, use_synthetic: bool = False) -> None:
    if use_synthetic:
        print("[*] Generating synthetic revision data for analysis...")
        init_db(db_path)
        generate_synthetic_revisions(n_seasons=3, weeks_per_season=25, max_lag=15, db_path=db_path)

    summary = get_revision_summary(db_path=db_path)

    if summary["n_epiweeks"] == 0:
        print("[!] No revision data found in database.")
        print("    Run with --synthetic to generate test data.")
        return

    print_header("FluSurv-NET Revision Analysis")

    print(f"\n  Epiweeks analyzed:  {summary['n_epiweeks']}")
    print(f"  Seasons:            {summary['seasons']}")
    if "epiweek_range" in summary:
        print(f"  Epiweek range:      {summary['epiweek_range'][0]} - {summary['epiweek_range'][1]}")
    print(f"  Lag levels:         {len(summary['lags'])}")

    print_header("Revision Ratios by Lag")
    print(f"  {'Lag':>4}  {'N':>5}  {'Mean':>7}  {'Std':>7}  {'Median':>7}  {'Min':>7}  {'Max':>7}  {'Mean Mag%':>9}")
    print(f"  {'----':>4}  {'-----':>5}  {'-------':>7}  {'-------':>7}  {'-------':>7}  {'-------':>7}  {'-------':>7}  {'---------':>9}")

    for lag in sorted(summary["lags"].keys()):
        s = summary["lags"][lag]
        print(
            f"  {lag:>4}  {s['n']:>5}  {s['mean_ratio']:>7.4f}  {s['std_ratio']:>7.4f}  "
            f"{s['median_ratio']:>7.4f}  {s['min_ratio']:>7.4f}  {s['max_ratio']:>7.4f}  "
            f"{s['mean_magnitude']:>8.2f}%"
        )

    print_header("Key Takeaways")

    if 0 in summary["lags"]:
        lag0 = summary["lags"][0]
        print(f"\n  Lag 0 (first report): mean revision ratio = {lag0['mean_ratio']:.4f}")
        print(f"    -> A preliminary rate of 40.0 will likely become {40.0 * lag0['mean_ratio']:.1f}")
        print(f"    -> Revision range: {lag0['min_ratio']:.2f}x to {lag0['max_ratio']:.2f}x")

    # Find the lag where revision stabilizes (<2%)
    stable_lag = None
    for lag in sorted(summary["lags"].keys()):
        if summary["lags"][lag]["mean_magnitude"] < 2.0:
            stable_lag = lag
            break
    if stable_lag is not None:
        print(f"\n  Data stabilizes around lag {stable_lag} (<2% mean revision)")
    else:
        print("\n  Data does not fully stabilize within observed lag range")

    print_header("Model Predictions (Example)")
    model, metrics = train(db_path=db_path)
    print(f"\n  Trained on {metrics['n_epiweeks']} epiweeks, {metrics['n_seasons']} seasons")
    print()
    print(f"  {'Lag':>4}  {'Current':>8}  {'Predicted':>10}  {'Factor':>7}  {'90% CI':>16}  {'N hist':>6}")
    print(f"  {'----':>4}  {'--------':>8}  {'----------':>10}  {'-------':>7}  {'----------------':>16}  {'------':>6}")

    for lag in [0, 1, 2, 3, 5, 8, 10, 15]:
        r = predict(epiweek=202601, current_rate=40.0, lag=lag, model=model)
        ci_str = f"[{r['ci_lower']:.1f}, {r['ci_upper']:.1f}]"
        print(
            f"  {lag:>4}  {40.0:>8.1f}  {r['predicted_final_rate']:>10.1f}  "
            f"{r['revision_factor']:>7.4f}  {ci_str:>16}  {r['n_historical']:>6}"
        )

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze FluSurv-NET revision data")
    parser.add_argument(
        "--synthetic", action="store_true",
        help="Generate synthetic data for testing (will not overwrite real data)"
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="Generate revision curve plots"
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to database (default: config.DB_PATH)"
    )
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    analyze(db_path=db_path, use_synthetic=args.synthetic)

    if args.plot:
        try:
            from models.backfill import plot_revision_curves, plot_revision_factor_distribution
            print("[*] Generating plots...")
            plot_revision_curves(db_path=db_path, save_path="data/revision_curves.png")
            plot_revision_factor_distribution(db_path=db_path, save_path="data/revision_factors.png")
            print("[+] Plots saved to data/")
        except ImportError:
            print("[!] matplotlib not installed, skipping plots")


if __name__ == "__main__":
    main()
