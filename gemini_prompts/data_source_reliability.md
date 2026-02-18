# Vetting Request: Data Source Reliability for Flu Surveillance Trading System

## Background

We are building a quantitative trading system ("Project FluSight Edge") that trades Polymarket prediction markets on CDC FluSurv-NET influenza hospitalization rate brackets. The system fuses 7 real-time epidemiological and behavioral surveillance signals to predict where the final (post-revision) cumulative hospitalization rate will land relative to the bracket thresholds set by the market.

The entire strategy depends on reliable, timely, programmatic access to these data sources throughout the flu season (roughly October through May). If any critical data feed goes offline, changes format, or becomes unreliable, the model degrades. We need an independent assessment of the reliability, availability, and risks associated with each data source we plan to use.

Please answer each question below with specific, verifiable facts. Cite official documentation, announcements, API changelogs, or news reports where available.

## Questions

### 1. Delphi Epidata API (CMU)
We plan to use the Delphi Epidata API (https://cmu-delphi.github.io/delphi-epidata/) for two purposes: (a) accessing ILINet and FluSurv-NET data, and (b) using the versioned/as-of query feature to retrieve historical vintages of data (i.e., what the data looked like on a specific past date) so we can model revision patterns. Is the Epidata API still actively maintained as of the 2025-2026 flu season? Has CMU's Delphi Group made any public announcements about deprecation, funding changes, or reduced maintenance? Are the versioned/as-of endpoints for FluSurv-NET data specifically still functional and returning data for the current season? What is the typical latency between CDC publication and Epidata availability? Are there rate limits or access restrictions we should be aware of?

### 2. WastewaterSCAN (Stanford/Emory)
We plan to pull wastewater influenza RNA concentration data from the WastewaterSCAN platform (https://data.wastewaterscan.org/), which is run by Stanford's Boehm Lab and Emory University. Is WastewaterSCAN still actively collecting and publishing influenza data for the 2025-2026 season? Has there been any change in the number of participating treatment plants, geographic coverage, or data update frequency? Is there a stable API or data export mechanism, or must data be scraped from dashboards? Has the project's funding status changed (it was originally supported by CDC and other grants)?

### 3. CDC National Wastewater Surveillance System (NWSS)
The CDC NWSS publishes wastewater pathogen data including influenza. What is the current data access mechanism -- is there a public API with machine-readable output (JSON, CSV), or is the data only available through the CDC COVID/Respiratory Data Tracker dashboards? What geographic granularity is available (national, state, site-level)? How frequently is the data updated? Is the influenza wastewater data from NWSS meaningfully different from or duplicative of WastewaterSCAN data? Are there documented data quality issues or coverage gaps?

### 4. Google Trends for Influenza Queries
We plan to use Google Trends data for flu-related search terms (e.g., "flu symptoms," "Tamiflu," "flu near me") as a behavioral signal. Google Flu Trends, a prior Google product that directly estimated flu prevalence from search data, famously failed in 2013 by overestimating flu activity by nearly 2x for multiple seasons. What specifically caused the Google Flu Trends failure? How do modern approaches (such as the ARGO model by Yang et al., 2015, or subsequent iterations) avoid the same pitfalls? What are the documented failure modes of using raw Google Trends data in epidemiological models -- for example, media-driven search spikes during pandemic scares, algorithm changes to Google's trend normalization, or seasonal confounders? Is the Google Trends API (pytrends or official) stable and reliable for automated weekly data pulls?

### 5. GoodRx Tamiflu/Oseltamivir Tracker
We plan to use publicly available GoodRx data on Tamiflu (oseltamivir) prescription pricing and search volume as a proxy for antiviral demand, which may lead hospitalization data. Does GoodRx still publish a publicly accessible Tamiflu pricing/trends page? Is there an API or structured data feed, or would this require web scraping? How reliable has this data source been historically -- are there gaps, format changes, or access restrictions? Are there alternative sources for antiviral prescription volume data (e.g., IQVIA, CDC antiviral surveillance)?

### 6. CDC FluSight Forecast Hub
We plan to incorporate ensemble forecasts from the CDC FluSight Collaborative Forecast Hub (https://github.com/cdcepi/FluSight-forecast-hub) as one of our model inputs. Is the 2025-2026 season forecast hub active and receiving submissions from participating teams on the expected weekly schedule? How many teams are submitting forecasts this season compared to previous seasons? Has the target definition changed (e.g., are they still forecasting weekly incident hospitalizations at the state and national level)? Is there any risk that the FluSight program is discontinued or substantially changed for future seasons?

### 7. Cross-Cutting Risk: Data Source Outages
Considering all 7 data sources together, what is the realistic probability that one or more sources becomes unavailable or significantly degraded during a flu season? Which sources are most fragile (e.g., dependent on a single academic lab's grant funding vs. a large government program)? Have any of these sources experienced unannounced outages or format changes in the past 2 seasons that would have broken an automated pipeline? What mitigation strategies are recommended (e.g., caching, fallback models that work with a subset of signals)?

## Response Format

For each data source, please provide: (a) current operational status with evidence (links to live dashboards, recent API responses, or announcements), (b) specific risks and failure history, and (c) a reliability rating on a 1-5 scale (5 = highly reliable government system with redundancy, 1 = fragile academic project that could disappear). Cite your sources.
