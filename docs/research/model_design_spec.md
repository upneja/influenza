# FluSight Edge: Mathematical Model Design Specification

**Author:** MATH-1 Agent
**Date:** 2026-02-18
**Status:** Draft
**Version:** 1.0

---

## Table of Contents

1. [Backfill Revision Model](#1-backfill-revision-model)
2. [Elastic Net Ensemble (Nowcast Model)](#2-elastic-net-ensemble-nowcast-model)
3. [Bracket Probability Conversion](#3-bracket-probability-conversion)
4. [Brier Score Methodology](#4-brier-score-methodology)
5. [Fractional Kelly Criterion](#5-fractional-kelly-criterion)
6. [Edge Estimation and Sequential Monitoring](#6-edge-estimation-and-sequential-monitoring)

---

## Notation

| Symbol | Meaning |
|--------|---------|
| $y_{w}$ | True final cumulative hospitalization rate for epiweek $w$ |
| $y_{w}^{(L)}$ | Preliminary cumulative rate for epiweek $w$ observed at lag $L$ weeks |
| $s$ | Season index ($s \in \{2019, 2022, 2023, 2024, 2025\}$; 2020-2021 excluded due to COVID) |
| $w$ | Epiweek index within a season ($w \in [40, 52] \cup [1, 20]$ approximately) |
| $B_k$ | Bracket $k$ (e.g., "<30", "30-40", ..., "70+"), $k \in \{1, ..., K\}$ with $K = 6$ |
| $p_k$ | Model-assigned probability that the outcome falls in bracket $B_k$ |
| $m_k$ | Market-implied probability for bracket $B_k$ (from last trade or midpoint price) |
| $\hat{y}$ | Point estimate of the cumulative rate |
| $f$ | Kelly fraction multiplier (0.20) |

---

## 1. Backfill Revision Model

### 1.1 Problem Statement

CDC FluSurv-NET cumulative hospitalization rates undergo substantial upward revision after initial publication. The preliminary rate $y_w^{(0)}$ reported in the same week as the data is typically 15--30% below the final settled value $y_w^{(\infty)}$. Polymarket contracts resolve on the **final** value, not the preliminary one. We must predict $y_w^{(\infty)}$ from $y_w^{(L)}$ where $L$ is the current lag (number of weeks since epiweek $w$).

### 1.2 Model Choice: Multiplicative Log-Linear Revision Model

We use a **multiplicative** rather than additive model. Rationale: revision magnitude scales with the level of the rate. A week with a preliminary rate of 50 tends to be revised upward by more absolute units than a week with a rate of 10, but the proportional revision is more stable. Empirically, FluSurv-NET revision ratios cluster around 1.15--1.30 across seasons regardless of absolute level.

#### Definition

Let the **revision ratio** at lag $L$ be:

$$R_w^{(L)} = \frac{y_w^{(\infty)}}{y_w^{(L)}}$$

We model:

$$\log R_w^{(L)} = \beta_0^{(L)} + \beta_1^{(L)} \cdot \text{week}_w + \beta_2^{(L)} \cdot \log y_w^{(L)} + \beta_3^{(L)} \cdot \text{severity}_s + \varepsilon_w$$

where:

- $\text{week}_w \in [1, 33]$ is the week number within the season (epiweek 40 maps to week 1, epiweek 20 maps to week 33), capturing the fact that revisions at end-of-season are smaller (less backlog).
- $\log y_w^{(L)}$ captures any residual level-dependence after the log transformation.
- $\text{severity}_s$ is a season-level severity indicator (z-scored peak rate for season $s$ relative to historical average). This accounts for the fact that severe seasons may have larger reporting backlogs.
- $\varepsilon_w \sim \mathcal{N}(0, \sigma_L^2)$.

We fit **separate models per lag** $L \in \{0, 1, 2, 3, 4, 5+\}$, where lag $5+$ pools all lags $\geq 5$. By lag 5 revisions are typically near zero, so fewer parameters are justified.

#### Simplified Fallback

If covariates $\text{week}_w$ and $\text{severity}_s$ do not improve leave-one-season-out (LOSO) cross-validation performance, fall back to the intercept-only model:

$$\log R_w^{(L)} = \mu_L + \varepsilon_w$$

which simply learns the average log revision ratio per lag. The predicted final rate becomes:

$$\hat{y}_w^{(\infty)} = y_w^{(L)} \cdot \exp(\hat{\mu}_L + \tfrac{1}{2}\hat{\sigma}_L^2)$$

The $\tfrac{1}{2}\hat{\sigma}_L^2$ term is the log-normal bias correction ensuring the estimate is the conditional mean (not the median).

### 1.3 Confidence Interval

Under the log-normal model, the prediction interval for $y_w^{(\infty)}$ is:

$$\left[ y_w^{(L)} \cdot \exp(\hat{\mu}_L - z_{\alpha/2} \cdot \hat{\sigma}_L), \quad y_w^{(L)} \cdot \exp(\hat{\mu}_L + z_{\alpha/2} \cdot \hat{\sigma}_L) \right]$$

where $z_{\alpha/2} = 1.96$ for a 95% interval.

For the full regression model, replace $\hat{\mu}_L$ with the fitted conditional mean $\hat{\beta}^{(L)} \cdot \mathbf{x}_w$ and $\hat{\sigma}_L$ with the residual standard error.

### 1.4 Training Procedure

**Available data:** Seasons 2018-2019, 2019-2020, 2022-2023, 2023-2024, 2024-2025 (5 seasons; 2020-2021 and 2021-2022 excluded due to COVID distortions). Each season contributes approximately 25--30 epiweeks, each with revision snapshots at lags 0 through ~20. Total sample: ~125--150 week-lag observations per lag group.

**Loss function:** Minimize mean squared error of $\log R_w^{(L)}$ predictions, which is equivalent to minimizing the geometric mean of the squared revision ratio error. This naturally penalizes both under- and over-estimation of the multiplicative factor.

**Regularization:** Given $\leq 4$ predictors and ~130 observations per lag, ordinary least squares is adequate. No regularization needed. If we add interaction terms or additional covariates, apply ridge regression ($\ell_2$) with $\lambda$ chosen by LOSO-CV.

**Validation:**

- **Primary:** Leave-one-season-out cross-validation (LOSO-CV). Train on 4 seasons, predict the 5th. Repeat 5 times. Report mean absolute error (MAE) and mean absolute percentage error (MAPE) of the predicted final rate.
- **Secondary:** Within-season temporal holdout: train on weeks 1--20 of all seasons, predict weeks 21--33.
- **Model selection criterion:** LOSO-CV MAPE. If the full regression model does not improve MAPE by at least 5% relative to the intercept-only model, prefer the simpler model.

### 1.5 Handling Edge Cases

- **Early season (weeks 1--3):** Very few cumulative hospitalizations have occurred. Revision ratios may be extremely noisy (e.g., 0.5 revising to 2.0 is a 4x ratio). Impose a floor: $\hat{y}_w^{(\infty)} \geq y_w^{(L)}$ (revisions are monotonically upward for FluSurv-NET).
- **Lag 0 (same-week report):** Largest revisions. Use the most recent 3 seasons' lag-0 ratios as a robust prior. If the current season's observed ratios at longer lags are systematically different from historical, apply a season-specific adjustment.
- **Missing revision data:** If a particular lag's observation is missing, linearly interpolate the log revision ratio between the nearest available lags.

---

## 2. Elastic Net Ensemble (Nowcast Model)

### 2.1 Objective

Predict the **next week's final cumulative hospitalization rate** $y_{w+1}^{(\infty)}$ using 7 real-time surveillance signals, where "final" means the backfill-adjusted value (not the preliminary CDC report).

### 2.2 Why Elastic Net?

| Method | Pros | Cons for our setting |
|--------|------|----------------------|
| OLS | Simple, interpretable | Overfits with 20+ features and ~130 training samples |
| Ridge | Handles collinearity | Keeps all features; harder to interpret which signals matter |
| LASSO | Feature selection | Unstable with correlated features (our signals are correlated) |
| **Elastic Net** | **Feature selection + handles collinearity** | **Slight tuning needed** |
| Random Forest | Nonlinear, robust | Needs 500+ samples for stable tree splits; poor extrapolation |
| XGBoost | State-of-the-art tabular | Same sample size issue; hard to calibrate uncertainty |

**Decision:** Elastic net is the right choice because:
1. We have ~130 training observations (5 seasons x 26 weeks) and 20+ candidate features. The ratio is marginal for unregularized methods.
2. Our 7 signals are substantially correlated (e.g., wastewater and ED syndromic both track influenza incidence). LASSO would arbitrarily pick one from a correlated group; elastic net keeps partially-correlated predictors.
3. We need interpretable coefficients to sanity-check the model (e.g., "wastewater up --> rate up").
4. We need to extrapolate to unseen severity levels. Linear models extrapolate more gracefully than tree ensembles.

### 2.3 Feature Engineering

For each signal $j$ at epiweek $w$, construct the following features. Let $x_j(w)$ denote the raw signal value.

#### Signal 1: Wastewater (WastewaterSCAN Influenza A concentration)

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `ww_level` | $\bar{x}_{\text{ww}}(w)$ averaged over FluSurv-NET catchment sites | Absolute pathogen load |
| `ww_delta` | $\bar{x}_{\text{ww}}(w) - \bar{x}_{\text{ww}}(w-1)$ | Week-over-week change |
| `ww_roc` | $\frac{\bar{x}_{\text{ww}}(w) - \bar{x}_{\text{ww}}(w-1)}{\bar{x}_{\text{ww}}(w-1) + \epsilon}$ | Rate of change (add $\epsilon = 0.01$ to avoid division by zero) |
| `ww_2wk_trend` | $\bar{x}_{\text{ww}}(w) - \bar{x}_{\text{ww}}(w-2)$ | Two-week momentum |

#### Signal 2: ED Syndromic Surveillance (NSSP % flu-related ED visits)

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `ed_pct` | Percentage of ED visits flagged as flu-like illness | Absolute level |
| `ed_delta` | $x_{\text{ed}}(w) - x_{\text{ed}}(w-1)$ | Week-over-week change |
| `ed_roc` | Rate of change (same formula as wastewater) | Normalized trend |

#### Signal 3: Google Trends (Influenza search interest, national)

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `gt_index` | Google Trends index $\in [0, 100]$ | Search interest as proxy for disease awareness |
| `gt_delta` | $x_{\text{gt}}(w) - x_{\text{gt}}(w-1)$ | Momentum |

#### Signal 4: Antiviral Prescriptions (Oseltamivir fills, IQVIA or similar)

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `rx_count` | Normalized fill count | Direct measure of diagnosed/treated flu |
| `rx_roc` | Week-over-week rate of change | Trend |

#### Signal 5: FluSight Ensemble (CDC official forecast)

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `flusight_point` | FluSight ensemble point estimate for next week's rate | Consensus forecast |
| `flusight_width` | 90% PI upper - lower bound | Forecast uncertainty; wide = uncertain |
| `flusight_skew` | (upper - point) / (point - lower) | Asymmetry of risk |

#### Signal 6: Delphi Backfill-Adjusted Rate

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `bf_rate` | $\hat{y}_w^{(\infty)}$ from Section 1 | Best estimate of current true cumulative rate |
| `bf_delta` | $\hat{y}_w^{(\infty)} - \hat{y}_{w-1}^{(\infty)}$ | Adjusted weekly incidence |
| `bf_ratio` | $\hat{y}_w^{(\infty)} / y_w^{(0)}$ | How much backfill we are predicting (high = lots of unreported) |

#### Signal 7: ILINet (% ILI visits from outpatient sentinel network)

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `ili_pct` | Percentage of outpatient visits for influenza-like illness | Clinical surveillance baseline |
| `ili_delta` | $x_{\text{ili}}(w) - x_{\text{ili}}(w-1)$ | Trend |

**Total features:** 4 + 3 + 2 + 2 + 3 + 3 + 2 = **19 features**.

#### Additional Contextual Features

| Feature | Definition | Rationale |
|---------|------------|-----------|
| `season_week` | Week number within season $\in [1, 33]$ | Captures seasonality |
| `cum_rate_prev` | Previous week's backfill-adjusted cumulative rate $\hat{y}_{w-1}^{(\infty)}$ | Autoregressive baseline |

**Grand total: 21 features.**

### 2.4 Preprocessing

1. **Standardization:** All features are z-scored using training-set means and standard deviations. At prediction time, use the training-set statistics (not recomputed).
2. **Missing values:** If a signal is unavailable for a given week, impute with the previous week's value (last-observation-carried-forward). If no previous value exists (season start), impute with the training-set mean.
3. **Target variable:** $y_{w+1}^{(\infty)}$ -- the final cumulative rate for the **next** epiweek. This is a 1-week-ahead forecast. The target is also z-scored during training and inverse-transformed at prediction time.

### 2.5 Model Specification

The elastic net solves:

$$\hat{\boldsymbol{\beta}} = \arg\min_{\boldsymbol{\beta}} \left\{ \frac{1}{2N} \sum_{i=1}^{N} (y_i - \mathbf{x}_i^T \boldsymbol{\beta})^2 + \alpha \left[ \frac{1 - \rho}{2} \|\boldsymbol{\beta}\|_2^2 + \rho \|\boldsymbol{\beta}\|_1 \right] \right\}$$

where:
- $\alpha > 0$ is the overall regularization strength.
- $\rho \in [0, 1]$ is the $\ell_1$ ratio (LASSO weight). $\rho = 1$ is pure LASSO; $\rho = 0$ is pure ridge.
- $N$ is the number of training observations (~130).
- $\mathbf{x}_i \in \mathbb{R}^{21}$ is the feature vector.
- $y_i$ is the standardized target.

### 2.6 Hyperparameter Tuning

**Method:** Leave-one-season-out cross-validation (LOSO-CV).

1. For each held-out season $s$, train on the remaining 4 seasons.
2. Within the training fold, run a grid search over:
   - $\alpha \in \{10^{-4}, 10^{-3}, 10^{-2}, 0.05, 0.1, 0.5, 1.0, 5.0\}$
   - $\rho \in \{0.1, 0.3, 0.5, 0.7, 0.9\}$
3. Select $(\alpha^*, \rho^*)$ that minimizes the average RMSE across all 5 LOSO folds.

**Practical implementation:** Use `sklearn.linear_model.ElasticNetCV` with `cv=PredefinedSplit` configured for LOSO groups. The `PredefinedSplit` assigns each observation to its season's fold.

**Expected outcome:** Based on typical epidemiological nowcasting, $\rho^* \approx 0.3$--$0.5$ (modest LASSO component) and $\alpha^* \approx 0.01$--$0.1$.

### 2.7 Output

The model produces:

$$\hat{y}_{w+1} = \mathbf{x}_w^T \hat{\boldsymbol{\beta}} \cdot \hat{\sigma}_y + \hat{\mu}_y$$

where $\hat{\sigma}_y$ and $\hat{\mu}_y$ are the training-set standard deviation and mean of the target (inverse z-score).

The **residual standard error** is estimated from LOSO-CV residuals:

$$\hat{\sigma}_{\text{res}} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} (y_i - \hat{y}_i^{(-s_i)})^2}$$

where $\hat{y}_i^{(-s_i)}$ is the prediction for observation $i$ from the model trained without season $s_i$.

This pair $(\hat{y}_{w+1}, \hat{\sigma}_{\text{res}})$ feeds into the bracket probability conversion (Section 3).

---

## 3. Bracket Probability Conversion

### 3.1 Problem Statement

Convert a point estimate $\hat{y}$ and residual standard error $\hat{\sigma}$ into a probability distribution over $K = 6$ brackets: $B_1 = [0, 30)$, $B_2 = [30, 40)$, $B_3 = [40, 50)$, $B_4 = [50, 60)$, $B_5 = [60, 70)$, $B_6 = [70, \infty)$.

### 3.2 Options Considered

| Method | Description | Assessment |
|--------|-------------|------------|
| **(a) Normal CDF** | Assume $Y \sim \mathcal{N}(\hat{y}, \hat{\sigma}^2)$, compute $P(B_k)$ from CDF | Simple; may be miscalibrated (real errors are often skewed right for cumulative rates) |
| **(b) EMOS** | Fit $Y \sim \mathcal{N}(a + b\hat{y}, (c + d\hat{\sigma})^2)$ via maximum likelihood on training data | Calibrated; standard in weather forecasting; 4 parameters to fit |
| **(c) Quantile Regression** | Separate regression for each quantile of interest | Requires fitting many models; crossing quantiles problematic with small data |

### 3.3 Recommended Approach: EMOS with Log-Normal Extension

**Primary method: EMOS (Ensemble Model Output Statistics)** with a log-normal distributional assumption.

Rationale:
- EMOS is the standard approach for calibrating ensemble forecasts in meteorology and has been successfully applied to epidemiological forecasting.
- We choose log-normal over normal because cumulative hospitalization rates are non-negative, right-skewed, and the variance increases with the mean.
- With only 4 parameters, EMOS is feasible to fit with ~130 training observations.
- EMOS directly optimizes calibration via CRPS (Continuous Ranked Probability Score), which is the proper scoring rule for distributional forecasts.

#### Specification

Assume:

$$\log Y \mid \hat{y}, \hat{\sigma} \sim \mathcal{N}\!\left(\mu(\hat{y}), \sigma^2(\hat{\sigma})\right)$$

where:

$$\mu(\hat{y}) = a + b \cdot \log(\hat{y})$$
$$\sigma(\hat{\sigma}) = \exp(c + d \cdot \log(\hat{\sigma}))$$

Parameters $\theta = (a, b, c, d)$ are fitted by minimizing the **CRPS** over training data:

$$\hat{\theta} = \arg\min_{\theta} \frac{1}{N} \sum_{i=1}^{N} \text{CRPS}\!\left(\mathcal{LN}(\mu_i, \sigma_i^2), \; y_i\right)$$

The CRPS for a log-normal distribution $\mathcal{LN}(\mu, \sigma^2)$ evaluated at observation $y$ has a closed-form expression:

$$\text{CRPS}(\mathcal{LN}(\mu, \sigma^2), y) = y \left[2\Phi\!\left(\frac{\log y - \mu}{\sigma}\right) - 1\right] - 2\exp\!\left(\mu + \frac{\sigma^2}{2}\right)\left[\Phi\!\left(\frac{\log y - \mu - \sigma^2}{\sigma}\right) + \Phi\!\left(\frac{\mu + \sigma^2}{\sigma \sqrt{2}}\right) - 1\right]$$

where $\Phi(\cdot)$ is the standard normal CDF.

**Training:** Minimize using `scipy.optimize.minimize` with the L-BFGS-B method. Initialize: $a = 0$, $b = 1$ (no location bias), $c = 0$, $d = 1$ (no dispersion bias).

**Validation:** LOSO-CV. Evaluate calibration via PIT (Probability Integral Transform) histograms. A well-calibrated model produces uniform PIT values.

### 3.4 Computing Bracket Probabilities

Given fitted parameters and a new prediction $(\hat{y}, \hat{\sigma})$:

1. Compute $\hat{\mu} = a + b \cdot \log(\hat{y})$ and $\hat{\sigma}_{\text{cal}} = \exp(c + d \cdot \log(\hat{\sigma}))$.
2. The predicted distribution is $Y \sim \mathcal{LN}(\hat{\mu}, \hat{\sigma}_{\text{cal}}^2)$.
3. Bracket probabilities:

$$p_k = P(Y \in B_k) = \Phi\!\left(\frac{\log u_k - \hat{\mu}}{\hat{\sigma}_{\text{cal}}}\right) - \Phi\!\left(\frac{\log l_k - \hat{\mu}}{\hat{\sigma}_{\text{cal}}}\right)$$

where $[l_k, u_k)$ are the bracket boundaries (with $l_1 = 0^+ \to -\infty$ on the log scale and $u_K = \infty$).

Explicitly:

| Bracket $B_k$ | $l_k$ | $u_k$ | $p_k$ formula |
|----------------|--------|--------|----------------|
| $<30$ | 0 | 30 | $\Phi\!\left(\frac{\log 30 - \hat{\mu}}{\hat{\sigma}_{\text{cal}}}\right)$ |
| $30$--$40$ | 30 | 40 | $\Phi\!\left(\frac{\log 40 - \hat{\mu}}{\hat{\sigma}_{\text{cal}}}\right) - \Phi\!\left(\frac{\log 30 - \hat{\mu}}{\hat{\sigma}_{\text{cal}}}\right)$ |
| $40$--$50$ | 40 | 50 | analogous |
| $50$--$60$ | 50 | 60 | analogous |
| $60$--$70$ | 60 | 70 | analogous |
| $70+$ | 70 | $\infty$ | $1 - \Phi\!\left(\frac{\log 70 - \hat{\mu}}{\hat{\sigma}_{\text{cal}}}\right)$ |

By construction, $\sum_{k=1}^{K} p_k = 1.0$ exactly (the CDF differences telescope).

### 3.5 Fallback: Direct Normal CDF

If EMOS fitting is numerically unstable or does not improve calibration in LOSO-CV, fall back to:

$$Y \sim \mathcal{N}(\hat{y}, \hat{\sigma}^2)$$

with bracket probabilities computed via:

$$p_k = \Phi\!\left(\frac{u_k - \hat{y}}{\hat{\sigma}}\right) - \Phi\!\left(\frac{l_k - \hat{y}}{\hat{\sigma}}\right)$$

Apply a minimum probability floor of $p_k \geq 0.005$ (0.5%) to prevent zero-probability brackets. Renormalize after flooring:

$$p_k' = \frac{\max(p_k, 0.005)}{\sum_{j=1}^{K} \max(p_j, 0.005)}$$

---

## 4. Brier Score Methodology

### 4.1 Definition

For a single market with $K$ brackets that resolves to bracket $k^*$, define the outcome vector $\mathbf{o} = (o_1, ..., o_K)$ where $o_k = \mathbb{1}[k = k^*]$.

The **multi-category Brier Score** for probability forecast $\mathbf{p} = (p_1, ..., p_K)$ is:

$$\text{BS}(\mathbf{p}, \mathbf{o}) = \frac{1}{K} \sum_{k=1}^{K} (p_k - o_k)^2$$

Lower is better. A perfect forecast (all probability on the correct bracket) gives $\text{BS} = 0$. The climatological forecast ($p_k = 1/K$ for all $k$) gives $\text{BS} = \frac{K-1}{K^2}$. With $K = 6$: $\text{BS}_{\text{clim}} = 5/36 \approx 0.139$.

### 4.2 Average Brier Score Over Multiple Weeks

Over $T$ resolved markets:

$$\overline{\text{BS}} = \frac{1}{T} \sum_{t=1}^{T} \text{BS}(\mathbf{p}_t, \mathbf{o}_t)$$

### 4.3 Market's Implied Brier Score

The market's "prediction" is the vector of implied probabilities $\mathbf{m}_t = (m_{1,t}, ..., m_{K,t})$ derived from midpoint prices (or last trade prices). Compute:

$$\overline{\text{BS}}_{\text{mkt}} = \frac{1}{T} \sum_{t=1}^{T} \text{BS}(\mathbf{m}_t, \mathbf{o}_t)$$

Our edge in Brier score terms is:

$$\Delta\text{BS} = \overline{\text{BS}}_{\text{mkt}} - \overline{\text{BS}}_{\text{model}}$$

Positive $\Delta\text{BS}$ means our model is better calibrated than the market.

### 4.4 Brier Skill Score

$$\text{BSS} = 1 - \frac{\overline{\text{BS}}_{\text{model}}}{\overline{\text{BS}}_{\text{clim}}}$$

where $\overline{\text{BS}}_{\text{clim}}$ is the Brier score of the climatological (uniform) forecast. BSS = 1 is perfect; BSS = 0 means no better than climatology; BSS < 0 means worse than climatology.

### 4.5 Statistical Test: Is Our Model Better Than the Market?

**Test:** Paired permutation test on per-week Brier score differences.

Define $d_t = \text{BS}(\mathbf{m}_t, \mathbf{o}_t) - \text{BS}(\mathbf{p}_t, \mathbf{o}_t)$ for each resolved week $t$.

- $H_0$: $E[d_t] = 0$ (model and market are equally calibrated).
- $H_1$: $E[d_t] > 0$ (model is better calibrated).

**Procedure:**

1. Compute observed $\bar{d} = \frac{1}{T} \sum_{t=1}^{T} d_t$.
2. Under $H_0$, randomly flip the signs of $d_t$ values. Repeat $B = 10{,}000$ times to build a null distribution of $\bar{d}^{*}$.
3. $p$-value $= P(\bar{d}^{*} \geq \bar{d})$.

Alternatively, use a **one-sided paired $t$-test** on $\{d_t\}$ if normality of $d_t$ is plausible (check with Shapiro-Wilk on the $d_t$ values):

$$t = \frac{\bar{d}}{s_d / \sqrt{T}}, \quad \text{df} = T - 1$$

### 4.6 Sample Size for Statistical Significance

For the paired $t$-test, the required number of weeks $T$ to detect a mean Brier score difference of $\delta$ with power $1 - \beta$ at significance level $\alpha$:

$$T = \left(\frac{(z_{\alpha} + z_{\beta}) \cdot \sigma_d}{\delta}\right)^2$$

**Estimated parameters** (from analogous prediction market studies):

- Expected edge: $\delta \approx 0.015$--$0.03$ (our model is 0.015--0.03 better in Brier score).
- Standard deviation of differences: $\sigma_d \approx 0.04$--$0.06$.
- Significance: $\alpha = 0.05$ (one-sided), $z_{\alpha} = 1.645$.
- Power: $1 - \beta = 0.80$, $z_{\beta} = 0.842$.

**Conservative estimate** ($\delta = 0.02$, $\sigma_d = 0.05$):

$$T = \left(\frac{(1.645 + 0.842) \times 0.05}{0.02}\right)^2 = \left(\frac{0.124}{0.02}\right)^2 = 6.2^2 \approx 39 \text{ weeks}$$

**Optimistic estimate** ($\delta = 0.03$, $\sigma_d = 0.04$):

$$T = \left(\frac{2.487 \times 0.04}{0.03}\right)^2 = 3.32^2 \approx 11 \text{ weeks}$$

**Practical implication:** One flu season (~26 weeks of active markets) is likely sufficient to detect a meaningful edge if one exists. Two seasons would provide definitive confirmation.

### 4.7 Decomposition: Reliability and Resolution

Decompose the Brier score into calibration (reliability) and sharpness (resolution) components:

$$\overline{\text{BS}} = \overline{\text{REL}} - \overline{\text{RES}} + \overline{\text{UNC}}$$

where:

- $\overline{\text{REL}} = \frac{1}{J} \sum_{j=1}^{J} n_j (\bar{p}_j - \bar{o}_j)^2$ (reliability; lower = better calibrated).
- $\overline{\text{RES}} = \frac{1}{J} \sum_{j=1}^{J} n_j (\bar{o}_j - \bar{o})^2$ (resolution; higher = more discriminating).
- $\overline{\text{UNC}} = \bar{o}(1 - \bar{o})$ (uncertainty; property of the outcome, not the forecast).

Bin forecasts into $J = 10$ equally-spaced bins of predicted probability. This decomposition tells us whether our edge comes from better calibration (reliability) or sharper predictions (resolution).

---

## 5. Fractional Kelly Criterion

### 5.1 Full Kelly Derivation

Consider a binary bet on bracket $B_k$. Our model assigns probability $p_k$; the market offers implied probability $m_k$ (the price of a "Yes" share). If we buy a Yes share at price $m_k$:

- **If $B_k$ is correct:** We receive $\$1$ and profit $1 - m_k$ per share.
- **If $B_k$ is wrong:** We lose $m_k$ per share.

The Kelly criterion maximizes the expected logarithmic growth of wealth:

$$f^* = \arg\max_f \; E[\log(1 + f \cdot R)]$$

where $R$ is the return per dollar wagered:

$$R = \begin{cases} \frac{1 - m_k}{m_k} & \text{with probability } p_k \\ -1 & \text{with probability } 1 - p_k \end{cases}$$

Note: $f$ is the fraction of total capital wagered (not the fraction of capital allocated).

The optimal Kelly fraction is:

$$f^* = \frac{p_k \cdot (1 - m_k) - (1 - p_k) \cdot m_k}{(1 - m_k)} = \frac{p_k - m_k}{1 - m_k}$$

This expression has a clean interpretation: the **edge** $(p_k - m_k)$ divided by the **odds** $(1 - m_k)$.

### 5.2 Fractional Kelly

Full Kelly is optimal for log-utility but produces extreme drawdowns. In practice, with model uncertainty, parameter estimation error, and limited data, we use a **fractional Kelly** multiplier $\gamma \in (0, 1)$:

$$f = \gamma \cdot \frac{p_k - m_k}{1 - m_k}$$

We set $\gamma = 0.20$ (20% Kelly).

#### Why 0.20x Specifically?

**Sensitivity analysis on Kelly fraction:**

Let the true edge be $p - m = 0.05$ and market price $m = 0.30$. Full Kelly: $f^* = 0.05 / 0.70 = 0.071$ (7.1% of capital).

| Kelly Fraction $\gamma$ | Bet Size (% capital) | Expected Growth Rate (% of optimal) | Max Drawdown (approx.) |
|--------------------------|----------------------|-------------------------------------|------------------------|
| 1.00 (full) | 7.1% | 100% | ~50%+ |
| 0.50 (half) | 3.6% | 75% | ~25% |
| 0.25 (quarter) | 1.8% | 44% | ~12% |
| **0.20** | **1.4%** | **36%** | **~10%** |
| 0.10 | 0.7% | 19% | ~5% |

The expected geometric growth rate of fractional Kelly is:

$$g(\gamma) = \gamma \cdot g^* - \frac{\gamma^2}{2} \cdot \text{Var}[R] \cdot (f^*)^2$$

Approximately: $g(\gamma) \approx g^* \cdot \gamma (2 - \gamma)$ where $g^* = g(1)$ is the full Kelly growth rate. At $\gamma = 0.20$: $g(0.20) \approx 0.20 \times 1.80 \times g^* = 0.36 g^*$.

**Rationale for 0.20x:** Our model probabilities carry substantial estimation uncertainty (trained on 5 seasons). The "effective" Kelly fraction when model probability has estimation error $\sigma_p$ is:

$$\gamma_{\text{eff}} = \frac{1}{1 + \sigma_p^2 / \text{edge}^2}$$

With $\sigma_p \approx 0.08$ (typical for our calibration uncertainty) and edge $\approx 0.04$: $\gamma_{\text{eff}} = 1 / (1 + 0.08^2 / 0.04^2) = 1/5 = 0.20$. This is not a coincidence; 20% Kelly approximately accounts for our model uncertainty.

### 5.3 Minimum Edge Threshold

Only trade when:

$$p_k - m_k \geq \tau_{\text{edge}} = 0.03$$

Rationale:
1. Transaction costs (spread + gas): approximately 1--2 cents per share.
2. Model calibration error: our bracket probabilities have a root-mean-square calibration error of ~2 cents (from LOSO-CV).
3. Combined: we need at least 3 cents of model edge to overcome costs and noise.

### 5.4 Handling Correlated Bets Across Adjacent Brackets

When we bet on multiple brackets simultaneously, the bets are **negatively correlated** (exactly one bracket pays out). The portfolio Kelly criterion for $K$ correlated bets solves:

$$\mathbf{f}^* = \arg\max_{\mathbf{f}} \; E\left[\log\left(1 + \sum_{k=1}^{K} f_k R_k\right)\right]$$

subject to $f_k \geq 0$ for all $k$.

For mutually exclusive outcomes with probabilities $\mathbf{p}$ and prices $\mathbf{m}$, the exact solution requires solving a constrained optimization. However, because we use 0.20x fractional Kelly (well below any single full Kelly bet), and because the brackets are mutually exclusive (at most one pays off), the simple per-bracket fractional Kelly is conservative:

$$f_k = 0.20 \cdot \max\!\left(0, \frac{p_k - m_k}{1 - m_k}\right) \cdot \mathbb{1}[p_k - m_k \geq 0.03]$$

This is conservative because negative correlation between winning bets means the portfolio variance is lower than the sum of individual variances, so per-bet Kelly slightly underinvests. In our setting this is fine -- it provides an additional safety margin.

**Total exposure constraint:** The total capital committed across all brackets must satisfy:

$$\sum_{k=1}^{K} f_k \cdot m_k \leq 0.15$$

(maximum 15% of capital in any single market event).

### 5.5 Ladder Strategy

The executor splits the primary bet across the target bracket and its two adjacent brackets. Let $f_k$ be the calculated bet fraction for the target bracket $k$.

$$f_k^{\text{primary}} = 0.70 \cdot f_k \qquad (\text{on bracket } B_k)$$
$$f_k^{\text{left}} = 0.15 \cdot f_k \qquad (\text{on bracket } B_{k-1}, \text{ if it exists and } p_{k-1} > m_{k-1})$$
$$f_k^{\text{right}} = 0.15 \cdot f_k \qquad (\text{on bracket } B_{k+1}, \text{ if it exists and } p_{k+1} > m_{k+1})$$

**Why ladder?**

1. **Point estimate uncertainty:** If our model predicts $\hat{y} = 48$, the true outcome at 51 is nearly as likely as 48. Both fall in adjacent brackets. Spreading bets captures value when the outcome is close to a bracket boundary.
2. **Market impact:** Placing the entire order in one bracket may move the price. Splitting across 3 brackets reduces market impact.
3. **Robustness:** If our point estimate is off by one bracket, we still profit on the 15% hedge.

**Constraint on adjacent bets:** Only place the adjacent leg if $p_{k\pm 1} > m_{k\pm 1}$ (our model assigns higher probability than the market). If an adjacent bracket has zero edge, reallocate that 15% back to the primary bracket.

### 5.6 Expected Growth Rate and Drawdown

**Expected log-growth per trade:**

$$g = \sum_{k=1}^{K} \left[ p_k \log\!\left(1 + f_k \cdot \frac{1 - m_k}{m_k}\right) + (1 - p_k) \log(1 - f_k) \right]$$

With $\gamma = 0.20$, typical edge $= 0.04$, price $m = 0.30$, we get $f = 0.20 \times 0.04 / 0.70 = 0.0114$ (1.14% of capital per trade).

- **Expected profit per trade:** $f \cdot \text{edge} = 0.0114 \times 0.04 = 0.046\%$ of capital.
- **Over 26 weekly trades:** Expected cumulative growth $\approx 1.2\%$ of capital.
- **Maximum drawdown (95th percentile):** With 0.20x Kelly and ~1% bets, the worst 5-trade losing streak costs approximately $5 \times 1.14\% = 5.7\%$ of capital. This is manageable for a $5,000 bankroll.

**Kelly ruin probability:** With fractional Kelly at $\gamma = 0.20$ and positive true edge, the theoretical probability of ruin is 0. However, if the true edge is zero or negative, the expected loss per trade is approximately equal to transaction costs (~1-2% per trade amount), leading to gradual attrition.

---

## 6. Edge Estimation and Sequential Monitoring

### 6.1 Realized Edge Estimation

After $T$ resolved trades, define the realized return for trade $t$:

$$r_t = \begin{cases} \frac{1 - m_{k_t}}{m_{k_t}} & \text{if bracket } k_t \text{ is correct} \\ -1 & \text{if bracket } k_t \text{ is incorrect} \end{cases}$$

weighted by size $s_t$ (dollars wagered on trade $t$). The realized edge per dollar is:

$$\hat{e} = \frac{\sum_{t=1}^{T} s_t \cdot r_t}{\sum_{t=1}^{T} s_t}$$

The implied edge in probability terms:

$$\hat{e}_{\text{prob}} = \frac{1}{T} \sum_{t=1}^{T} (\mathbb{1}[\text{win}_t] - m_{k_t})$$

This is the average difference between the realized hit rate and the market's implied probability.

### 6.2 Confidence Interval on Edge

Assuming trades are independent (approximately true for weekly markets):

$$\hat{e}_{\text{prob}} \pm z_{\alpha/2} \cdot \frac{\hat{\sigma}_e}{\sqrt{T}}$$

where:

$$\hat{\sigma}_e = \sqrt{\frac{1}{T-1} \sum_{t=1}^{T} \left((\mathbb{1}[\text{win}_t] - m_{k_t}) - \hat{e}_{\text{prob}}\right)^2}$$

### 6.3 Sample Size to Confirm Edge

To distinguish a true edge of $e > 0$ from zero with 95% confidence:

$$T \geq \left(\frac{z_{\alpha/2} \cdot \hat{\sigma}_e}{e}\right)^2$$

With typical values: $e = 0.04$, $\hat{\sigma}_e = 0.45$ (binary outcomes are high-variance):

$$T \geq \left(\frac{1.96 \times 0.45}{0.04}\right)^2 = 22.05^2 \approx 486 \text{ trades}$$

**This is a lot of trades.** With ~3 trades per week over a 26-week season, one season yields ~78 trades, far fewer than 486. This underscores two points:

1. **We cannot statistically confirm the edge within a single season using raw trade returns.** The variance of binary outcomes dominates.
2. **The Brier score test (Section 4) is more powerful** because it uses the full probability distribution, not just binary win/loss. We should monitor Brier scores as the primary edge metric, not P&L.

### 6.4 Sequential Monitoring: When to Stop

We use a **sequential probability ratio test (SPRT)** to continuously monitor whether the edge is real.

Define two hypotheses:
- $H_0$: True edge $e = 0$ (no edge; stop trading).
- $H_1$: True edge $e = e_1 = 0.03$ (minimum viable edge; continue trading).

The SPRT computes the log-likelihood ratio after each trade:

$$\Lambda_T = \sum_{t=1}^{T} \log \frac{P(\text{outcome}_t \mid e = e_1)}{P(\text{outcome}_t \mid e = 0)}$$

For each trade on bracket $k_t$ at market price $m_{k_t}$:

$$\log \frac{P(\text{outcome}_t \mid e = e_1)}{P(\text{outcome}_t \mid e = 0)} = \begin{cases} \log\!\frac{m_{k_t} + e_1}{m_{k_t}} & \text{if win} \\ \log\!\frac{1 - m_{k_t} - e_1}{1 - m_{k_t}} & \text{if loss} \end{cases}$$

**Decision boundaries:**

$$\Lambda_T \geq A = \log\!\frac{1 - \beta}{\alpha} \quad \Rightarrow \quad \text{Accept } H_1 \text{ (edge exists, keep trading)}$$

$$\Lambda_T \leq B = \log\!\frac{\beta}{1 - \alpha} \quad \Rightarrow \quad \text{Accept } H_0 \text{ (no edge, stop trading)}$$

With $\alpha = 0.05$, $\beta = 0.10$: $A = \log(0.90 / 0.05) = 2.89$ and $B = \log(0.10 / 0.95) = -2.25$.

**Expected sample sizes:**
- Under $H_1$ (edge exists): SPRT concludes in approximately 80--120 trades.
- Under $H_0$ (no edge): SPRT concludes in approximately 60--100 trades.

Both are achievable within one to two flu seasons.

### 6.5 Practical Monitoring Dashboard Metrics

Track weekly:

| Metric | Formula | Threshold |
|--------|---------|-----------|
| Cumulative P&L | $\sum_t s_t r_t$ | > 0 after 10+ trades |
| Win rate | $\frac{1}{T}\sum_t \mathbb{1}[\text{win}_t]$ | > average $\bar{m}$ (avg market price) |
| Model Brier score | Section 4.2 | < market Brier score |
| SPRT log-likelihood ratio | $\Lambda_T$ | Between $B$ and $A$ (continue), $\geq A$ (confirm edge), $\leq B$ (stop) |
| Calibration slope | Regress outcomes on model probabilities; slope $\approx 1$ if calibrated | $\in [0.7, 1.3]$ |
| Maximum drawdown | Largest peak-to-trough decline in cumulative P&L | < 20% of capital |

**Kill switch triggers (stop all trading immediately):**

1. SPRT ratio $\Lambda_T \leq B$ (formally reject the edge hypothesis).
2. Maximum drawdown exceeds 25% of initial capital ($\$1,250$).
3. Model Brier score exceeds market Brier score for 8 consecutive weeks.
4. Calibration slope outside $[0.3, 2.0]$ (model is severely miscalibrated).

---

## Appendix A: Full Pipeline Data Flow

```
                    +-----------------+
                    |  7 Real-Time    |
                    |  Signals        |
                    +--------+--------+
                             |
                             v
                    +--------+--------+
                    | Feature         |
                    | Engineering     |
                    | (21 features)   |
                    +--------+--------+
                             |
          +------------------+------------------+
          |                                     |
          v                                     v
+---------+---------+                 +---------+---------+
| Backfill Model    |                 | Elastic Net       |
| (Section 1)       |---bf_rate----->| (Section 2)       |
| log R ~ N(mu,s^2) |                | y_hat, sigma_hat  |
+-------------------+                +---------+---------+
                                                |
                                                v
                                      +---------+---------+
                                      | EMOS Calibration  |
                                      | (Section 3)       |
                                      | p_1, ..., p_K     |
                                      +---------+---------+
                                                |
                              +-----------------+-----------------+
                              |                                   |
                              v                                   v
                    +---------+---------+               +---------+---------+
                    | Brier Score       |               | Fractional Kelly  |
                    | Evaluation        |               | (Section 5)       |
                    | (Section 4)       |               | f_1, ..., f_K     |
                    +-------------------+               +---------+---------+
                                                                  |
                                                                  v
                                                        +---------+---------+
                                                        | Ladder Executor   |
                                                        | (Section 5.5)     |
                                                        | Trade orders      |
                                                        +---------+---------+
                                                                  |
                                                                  v
                                                        +---------+---------+
                                                        | Sequential        |
                                                        | Monitoring        |
                                                        | (Section 6)       |
                                                        +-------------------+
```

## Appendix B: Key Assumptions and Risks

| Assumption | Risk if Violated | Mitigation |
|------------|------------------|------------|
| FluSurv-NET revision patterns are stable across seasons | Backfill model is miscalibrated | LOSO-CV; conservative revision estimates; monitor in-season revisions vs. predictions |
| Signals are linearly predictive of next-week rate | Elastic net underperforms | Add polynomial/interaction features if LOSO-CV RMSE is poor; consider GAMs |
| Prediction errors are approximately log-normal | Bracket probabilities are miscalibrated | PIT histogram checks; fall back to empirical quantiles if needed |
| Market prices reflect crowd consensus probability | Edge is real and exploitable | Verify market has sufficient volume (> $5K daily) for price discovery |
| Weekly trades are approximately independent | Sequential tests are invalid | Account for autocorrelation by using Newey-West standard errors with lag 2 |
| Transaction costs are ~1-2 cents | True cost may eat the edge | Track realized spread and gas costs; adjust $\tau_{\text{edge}}$ upward if needed |

## Appendix C: Implementation Checklist

- [ ] `backfill.py`: Implement log-linear revision model per lag group; LOSO-CV evaluation
- [ ] `nowcast.py`: Feature engineering for 21 features; `ElasticNetCV` with LOSO folds
- [ ] `calibration.py`: EMOS log-normal fit via CRPS minimization; PIT histograms
- [ ] `kelly.py`: Fractional Kelly with edge threshold, ladder splitting, exposure cap
- [ ] `monitoring/`: Brier score tracker, SPRT monitor, drawdown circuit breaker
- [ ] `tests/`: Unit tests for each mathematical formula in this document against hand-computed examples

---

*End of specification.*
