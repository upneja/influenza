# API Validation Report — Project FluSight Edge

**Agent:** RESEARCH-1 (API Validation)
**Date:** 2026-02-18
**Status:** Complete

---

## Executive Summary

Of the 8 API sources tested, **4 are fully operational and provide high-quality structured data** (Delphi Epidata FluSurv/FluView, CDC NWSS Wastewater, CDC FluSight Forecast Hub). Polymarket has functional APIs but **no active flu hospitalization markets currently exist**. Google Trends requires the `pytrends` library (not installed) and the direct API aggressively rate-limits. WastewaterSCAN has no public API. GoodRx data is embedded in Datawrapper iframes and is not programmatically accessible.

---

## 1. Delphi Epidata API

**Base URL:** `https://api.delphi.cmu.edu/epidata`
**Auth Required:** None (public, no API key needed)
**Rate Limits:** Not documented; no rate limiting encountered during testing
**Status: FULLY OPERATIONAL — PRIMARY DATA SOURCE**

### 1a. FluSurv-NET (`/flusurv/`)

**URL Tested:**
```
https://api.delphi.cmu.edu/epidata/flusurv/?locations=network_all&epiweeks=202605
```

**HTTP Status:** 200
**Content-Type:** `application/json`
**Response Format:** JSON with `epidata` array, `result` (1=success, -2=no results), `message`

**Sample Response (epiweek 202605):**
```json
{
  "epidata": [{
    "release_date": "2026-02-13",
    "location": "network_all",
    "season": "2025-26",
    "issue": 202606,
    "epiweek": 202605,
    "lag": 1,
    "rate_overall": 2.3,
    "rate_age_0": 1.6,
    "rate_age_1": 0.5,
    "rate_age_2": 0.7,
    "rate_age_3": 1.9,
    "rate_age_4": 7.3,
    "rate_age_5": 4.7,
    "rate_age_6": 9.0,
    "rate_age_7": 19.8,
    "rate_age_lt18": 1.2,
    "rate_age_gte18": 2.6,
    "rate_race_white": 2.3,
    "rate_race_black": 2.9,
    "rate_race_hisp": 1.6,
    "rate_race_asian": 1.5,
    "rate_race_natamer": 2.6,
    "rate_sex_male": 2.3,
    "rate_sex_female": 2.3,
    "rate_flu_a": 2.0,
    "rate_flu_b": 0.3
  }],
  "result": 1,
  "message": "success"
}
```

**Available Locations (state-level, tested for epiweek 202605):**

| Location | Rate Overall |
|----------|-------------|
| `network_all` | 2.3 |
| `CA` | 3.1 |
| `CO` | 2.0 |
| `CT` | 1.3 |
| `GA` | 1.9 |
| `MD` | 1.4 |
| `MI` | 3.2 |
| `MN` | 0.9 |
| `NM` | 2.7 |
| `OR` | 5.4 |
| `TN` | 3.5 |
| `UT` | 2.1 |

Note: NY, IA, OH not returned — they may use different codes or not be available at this time. `EIP` and `IHSP` network-level codes did not return separate records (only `network_all` works as an aggregate).

**Key Parameters:**
- `locations` — Comma-separated: `network_all`, state abbreviations (CA, CO, CT, GA, MD, MI, MN, NM, OR, TN, UT)
- `epiweeks` — Single week (202605) or range (202501-202510)
- `issues` — For versioned data (see below)
- `lag` — Integer lag value

**Versioned Data / Revision History:**

**IMPORTANT FINDING:** The `issues` parameter does NOT work for FluSurv. All queries with `issues=XXXXXX` returned `"no results"` (-2). However, FluSurv data is inherently versioned through the `issue` and `lag` fields in the response. Each record includes:
- `issue`: The epiweek when the data was released
- `lag`: How many weeks after the epiweek the data was issued
- `release_date`: The actual calendar date of release

To track revisions, you must query the same epiweek over time and compare `rate_overall` values across different `issue` dates. Since `issues` filtering is broken for FluSurv, the practical approach is to **poll the endpoint weekly and store snapshots**, then compute deltas offline.

### 1b. FluView / ILINet (`/fluview/`)

**URL Tested:**
```
https://api.delphi.cmu.edu/epidata/fluview/?regions=nat&epiweeks=202605
```

**HTTP Status:** 200
**Content-Type:** `application/json`

