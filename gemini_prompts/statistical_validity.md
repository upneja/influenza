# Vetting Request: Statistical Validity of FluSurv-NET Prediction Strategy

## Background

We are building a quantitative trading system ("Project FluSight Edge") that bets on Polymarket prediction markets for U.S. influenza hospitalization rates. The markets resolve based on CDC FluSurv-NET cumulative hospitalization rate brackets (e.g., 20-25 per 100,000, 25-30 per 100,000, etc.) reported at the end of each flu season.

Our core thesis is that FluSurv-NET preliminary hospitalization numbers are systematically revised upward as lagging hospitals submit data over subsequent weeks, and that Polymarket traders anchor on the preliminary (lower) numbers. We call this "backfill arbitrage." We fuse 7 real-time surveillance signals to predict the final (post-revision) bracket: wastewater influenza RNA concentrations (NWSS/WastewaterSCAN), emergency department syndromic surveillance visits (NSSP), Google Trends for flu-related queries, antiviral prescription volume (GoodRx Tamiflu tracker), CDC FluSight ensemble model forecasts, Delphi Epidata versioned/as-of data for modeling revision patterns, and ILINet outpatient influenza-like illness rates.

Our model is an elastic net regression trained on approximately 5 seasons of historical data (2017-2018 through 2023-2024, excluding the anomalous 2020-2021 COVID season). We size positions using a fractional Kelly criterion at 0.20x (one-fifth Kelly).

We need an independent, evidence-based assessment of whether this strategy is statistically sound. Please answer each question below with specific citations to peer-reviewed literature, CDC technical documentation, or authoritative data sources.

## Questions

### 1. FluSurv-NET Revision Magnitudes
We claim that FluSurv-NET cumulative hospitalization rates are revised upward by 15-30% from the initial preliminary report to the final report, due to reporting lag from participating hospitals. Is this accurate? What do CDC technical notes and published analyses say about the typical magnitude and direction of FluSurv-NET data revisions? Are there specific seasons where revisions were substantially larger or smaller? Is the revision pattern consistent enough across seasons to be exploitable, or is the variance in revision magnitude itself a major risk?

### 2. Elastic Net Regression with Limited Training Data
We are using elastic net regression (a combination of L1 and L2 regularization) to predict hospitalization bracket outcomes from 7 input signals. Our training set covers approximately 5 flu seasons (roughly 130-150 weekly observations, though not all signals are available for all weeks). Is elastic net an appropriate choice for this sample size and feature count? What is the realistic risk of overfitting with 7 predictors and ~5 seasons of data? Would simpler approaches (e.g., ridge regression, or even a 2-3 variable OLS model selected by domain expertise) be more robust given data limitations? What cross-validation strategy is recommended for time-series epidemiological data of this length (e.g., leave-one-season-out)?

### 3. Kelly Criterion Sizing
We plan to size bets at 0.20x Kelly fraction (one-fifth of the Kelly-optimal bet size). Given that our model has high parameter uncertainty (small training set, potential regime changes between flu seasons, novel signal combinations), is 0.20x Kelly conservative enough? What does the literature on fractional Kelly betting say about appropriate fractions when model confidence is low? At what level of edge estimation error does Kelly sizing become worse than flat betting?

### 4. Sample Size for Skill Detection
Polymarket flu bracket markets resolve on a weekly or seasonal basis. How many resolved predictions (weeks of trading data) would we need to statistically distinguish genuine forecasting skill from luck at a significance level of p < 0.05? Please consider this in the context of categorical bracket predictions (multinomial outcomes with 5-8 brackets) rather than simple binary bets. What is the minimum track record length that would be convincing?

### 5. Realistic Brier Score Improvement
What Brier score improvement over naive baselines (e.g., linear extrapolation of current trends, or simply using the most recent FluSight ensemble forecast without modification) is realistically achievable by fusing multiple surveillance signals? Are there published evaluations of multi-signal flu forecasting models that report Brier scores or log scores we can benchmark against? Specifically, does adding wastewater data, Google Trends, and antiviral prescription data to FluSight ensemble forecasts produce statistically significant forecast improvements?

### 6. Wastewater-to-Hospitalization Prediction
Are there published studies that specifically use wastewater influenza RNA concentrations to predict FluSurv-NET hospitalization rates (not just ILI rates or case counts)? What lead time do wastewater signals provide over hospitalization reports? What is the documented correlation strength (R-squared or similar metric) between wastewater RNA levels and subsequent hospitalization rates at the national or HHS-region level?

## Response Format

For each question, please provide: (a) a direct answer, (b) supporting evidence with specific citations (author, year, journal/source, and DOI or URL where available), and (c) an honest assessment of how confident you are in the answer given available evidence. If a claim we are making is wrong or unsupported, say so directly.
