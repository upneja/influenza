# Models Directory

## Components

### backfill.py — Revision Prediction Model
- Input: Delphi Epidata versioned FluSurv-NET data (all historical revisions)
- Output: Predicted final cumulative rate, given current preliminary rate
- Method: Analyze historical revision curves (lag 0 → final) to predict upward adjustment
- Key insight: Recent weeks are revised upward 15-30%. Model should learn per-lag adjustment factors.

### nowcast.py — Bracket Probability Ensemble
- Input: All signal values for current epiweek + backfill-adjusted cumulative rate
- Output: Probability distribution over market brackets (e.g., <30, 30-40, 40-50, 50-60, 60-70, 70+)
- Method: Elastic net regression on signal features → point estimate → calibrated probability distribution over brackets
- Must output calibrated probabilities that sum to 1.0

### calibration.py — Probability Calibration
- Input: Raw model predictions
- Output: Calibrated bracket probabilities
- Method: EMOS (Ensemble Model Output Statistics) or isotonic regression
- Calibrate using leave-one-season-out cross-validation

## Contracts
- Models read from SQLite (signal data stored by signal modules)
- Models write predictions to SQLite `predictions` table
- All models must expose: `train(seasons: list[int])` and `predict(epiweek: int) -> dict[str, float]`