**Sample Response:**
```json
{
  "epidata": [{
    "release_date": "2026-02-13",
    "region": "nat",
    "issue": 202605,
    "epiweek": 202605,
    "lag": 0,
    "num_ili": 109531,
    "num_patients": 2580915,
    "num_providers": 4217,
    "wili": 4.59299,
    "ili": 4.24388
  }],
  "result": 1,
  "message": "success"
}
```

**Versioned Data — WORKING for FluView:**

The `issues` parameter works correctly for FluView. Tested revision history for epiweek 202501:

| Issue | Lag | ILI (%) | wILI (%) | num_ili |
|-------|-----|---------|----------|---------|
| 202502 | 1 | 6.17074 | 6.32776 | 163,686 |
| 202503 | 2 | 6.15326 | 6.29946 | 164,183 |
| 202504 | 3 | 6.17991 | 6.33203 | 164,291 |
| 202505 | 4 | 6.17960 | 6.33180 | 164,294 |

Revision pattern: ILI rates stabilize after ~3 weeks (lag 3+), with the biggest revisions between lag 0 and lag 1. The `num_providers` also increases as late reporters file.

The `lag` parameter also works: `lag=0` returns only the first-reported value for each epiweek.

**HHS Regions (all 10 working):**
```
regions=hhs1,hhs2,...,hhs10
```
Returns ILI and wILI for each HHS region. Also supports `regions=nat` for national.

**Key Fields:**
- `wili`: Weighted ILI percentage (weighted by state population)
- `ili`: Unweighted ILI percentage
- `num_ili`: Number of ILI cases
- `num_patients`: Total patient visits
- `num_providers`: Number of reporting providers
- `num_age_0` through `num_age_5`: Age-stratified counts

### 1c. Delphi Google Health Trends (`/ght/`)

**Status: REQUIRES AUTH**

```
HTTP 401: "Provided API key does not have access to this endpoint.
Please contact delphi-support+privacy@andrew.cmu.edu."
```

This endpoint proxies Google Health Trends data but requires a Delphi API key with special permissions. Contact `delphi-support+privacy@andrew.cmu.edu` to request access.

### 1d. Alternate Endpoint Format

The older `api.php` format also works:
```
https://api.delphi.cmu.edu/epidata/api.php?endpoint=flusurv&locations=network_all&epiweeks=202605
```
Returns identical data. Both formats are supported.

---

## 2. WastewaterSCAN

**URL:** `https://data.wastewaterscan.org`
**Status: NO PUBLIC API — DASHBOARD ONLY**

### Findings

- The site is a Nuxt.js (Vue) single-page application serving a data dashboard
- No `/api`, `/api/v1`, `/dataset`, or `/downloads` endpoints exist (all return 404)
- JavaScript bundles were inspected but no obvious API base URLs were found
- The dashboard renders charts client-side from data loaded via internal JS bundles

### Data Available (via dashboard, not API)

- IAV (Influenza A Virus) RNA concentration data by site
- Site-level geographic granularity (individual wastewater treatment plants)
- Time series charts visible in browser

### Alternatives

1. **CDC NWSS** (see Section 3) — provides state-level and regional Influenza A wastewater viral activity levels via downloadable CSV/JSON
2. **Biobot Analytics** — `https://biobot.io/data/` — may have public data downloads
3. **Manual browser scraping** — would require Selenium/Playwright to interact with the Nuxt.js SPA, which is fragile and not recommended
4. **Contact Stanford/Verily** — WastewaterSCAN is a Stanford/Emory/Verily project; they may offer data access for research purposes

---

## 3. CDC NWSS Wastewater (Influenza A)

**Base URL:** `https://www.cdc.gov/nwss/rv/`
**Auth Required:** None
**Status: FULLY OPERATIONAL — HIGH-QUALITY DATA**

### Data Endpoints Discovered

The CDC NWSS pages use a dashboard framework with JSON configuration files that reference underlying data URLs. All data is publicly downloadable.

#### 3a. State-Level Map Data (CSV)

**URL:**
```
https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluastatemapDL.csv
```

**HTTP Status:** 200
**Format:** CSV

**Sample Data:**
```csv
State/Territory,State_Abbreviation,WVAL_Category,Number_of_Sites,Time_Period,Coverage,date_updated
"Alabama","AL","High","6","February 01, 2026 - February 07, 2026",,"2026-02-12T07:44:56.590592Z"
"California","CA","High","80","February 01, 2026 - February 07, 2026",,"2026-02-12T07:44:56.590592Z"
"Colorado","CO","Very Low","22","February 01, 2026 - February 07, 2026",,"2026-02-12T07:44:56.590592Z"
```

