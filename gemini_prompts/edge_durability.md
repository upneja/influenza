# Vetting Request: Edge Durability and Market Analysis for Flu Prediction Market Strategy

## Background

We are building a quantitative trading system ("Project FluSight Edge") that trades on Polymarket prediction markets for U.S. influenza hospitalization rates. Polymarket offers markets on CDC FluSurv-NET cumulative hospitalization rate brackets -- for example, "Will the cumulative flu hospitalization rate for the 2025-2026 season be between 25 and 30 per 100,000?" -- with binary YES/NO shares that pay $1 if the outcome lands in that bracket.

Our edge comes from two sources: (1) fusing 7 real-time epidemiological signals (wastewater RNA, ED visits, Google Trends, antiviral prescriptions, FluSight ensemble forecasts, Delphi revision data, and ILINet data) to forecast hospitalizations more accurately than the market, and (2) exploiting the systematic upward revision of preliminary FluSurv-NET data (we estimate 15-30% upward revision from initial to final report), which we believe most traders do not account for.

We plan to deploy capital gradually over the flu season, sizing positions at 0.20x Kelly fraction. We need an independent assessment of whether this edge is real, how long it might last, and what external risks could kill the strategy. Please answer each question with specific evidence and citations.

## Questions

### 1. Polymarket Flu Market Liquidity and Volume
What is the current trading volume and liquidity on Polymarket's influenza hospitalization bracket markets for the 2025-2026 season? How does this compare to the 2024-2025 season (if those markets existed)? What is the typical bid-ask spread on these markets? What is the total open interest across all flu-related markets on Polymarket? Has the flu market category grown, shrunk, or remained stable in trader participation over time? Please provide specific numbers or estimates if available, or state clearly if this data is not publicly accessible.

### 2. Sophisticated Competition
Are there any known quantitative trading teams, hedge funds, prediction market specialists, or automated bots that are known or suspected to be actively trading Polymarket flu hospitalization markets? Are there any public discussions (e.g., on Twitter/X, prediction market forums, Metaculus, or academic blogs) of strategies similar to ours -- specifically the backfill arbitrage thesis or multi-signal epidemiological fusion for Polymarket trading? Has anyone published research on trading prediction markets using epidemiological data advantages? How would we detect if a sophisticated competitor entered the market (e.g., sudden liquidity increase, price efficiency improvements)?

### 3. Market Capacity and Edge Compression
Assuming our model has a genuine informational edge, how much capital can we realistically deploy into Polymarket flu markets before our own trading compresses the edge? What is the typical price impact of a $1,000, $5,000, or $10,000 trade on these markets? Is there an automated market maker (AMM) or order book system, and how does that affect price impact? At what capital level does our trading itself become the dominant signal in the market? What does the academic literature on prediction market microstructure say about the relationship between informed trading volume and price efficiency?

### 4. Informational Edge Duration in Prediction Markets
How long do informational edges typically persist in prediction markets before being competed away? What does the academic literature say about the speed of information incorporation in prediction markets generally (citing, e.g., work by Wolfers & Zitzewitz, Arrow et al., Hanson, or others)? Are there documented cases of sustained edges in prediction markets lasting an entire season (4-6 months), or do edges typically collapse within days/weeks once a new information source becomes widely known? Is the flu hospitalization market likely to be "efficient" in the academic sense, given its niche topic and relatively low volume?

### 5. Regulatory and Legal Risks
What is the current legal status of trading on Polymarket from the United States as of early 2026? Polymarket settled with the CFTC in January 2022 for $1.4 million and was subsequently available primarily to non-US users, but there have been reports of US access via VPN or changes in policy. Has the regulatory situation changed? Are there specific legal risks (CFTC enforcement, state gambling laws, tax reporting requirements) that a US-based trader should be aware of? Has the broader prediction market regulatory landscape shifted (e.g., Kalshi's CFTC approval for event contracts, any new legislation)? What is the realistic enforcement risk for an individual US-based trader using Polymarket?

### 6. UMA Optimistic Oracle Resolution
Polymarket uses the UMA Optimistic Oracle for market resolution. A proposer asserts an outcome, and if no one disputes it within a challenge period, it is accepted. How reliable has this mechanism been for resolving flu hospitalization markets specifically? Have there been any disputes on flu or public health-related markets on Polymarket? What happens if the resolution source (CDC FluSurv-NET) publishes ambiguous data, or if the final number falls exactly on a bracket boundary? Is there a risk that a malicious actor could dispute a correct resolution and cause delays or incorrect payouts? What is the typical resolution timeline after the season ends?

### 7. Comprehensive Failure Mode Analysis
Beyond model prediction error, what are the most likely failure modes for this strategy? Please assess the following risks and add any we have not considered:
- **Data source failure**: One or more of the 7 signals becomes unavailable mid-season (covered in our separate data reliability vetting, but please comment on the trading impact).
- **Market structural risk**: Polymarket changes its flu market structure, delists markets, or changes resolution criteria mid-season.
- **Liquidity evaporation**: Flu markets lose liquidity and we cannot exit positions at reasonable prices.
- **CDC methodology change**: CDC changes FluSurv-NET methodology, catchment areas, or reporting schedule in a way that breaks the backfill pattern.
- **Black swan epidemiological event**: A novel flu strain, a pandemic declaration, or a public health emergency causes unprecedented hospitalization patterns outside historical ranges.
- **Smart money arrival**: A well-capitalized, well-informed competitor enters the market and eliminates the pricing inefficiency.
- **Platform risk**: Polymarket itself becomes unavailable (regulatory shutdown, technical failure, smart contract exploit).

For each failure mode, please estimate rough probability over a single flu season and potential severity (partial capital loss vs. total loss vs. stranded capital).

## Response Format

For each question, provide: (a) a direct evidence-based answer, (b) citations to academic literature, market data, regulatory filings, or news reports as applicable, and (c) an explicit statement of confidence in your answer and what additional information would be needed for a more definitive assessment. If you cannot find concrete data on Polymarket flu market volume or participants, state that clearly rather than speculating.
