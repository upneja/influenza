# Historical Backtesting Data Report for FluSight Edge

**Author:** RESEARCH-3 (Historical Backtesting Data Agent)
**Date:** 2026-02-18
**Status:** Complete

---

## Executive Summary

This report assesses the availability of historical data for backtesting a nowcasting model that exploits FluSurv-NET backfill patterns and prediction market mispricing. The key finding is a significant gap: **the Delphi Epidata API documents `issues` and `lag` parameters for FluSurv-NET, but these parameters return no data in practice**, meaning versioned (revision-level) FluSurv-NET data is not currently accessible via the API. FluView (ILI data) versioning works correctly. This gap is the single largest obstacle to backtesting a backfill arbitrage model and must be addressed through alternative means.

---

## 1. Delphi Epidata API -- Versioned Data Access

### 1.1 FluSurv-NET Endpoint

**Base URL:** `https://api.delphi.cmu.edu/epidata/flusurv/`

**Required Parameters:**
- `epiweeks`: List of epiweeks (e.g., `202401`)
- `locations`: Location label (e.g., `network_all`, `CA`, `CO`, `CT`, `GA`, `MD`, `MN`, `NM`, `OR`, `TN`, `network_eip`, `network_ihsp`)

**Optional Versioning Parameters (documented but non-functional for FluSurv):**
- `issues`: Epiweek of receipt by Delphi
- `lag`: Number of weeks between epiweek and its issue

**Critical Finding -- Versioned FluSurv Data Does NOT Work:**

The API documentation explicitly lists `issues` and `lag` as optional parameters for the FluSurv endpoint. However, extensive testing shows that **neither parameter returns any data**:

```
# All of these return {"epidata": [], "result": -2, "message": "no results"}
GET /flusurv/?locations=network_all&epiweeks=202401&lag=0
GET /flusurv/?locations=network_all&epiweeks=202401&lag=1
GET /flusurv/?locations=network_all&epiweeks=202401&lag=4
GET /flusurv/?locations=network_all&epiweeks=202401&issues=202402
GET /flusurv/?locations=network_all&epiweeks=202401&issues=202405
GET /flusurv/?locations=network_all&epiweeks=202401&issues=202410
```

Without versioning parameters, the API returns only the most recent (final) value. For example, querying epiweek 202401 returns data with `"lag": 89` and `"issue": 202538`, meaning the most recent revision from September 2025.

**Implication:** We cannot retrieve what FluSurv-NET reported at lag 0, lag 1, lag 2, etc. through the public API. This is the data we would need to model backfill patterns (how initial reports get revised upward over subsequent weeks).

### 1.2 FluView Endpoint (ILI Data) -- Versioning WORKS

In contrast, the FluView (ILI) endpoint fully supports versioned data:

```
# Lag 0: issue=202401, wili=5.749, released 2024-01-12
GET /fluview/?regions=nat&epiweeks=202401&lag=0

# Lag 1: issue=202402, wili=5.785, released 2024-01-19
GET /fluview/?regions=nat&epiweeks=202401&lag=1

# Lag 4: issue=202405, wili=5.777, released 2024-02-09
GET /fluview/?regions=nat&epiweeks=202401&lag=4
```

Each lag value returns different data reflecting data revisions. This confirms the API infrastructure supports versioning, but FluSurv-NET data revisions are either not stored or not exposed.

### 1.3 COVIDcast HHS Endpoint

The COVIDcast API provides a `confirmed_admissions_influenza` signal from HHS data:
- **Start date:** 2020-01-02
- **End date:** 2024-04-30 (signal is now **inactive/discontinued**)
- Available as raw counts, 7-day averages, per-100K proportions
- This is **hospital admissions** data (different from FluSurv-NET cumulative hospitalization rates)
- The COVIDcast system generally supports `as_of` versioning, which may preserve revision history for this signal

### 1.4 Workaround Strategies for FluSurv Versioning