**Fields:** State/Territory, State_Abbreviation, WVAL_Category (Minimal/Very Low/Low/Moderate/High/Very High), Number_of_Sites, Time_Period, Coverage, date_updated

**Coverage:** All 50 states + DC + territories. Categories: Minimal, Very Low, Low, Moderate, High, Very High.

#### 3b. Regional Activity Level Time Series (CSV)

**URL:**
```
https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluaregionalactivitylevelDL.csv
```

**HTTP Status:** 200
**Format:** CSV

**Sample Data:**
```csv
Week_Ending_Date,Midwest_WVAL,National_WVAL,Northeast_WVAL,South_WVAL,West_WVAL,date_updated
"2026-01-31","7.517","5.491","4.004","6.217","4.766","2026-02-12T07:56:30.859Z"
"2025-12-20","5.317","6.786","11.056","7.338","6.233","2026-02-12T07:56:30.859Z"
"2025-02-15","20.040","16.960","19.301","14.214","14.619","2026-02-12T07:56:30.859Z"
```

**WVAL** = Wastewater Viral Activity Level (numeric, continuous scale). Historical data goes back to at least 2022.

**Activity Level Thresholds (from config):**
- Minimal: <= 2.7
- Low: 2.7 - 6.2
- Moderate: 6.2 - 11.2
- High: 11.2 - 16.4
- Very High: > 16.4

#### 3c. JSON Data Endpoints

Also available in JSON format:
- `https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluanationaldatabites.json` — National summary
- `https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluastatemap.json` — State map data
- `https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluaregionalactivitylevel.json` — Regional time series

Note: The JSON endpoints returned empty responses during testing (may be access-controlled or require specific headers). The CSV endpoints work reliably.

#### 3d. Update Frequency

Data is updated weekly (most recent `date_updated`: 2026-02-12). The most recent data covers the week ending February 07, 2026. There is a ~2 week lag noted in the dashboard configs.

---

## 4. Google Trends

**Status: REQUIRES `pytrends` LIBRARY (not installed) — RATE LIMITED VIA DIRECT API**

### Findings

- The `pytrends` Python library is not currently installed in the environment
- Direct Google Trends API requests return **HTTP 429 (Too Many Requests)** immediately
- The `/trends/api/dailytrends` endpoint returned 404
- The `/trends/api/explore` endpoint returned 429 (rate limited)

### Delphi Google Health Trends Proxy

The Delphi Epidata API has a `/ght/` endpoint that proxies Google Health Trends data, but it **requires an authorized API key** (HTTP 401). Contact `delphi-support+privacy@andrew.cmu.edu`.

### Recommended Approach

1. **Install pytrends:** `pip install pytrends` — this library handles session management and rate limiting
2. **Use cautiously:** Google aggressively rate-limits; add 10-60 second delays between requests
3. **Terms to query:** "flu symptoms", "tamiflu side effects", "flu rapid test near me"
4. **State-level granularity:** Supported via `geo='US-CA'` parameter in pytrends
5. **Alternative:** Use Delphi's Google Symptoms signal via covidcast API (tested `google-symptoms` source — returned no results for recent dates, may be discontinued)

### Expected pytrends Usage

```python
from pytrends.request import TrendReq
pytrends = TrendReq(hl='en-US', tz=360)
pytrends.build_payload(['flu symptoms'], timeframe='today 3-m', geo='US')
data = pytrends.interest_over_time()  # Returns pandas DataFrame
```

State-level for FluSurv-NET states:
```python
pytrends.build_payload(['flu symptoms'], timeframe='today 3-m', geo='US-CA')
```

---

## 5. CDC FluSight Forecast Hub

**URL:** `https://github.com/cdcepi/FluSight-forecast-hub`
**Auth Required:** None (public GitHub repo)
**Status: FULLY OPERATIONAL — RICH FORECAST DATA**

### Repository Structure

```
cdcepi/FluSight-forecast-hub/
├── hub-config/
│   ├── tasks.json          # Forecast format specification
│   ├── target-data.json    # Target data schema
│   ├── admin.json
│   └── model-metadata-schema.json
├── model-output/           # 30+ contributing models
│   ├── FluSight-ensemble/  # CDC official ensemble
│   ├── FluSight-baseline/
│   ├── Google_SAI-FluBoostQR/
│   ├── CFA_Pyrenew-Pyrenew_H_Flu/
│   └── ... (30+ more)
├── target-data/
│   ├── time-series.csv     # Historical actuals (versioned)
│   ├── oracle-output.csv
│   └── target-hospital-admissions.csv
├── ensemble-weights/
└── auxiliary-data/
```

### Forecast Output Types

The hub supports **5 distinct targets** with different output types:

| Target | Output Type | Description |
|--------|------------|-------------|
| `wk flu hosp rate change` | PMF | Categorical: large_decrease, decrease, stable, increase, large_increase |
| `wk inc flu hosp` | quantile + sample | Weekly incident flu hospitalizations (count) |
| `peak inc flu hosp` | quantile | Season peak hospitalization count |
| `peak week inc flu hosp` | PMF | Which week will the peak occur |
| `wk inc flu prop ed visits` | quantile + sample | Weekly proportion of ED visits for flu |

### Sample Ensemble Forecast (2026-02-14)

**File:** `model-output/FluSight-ensemble/2026-02-14-FluSight-ensemble.csv`

**Format:** CSV with columns: `reference_date, location, horizon, target, target_end_date, output_type, output_type_id, value`

**Quantile forecasts (wk inc flu hosp, location 01/Alabama, horizon 0):**
```csv
2026-02-14,01,0,wk inc flu hosp,2026-02-14,quantile,0.01,157
2026-02-14,01,0,wk inc flu hosp,2026-02-14,quantile,0.025,180
2026-02-14,01,0,wk inc flu hosp,2026-02-14,quantile,0.5,337    # median
2026-02-14,01,0,wk inc flu hosp,2026-02-14,quantile,0.975,505
2026-02-14,01,0,wk inc flu hosp,2026-02-14,quantile,0.99,539
```

**23 quantile levels:** 0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99

**PMF category forecasts (wk flu hosp rate change):**
```csv
2026-02-14,01,0,wk flu hosp rate change,2026-02-14,pmf,large_decrease,0.187
2026-02-14,01,0,wk flu hosp rate change,2026-02-14,pmf,decrease,0.230
2026-02-14,01,0,wk flu hosp rate change,2026-02-14,pmf,stable,0.262
2026-02-14,01,0,wk flu hosp rate change,2026-02-14,pmf,increase,0.157
2026-02-14,01,0,wk flu hosp rate change,2026-02-14,pmf,large_increase,0.163
```

**Horizons:** -1, 0, 1, 2, 3 (nowcast + up to 3 weeks ahead)

**Locations:** All US states by FIPS code (01=Alabama, 02=Alaska, ..., 56=Wyoming, US=national)

### Target Data (Actuals)

**File:** `target-data/time-series.csv`

```csv
as_of,target,target_end_date,location,location_name,observation,weekly_rate
2023-09-23,"wk inc flu hosp",2022-02-12,"01","Alabama",10,0.197
2023-09-23,"wk inc flu hosp",2022-02-12,"06","California",36,0.093
```

Includes `as_of` field for versioned actuals — critical for evaluating revision patterns.

### Key Findings

- **Bracket-style forecasts:** YES, via PMF output type for `wk flu hosp rate change` (5 categories)
- **Full distributional forecasts:** YES, via 23 quantile levels
- **Point estimates:** Extractable as median (quantile 0.5)
- **30+ contributing models** available for meta-analysis
- **Versioned target data** supports backtesting against as-reported values
- **Updated weekly** on Saturdays; latest file is 2026-02-14
- **Active season:** 2025-2026 season data from 2025-11-22 through 2026-05-23

---

## 6. Polymarket Gamma API

**Base URL:** `https://gamma-api.polymarket.com`
**Auth Required:** None
**Status: API WORKS — BUT NO FLU HOSPITALIZATION MARKETS FOUND**

### Endpoints Tested

**Markets Search:**
```
GET https://gamma-api.polymarket.com/markets?closed=false&limit=10&search=flu
```
**HTTP Status:** 200
**Content-Type:** `application/json`

**Events Search:**
```
GET https://gamma-api.polymarket.com/events?closed=false&limit=20&search=flu
```
**HTTP Status:** 200

### Search Results

Extensive searches were conducted with the following terms:
- `flu`, `influenza`, `hospitalization`, `H5N1`, `bird flu`, `pandemic`, `disease`, `CDC`
- Tag-based filtering: `tag=health`, `tag=flu`
- Both open and closed markets

**Result: No flu, influenza, or hospitalization-related markets were found.** The Gamma API's search function appears to use fuzzy matching, and returned unrelated results (deportation markets, cryptocurrency, politics) for every health-related query.

### API Response Format