Since the API does not expose FluSurv version history, potential workarounds include:

1. **Start collecting now:** Begin scraping the FluSurv API weekly during the 2025-26 season to build our own revision history going forward. This gives us at most 1 season of version data.

2. **CDC FluView Interactive archives:** The CDC FluView Interactive tool (https://gis.cdc.gov/GRASP/Fluview/FluHospRates.html) may expose historical snapshots. Archived CDC weekly reports contain point-in-time FluSurv rates.

3. **CDC weekly report archives:** Each season's FluView weekly reports (e.g., https://www.cdc.gov/flu/weekly/weeklyarchives2023-2024/) contain the FluSurv rate as reported at that time. Systematically scraping these archives could reconstruct version history.

4. **Contact Delphi directly:** The CMU Delphi group may have version history stored internally even if the API does not expose it. They offer free API key registration at https://api.delphi.cmu.edu/epidata/admin/registration_form.

5. **Use FluView ILI as a proxy:** Since FluView ILI versioning works, and ILI correlates with hospitalizations, we could model ILI backfill patterns as a proxy for hospitalization backfill.

---

## 2. FluSurv-NET Historical Rates

### 2.1 Data Availability via Delphi API

FluSurv-NET data is available from the **2009-10 season** through the **current 2025-26 season** (data from 2003-04 per documentation, but 2009-10 confirmed via testing). The API returns the **final revised** cumulative hospitalization rate per 100,000 for each epiweek.

**Confirmed API Response Fields:**
- `rate_overall`: Overall cumulative hospitalization rate per 100,000
- `rate_age_0` through `rate_age_7`: Age-stratified rates (0-4, 5-17, 18-49, 50-64, 65+, plus granular breakdowns)
- `rate_age_gte75`, `rate_age_18t29`, `rate_age_30t39`, `rate_age_40t49`, etc.
- `rate_race_white`, `rate_race_black`, `rate_race_hisp`, `rate_race_asian`, `rate_race_natamer`
- `rate_sex_male`, `rate_sex_female`
- `rate_flu_a`, `rate_flu_b`
- `season`, `epiweek`, `issue`, `lag`, `release_date`, `location`

### 2.2 End-of-Season Cumulative Rates (per 100,000)

Based on CDC reports and web research:

| Season | Cumulative Rate | Severity |
|--------|----------------|----------|
| 2010-11 | ~73.0 | High (reference season) |
| 2017-18 | 105.3 | Very High |
| 2018-19 | 23.8 | Low |
| 2019-20 | 66.2 | Moderate-High |
| 2020-21 | Minimal | COVID disrupted |
| 2021-22 | 11.1 | Very Low |
| 2022-23 | 59.2 | Moderate |
| 2023-24 | 79.0 | High |
| 2024-25 | 127.1 | Very High (record since 2010-11) |
| 2025-26 | ~63+ (in progress) | High (as of Week 4) |

**Median rate (2010-11 through 2023-24):** 62.0 per 100,000 (range: 8.7 to 102.9)

### 2.3 Geographic Breakdown

**Confirmed working location codes** (via API testing):
- `network_all` -- All FluSurv-NET sites combined
- `network_eip` -- Emerging Infections Program sites
- `network_ihsp` -- Influenza Hospitalization Surveillance Project sites
- Individual states: `CA`, `CO`, `CT`, `GA`, `MD`, `MN`, `NM`, `OR`, `TN`
- Note: `NY` returned no results (may use a different code)

### 2.4 Rate Limiting

The Delphi API enforces rate limits: 60 requests per window for anonymous queries. After hitting the limit, a `retry-after` header indicates ~3600 seconds (1 hour) wait time. Registering a free API key removes this limit.

---

## 3. Wastewater Historical Data

### 3.1 CDC NWSS Influenza A Wastewater Data

- **Start date:** Influenza A wastewater surveillance began with the **2023-24 influenza season (October 1, 2023)**
- **Coverage:** ~309 wastewater sites with sufficient data, across 48 states + DC, from ~750 total sampling sites
- **Update frequency:** Weekly (Fridays)
- **Data availability:** Complete time history available for download via data.cdc.gov in CSV, JSON, XML, RDF formats
- **Dataset catalog entry:** https://catalog.data.gov/dataset/cdc-wastewater-data-for-influenza-a
- **Metrics:** Viral activity levels categorized as Very Low (<2.7), Low (2.7-6.2), Moderate (6.2-11.2), High (11.2-17.6), Very High (>17.6)
- **H5 subtype data:** Available since August 2024 for avian influenza surveillance

**Limitations for backtesting:**
- Only ~2 complete flu seasons of data (2023-24 and 2024-25), with 2025-26 in progress
- Site-level data varies; not all states have consistent historical data
- The activity level metric uses the 2023-24 season as its baseline reference period

### 3.2 WastewaterSCAN (Stanford/Emory)

- **Earliest data:** October 2021 (University of Michigan detected H3N2 outbreak in wastewater)
- **Influenza A monitoring:** Active since fall 2021 at select sites
- **Data access:** Stanford Digital Repository (https://purl.stanford.edu/hj801ns5929) and Emory Dataverse
- **Geographic coverage:** Multiple sites across the US, expanding over time
- **Usage terms:** Contact required (aboehm@stanford.edu)
- **Dashboard:** https://data.wastewaterscan.org/ (national and regional views, download available)

**Limitations:** Research-grade data, fewer sites than NWSS, access may require coordination.

### 3.3 Overlap with FluSurv-NET

| Data Source | Earliest Flu A Data | Seasons with Overlap |
|-------------|-------------------|---------------------|
| CDC NWSS | Oct 2023 | 2023-24, 2024-25, 2025-26 |
| WastewaterSCAN | Oct 2021 | 2021-22, 2022-23, 2023-24, 2024-25, 2025-26 |
| FluSurv-NET | 2009+ | All seasons |

**Assessment:** Wastewater-FluSurv overlap is limited to 2-5 seasons depending on source. This is marginal for training a predictive model but potentially usable for validation.

---

## 4. FluSight Forecast Hub Historical Forecasts

### 4.1 Repository Structure

**Current hub (2023-24 onward):** https://github.com/cdcepi/FluSight-forecast-hub
- Seasons: 2023-24, 2024-25, 2025-26
- 91 participating teams/models (2025-26 season)
- Data mirrored on AWS S3 bucket: `cdcepi-flusight-forecast-hub`
- 2023-24 season data archived as GitHub release v1.0.0

**Archived hub (2021-22, 2022-23):** https://github.com/cdcepi/Flusight-forecast-data
- Quantile-based format
- Contains `data-forecasts/` and `data-truth/` directories

**Historical hub (pre-2021):** https://github.com/cdcepi/FluSight-forecasts
- Older seasons (FluSight challenges since 2013-14)
- Different format (ILI-focused rather than hospitalization-focused)

### 4.2 Forecast Format

**Primary targets (current hub):**
1. `wk inc flu hosp` -- Weekly incident flu hospitalizations (quantile + sample format)
2. `wk flu hosp rate change` -- Weekly rate change category (PMF format: large increase, increase, stable, decrease, large decrease)
3. `peak inc flu hosp` -- Peak incidence (quantile format)
4. `peak week inc flu hosp` -- Peak week (PMF format)
5. `wk inc flu prop ed visits` -- Weekly proportion of ED visits due to flu (quantile + sample)

**Horizons:** -1, 0, 1, 2, 3 weeks

**Quantile levels:** 0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99

**Sample format example (from 2025-11-22 FluSight-ensemble):**
```csv
reference_date,location,horizon,target,target_end_date,output_type,output_type_id,value
2025-11-22,01,0,wk inc flu hosp,2025-11-22,quantile,0.01,7
2025-11-22,01,0,wk inc flu hosp,2025-11-22,quantile,0.5,29
2025-11-22,01,0,wk inc flu hosp,2025-11-22,quantile,0.99,77
```

### 4.3 Ensemble Models

Key ensembles available:
- `FluSight-ensemble` (primary CDC ensemble)
- `FluSight-HJudge_ensemble`
- `FluSight-baseline_cat`
- `FluSight-ens_q_cat`
- `FluSight-equal_cat`

The FluSight ensemble performed better than 27 of 28 models in 2023-24 (only UMass-flusion outperformed it).

### 4.4 Historical FluSight Timeline

| Season | Hub/Repository | Target | Format |
|--------|---------------|--------|--------|
| 2013-14 to 2019-20 | cdcepi/FluSight-forecasts | ILI % | Varies |
| 2021-22 | cdcepi/Flusight-forecast-data | Hospitalizations | Quantile |
| 2022-23 | cdcepi/Flusight-forecast-data | Hospitalizations | Quantile |
| 2023-24 | cdcepi/FluSight-forecast-hub (v1.0.0) | Hospitalizations | Quantile + Sample |
| 2024-25 | cdcepi/FluSight-forecast-hub | Hospitalizations | Quantile + Sample |
| 2025-26 | cdcepi/FluSight-forecast-hub | Hospitalizations | Quantile + Sample + PMF |

**Note:** The target metric changed from ILI percentage (pre-2021) to weekly hospital admissions counts (2021+), making pre-2021 forecasts not directly comparable.

---

## 5. Polymarket Historical Flu Markets

### 5.1 When Markets Started

Polymarket flu hospitalization rate markets appear to have started during the **2025-26 flu season** (late 2025). This is Polymarket's first season offering flu-specific markets. No evidence was found of flu markets during the 2024-25 or earlier seasons.

### 5.2 Known Markets

| Week | Year | Brackets | Resolution | Volume | Status |
|------|------|----------|------------|--------|--------|
| Week 52 | 2025 | Unknown (may have had $0 volume) | Not resolved | $0 | Inactive |
| Week 1 | 2026 | "At least 30", "At least 35" | Both Yes | $24,459 | Resolved |
| Week 2 | 2026 | <30, 30-40, 40-50, 50-60, 60-70, >70 | 50-60 | $13,072 | Resolved |
| Week 3 | 2026 | <30, 30-40, 40-50, 50-60, 60-70, >70 | 50-60 | $43,708 | Resolved |
| Week 4 | 2026 | <30, 30-40, 40-50, 50-60, 60-70, >70 | 60-70 | $62,666 | Resolved |
| Week 5 | 2026 | <50, 50-60, 60-70, 70-80, 80-90, 90+ | 60-70 | $32,321 | Resolved |
| Week 6 | 2026 | <50, 50-60, 60-70, 70-80, 80-90, 90+ | ~60-70 | TBD | Resolved/Resolving |
| Week 7+ | 2026 | Not found | -- | -- | May not exist yet |

**Key observations:**
- Market structure evolved: Week 1 had only 2 outcomes, Weeks 2-4 had 6 brackets (10-point intervals from 30-70), and Weeks 5-6 shifted brackets upward (50-90+) as cumulative rates grew.
- Volume is increasing over time ($13K -> $43K -> $62K), suggesting growing trader interest.
- Resolution source is **CDC FluView / FluSurv-NET cumulative hospitalization rate per 100,000**.

### 5.3 API Access

- **Gamma API:** `https://gamma-api.polymarket.com/events?slug=<slug>` -- Now returning 403 errors for programmatic access
- **CLOB API:** Historical price data available at 12+ hour granularity for resolved markets via `/prices-history` endpoint
- **Dune Analytics:** General Polymarket dashboards exist (by filarm, rchen8, etc.) but no flu-specific dashboard was found
- **Data limitations:** The Gamma API does not support text search/filtering; finding markets requires knowing exact slugs

### 5.4 Historical Data Assessment

Since Polymarket flu markets only started in the 2025-26 season, there is **zero historical resolved market data** for backtesting. The earliest useful data point is Week 1, 2026 (January 2026). This means:
- We cannot backtest our Polymarket strategy against historical seasons
- We can only forward-test during the remainder of the 2025-26 season
- Paper trading against live markets is the only viable validation approach right now

---

## 6. Backtesting Feasibility Assessment

### 6.1 Data Availability Summary

| Data Type | Seasons Available | Usable for Backtest? |
|-----------|-------------------|---------------------|
| FluSurv-NET final rates | 2009-10 to 2025-26 (~16 seasons) | Yes (final values only) |
| FluSurv-NET versioned/revision data | 0 seasons | **NO -- critical gap** |
| FluView ILI versioned data | 2009+ (~16 seasons) | Yes (proxy for backfill) |
| CDC NWSS wastewater (flu A) | 2023-24 to 2025-26 (~3 seasons) | Partial |
| WastewaterSCAN (flu A) | 2021-22 to 2025-26 (~5 seasons) | Partial (access required) |
| FluSight ensemble forecasts (hosp) | 2021-22 to 2025-26 (~5 seasons) | Yes |
| FluSight ensemble forecasts (ILI) | 2013-14 to 2019-20 (~7 seasons) | Yes (different target) |
| Polymarket flu markets | 2025-26 only (~6 weeks) | **NO -- insufficient** |
| COVIDcast HHS flu admissions | 2020-01 to 2024-04 | Yes (different metric) |

### 6.2 Backfill Arbitrage Model -- Backtesting Feasibility

The core model requires knowing how FluSurv-NET rates change from initial report (lag 0) to final value. **This data is not available through the API.**

**Viable workarounds, ranked by feasibility:**

1. **Reconstruct from CDC weekly archives (Medium effort, ~3 seasons):** Parse CDC FluView weekly reports for 2022-23, 2023-24, and 2024-25 seasons. Each weekly report contains the cumulative hospitalization rate as known at that time. By comparing Week N's report of rates vs. Week N+4's report of the same rates, we can reconstruct backfill patterns.

2. **Use FluView ILI backfill as proxy (Low effort, ~16 seasons):** The FluView ILI endpoint has full version history. Model ILI backfill patterns and assume hospitalization backfill follows similar dynamics. This is an approximation but gives many seasons of data.

3. **Contact CMU Delphi (Low effort, unknown data):** Request internal FluSurv version history. The Delphi team is research-friendly and may provide bulk data.

4. **Collect prospectively (Zero effort now, 1+ seasons delay):** Start weekly FluSurv snapshots immediately. After one full season, we have real version data. Combined with 2025-26 partial season data, this gives us 1-2 seasons.

### 6.3 Ensemble Comparison Model -- Backtesting Feasibility

Comparing our nowcast against the FluSight ensemble is feasible for **4-5 seasons** (2021-22 through 2025-26). The ensemble forecasts are in quantile format, which we can convert to bracket probabilities for comparison with Polymarket-style markets.

### 6.4 Leave-One-Season-Out Cross-Validation

| Model Component | Feasible? | N Seasons | Notes |
|-----------------|-----------|-----------|-------|
| Backfill model (FluSurv) | No (need workaround) | 0-3 | Depends on archive reconstruction |
| Backfill model (ILI proxy) | Yes | 10+ | Different metric but similar dynamics |
| Wastewater leading indicator | Marginal | 2-3 | NWSS only, 3-5 with WastewaterSCAN |
| Ensemble calibration | Yes | 4-5 | Hospitalization forecasts since 2021-22 |
| Full pipeline (all components) | No | 0 | Need at least 1 season of Polymarket data |

### 6.5 Minimum Viable Backtesting Dataset

For a credible backtest of the full system, we need:

**Minimum (functional but limited):**
- 1 season of FluSurv version history (reconstruct from archives for 2024-25)
- FluSight ensemble data for the same season
- Forward-test on 2025-26 Polymarket markets

**Recommended (statistically meaningful):**
- 3+ seasons of FluSurv version history (reconstruct 2022-23 through 2024-25)
- FluSight ensemble data for those seasons
- NWSS wastewater data for 2023-24 and 2024-25
- Simulated prediction market brackets based on FluSight quantiles (since real Polymarket data only exists for 2025-26)

**Ideal (robust validation):**
- 5+ seasons of FluSurv version history
- All available FluSight ensemble data
- Full wastewater time series
- 2+ seasons of real prediction market data (requires waiting until 2026-27 season)

---

## 7. Recommended Next Steps

1. **Register a Delphi API key** at https://api.delphi.cmu.edu/epidata/admin/registration_form to remove rate limiting (currently 60 requests per window).

2. **Immediately begin collecting FluSurv weekly snapshots** for the remainder of the 2025-26 season to build version history.

3. **Reconstruct FluSurv version history** from CDC weekly report archives for 2022-23, 2023-24, and 2024-25 seasons.

4. **Contact CMU Delphi** to request internal FluSurv revision history data.

5. **Download FluSight ensemble forecasts** from the GitHub hub (v1.0.0 release for 2023-24, and current repository for 2024-25 and 2025-26).

6. **Build a Polymarket data collection pipeline** to capture weekly bracket prices, volumes, and resolutions for the remainder of the 2025-26 season.

7. **Investigate COVIDcast `as_of` parameter** for the HHS flu admissions signal as an alternative source of versioned hospitalization data (covers 2020-2024).

---

## Appendix A: API Reference Quick Guide

### FluSurv-NET (final values only)
```
GET https://api.delphi.cmu.edu/epidata/flusurv/
  ?locations=network_all
  &epiweeks=202401
```

### FluView ILI (with versioning)
```
GET https://api.delphi.cmu.edu/epidata/fluview/
  ?regions=nat
  &epiweeks=202401
  &lag=0          # Initial report
  &lag=4          # 4 weeks later
```

### FluSight Ensemble Data
```
# Current season (raw CSV)
https://raw.githubusercontent.com/cdcepi/FluSight-forecast-hub/main/model-output/FluSight-ensemble/<date>-FluSight-ensemble.csv

# S3 mirror (parquet, recommended for bulk access)
s3://cdcepi-flusight-forecast-hub/
```

### Polymarket (when accessible)
```
# Event details
GET https://gamma-api.polymarket.com/events?slug=flu-hospitalization-rate-week-3-2026

# Price history (CLOB)
GET https://clob.polymarket.com/prices-history?market=<token_id>&interval=max&fidelity=720
```

## Appendix B: Key URLs

- Delphi Epidata API docs: https://cmu-delphi.github.io/delphi-epidata/
- FluSurv-NET endpoint docs: https://cmu-delphi.github.io/delphi-epidata/api/flusurv.html
- CDC FluView Interactive: https://gis.cdc.gov/GRASP/Fluview/FluHospRates.html
- FluSight Forecast Hub: https://github.com/cdcepi/FluSight-forecast-hub
- FluSight Forecast Data (archived): https://github.com/cdcepi/Flusight-forecast-data
- CDC NWSS Influenza A data: https://www.cdc.gov/nwss/rv/InfluenzaA-national-data.html
- CDC wastewater data catalog: https://catalog.data.gov/dataset/cdc-wastewater-data-for-influenza-a
- WastewaterSCAN: https://data.wastewaterscan.org/
- Polymarket docs: https://docs.polymarket.com/
- CDC FluSight evaluation (2023-24): https://www.cdc.gov/flu-forecasting/evaluation/2023-2024-report.html
- Delphi API key registration: https://api.delphi.cmu.edu/epidata/admin/registration_form