When markets do exist, the response includes:
```json
{
  "id": "517310",
  "question": "Market question text",
  "slug": "url-slug",
  "outcomes": "[\"Yes\", \"No\"]",
  "outcomePrices": "[\"0.038\", \"0.962\"]",
  "volume": "1172840.52",
  "active": true,
  "closed": false,
  "liquidity": "24537.48",
  "conditionId": "0x...",
  "enableOrderBook": true,
  "volume24hr": 5900.75,
  "volume1wk": 89861.67,
  "volume1mo": 211061.02
}
```

### Recommendation

Polymarket does not currently have flu hospitalization prediction markets. Options:
1. **Create a market** — if the project has budget for market-making
2. **Monitor periodically** — flu markets may appear during peak season
3. **Use Metaculus or Manifold Markets** as alternatives for crowdsourced flu predictions
4. **Use FluSight ensemble** (Section 5) as the "market consensus" equivalent

---

## 7. Polymarket CLOB API

**Base URL:** `https://clob.polymarket.com`
**Auth Required:** None for read operations
**Status: API WORKS — REQUIRES TOKEN IDs**

### Endpoints Tested

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /` | 200 | Returns `"OK"` |
| `GET /markets` | 200 | Returns paginated list of all markets (1000+ items) |
| `GET /markets?search=flu` | 200 | No search parameter support — returns all markets |
| `GET /book?token_id=<id>` | 400/404 | Requires valid active token_id |
| `GET /midpoint?token_id=<id>` | 404 | Only works for active orderbooks |
| `GET /prices` | 400 | Requires token_id parameter |
| `GET /trade-history` | 404 | Endpoint not found |

### Key Findings

- The CLOB API is designed for **trading operations**, not market discovery
- Market discovery should be done via the **Gamma API** (Section 6), then token IDs used with CLOB for order book data
- The `/markets` endpoint returns all markets but with no search/filter capability — pagination via `next_cursor`
- No authentication needed for reading market data and order books
- Since no flu markets exist (per Section 6), the CLOB API has no relevant data

---

## 8. GoodRx Flu Tracker

**URL:** `https://www.goodrx.com/healthcare-access/research/flu-season-tracking-tamiflu-fills`
**Auth Required:** None (public webpage)
**Status: NOT PROGRAMMATICALLY ACCESSIBLE — EMBEDDED CHARTS ONLY**

### Findings

**HTTP Status:** 200
**Content-Type:** HTML (Next.js application)

The page contains embedded Datawrapper charts with Tamiflu prescription fill data:

| Chart | Datawrapper ID | URL |
|-------|---------------|-----|
| Weekly Tamiflu Fill Rate by Season (Nationwide) | `ifNGi` | `https://datawrapper.dwcdn.net/ifNGi/1/` |
| Weekly COVID-19 Antiviral Fill Rate by Season | `kd0YJ` | `https://datawrapper.dwcdn.net/kd0YJ/2/` |
| Weekly Oral Solution Antibiotics Fill Rate | `rgZuY` | `https://datawrapper.dwcdn.net/rgZuY/1/` |
| National Flu Treatment Fill Rates, Sep 2025 | `Zu9Pv` | `https://datawrapper.dwcdn.net/Zu9Pv/3/` |
| Vaccine Coverage Gaps in Commercial Plans | `9MoT2` | `https://datawrapper.dwcdn.net/9MoT2/5/` |

### Data Extraction Feasibility

- Datawrapper embeds render data client-side; the underlying CSV data URLs are **not exposed** in the iframe HTML
- The chart data could theoretically be extracted by inspecting the Datawrapper JavaScript runtime, but this is fragile
- No public API or downloadable dataset is offered by GoodRx

### Alternatives

1. **IQVIA / Symphony Health** — commercial pharmaceutical claims data (paid)
2. **CMS Medicare data** — public but lagged
3. **Consider Tamiflu fill rates as a proxy only** — the FluSurv-NET and ILINet data from Delphi are more directly relevant to hospitalization forecasting

---

## Summary Comparison

| API | Status | Auth | Format | Latency | Quality | Priority |
|-----|--------|------|--------|---------|---------|----------|
| Delphi FluSurv | WORKING | None | JSON | ~1 week lag | Excellent | **P0** |
| Delphi FluView/ILINet | WORKING | None | JSON | ~1 week lag | Excellent | **P0** |
| CDC NWSS Wastewater | WORKING | None | CSV/JSON | ~2 week lag | Good | **P1** |
| CDC FluSight Hub | WORKING | None | CSV (GitHub) | Weekly Saturday | Excellent | **P1** |
| Google Trends | NEEDS SETUP | None (pytrends) | DataFrame | Real-time | Medium | **P2** |
| Polymarket Gamma | WORKING (no flu markets) | None | JSON | Real-time | N/A | **P3** |
| Polymarket CLOB | WORKING (no flu markets) | None | JSON | Real-time | N/A | **P3** |
| WastewaterSCAN | NO API | N/A | N/A | N/A | N/A | Skip |
| GoodRx Flu Tracker | NO API | N/A | N/A | N/A | N/A | Skip |

---

## Recommended Data Pipeline Architecture

### Tier 1: Core Signals (poll weekly)
1. **Delphi FluSurv** — Hospitalization rates by age, race, sex, flu type; per state and national
2. **Delphi FluView** — ILI percentages with full revision history (use `issues` parameter)
3. **CDC FluSight Ensemble** — Pull latest ensemble forecast CSV from GitHub every Saturday

### Tier 2: Leading Indicators (poll weekly)
4. **CDC NWSS Wastewater** — Regional and state-level WVAL for Influenza A (CSV download)
5. **Google Trends** — Install pytrends; query "flu symptoms" etc. weekly with rate limiting

### Tier 3: Market Signals (monitor)
6. **Polymarket** — Monitor Gamma API weekly for new flu markets appearing (`search=flu+hospitalization`)

### Key Integration Notes

- **Epiweek alignment:** FluSurv and FluView use MMWR epiweeks (Sunday-Saturday). FluSight uses ISO weeks (reference_date is Saturday). CDC NWSS uses week-ending Saturday dates. All are alignable.
- **Revision tracking:** Store snapshots of FluView data weekly using `issues` parameter to capture revision patterns. FluSurv does not support `issues` filtering — store raw responses with timestamps.
- **FluSight target data** includes `as_of` versioning — use this for backtest evaluation.
- **NWSS WVAL thresholds** (Minimal <= 2.7, Low 2.7-6.2, Moderate 6.2-11.2, High 11.2-16.4, Very High > 16.4) can be used to create leading indicator features.

---

## Appendix: All Tested URLs

```
# Delphi Epidata
https://api.delphi.cmu.edu/epidata/flusurv/?locations=network_all&epiweeks=202605
https://api.delphi.cmu.edu/epidata/flusurv/?locations=CA,CO,CT,GA,MD,MI,MN,NM,OR,TN,UT&epiweeks=202605
https://api.delphi.cmu.edu/epidata/fluview/?regions=nat&epiweeks=202605
https://api.delphi.cmu.edu/epidata/fluview/?regions=nat&epiweeks=202501&issues=202502
https://api.delphi.cmu.edu/epidata/fluview/?regions=hhs1,hhs2,...,hhs10&epiweeks=202605
https://api.delphi.cmu.edu/epidata/fluview/?regions=nat&epiweeks=202501-202510&lag=0
https://api.delphi.cmu.edu/epidata/ght/?auth=&locations=US&epiweeks=202601-202606&query=flu+symptoms

# CDC NWSS
https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluastatemapDL.csv
https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluaregionalactivitylevelDL.csv
https://www.cdc.gov/nwss/rv/modules/flua/influenza-national-and-regional-trends-dashboard.json
https://www.cdc.gov/nwss/rv/modules/flua/flua-state-level-dashbaord.json
https://www.cdc.gov/nwss/rv/modules/flua/flua-top-modules.json

# CDC FluSight
https://raw.githubusercontent.com/cdcepi/FluSight-forecast-hub/main/model-output/FluSight-ensemble/2026-02-14-FluSight-ensemble.csv
https://raw.githubusercontent.com/cdcepi/FluSight-forecast-hub/main/hub-config/tasks.json
https://raw.githubusercontent.com/cdcepi/FluSight-forecast-hub/main/target-data/time-series.csv

# Polymarket
https://gamma-api.polymarket.com/markets?closed=false&limit=10&search=flu
https://gamma-api.polymarket.com/events?closed=false&limit=20&search=flu
https://clob.polymarket.com/
https://clob.polymarket.com/markets

# WastewaterSCAN
https://data.wastewaterscan.org
https://data.wastewaterscan.org/api (404)

# GoodRx
https://www.goodrx.com/healthcare-access/research/flu-season-tracking-tamiflu-fills
https://datawrapper.dwcdn.net/ifNGi/1/

# Google Trends
https://trends.google.com/trends/api/explore (429 rate limit)
```
