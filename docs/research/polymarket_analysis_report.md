# Polymarket Flu Hospitalization Markets -- Analysis Report

**Research Agent:** RESEARCH-2 (Polymarket Analysis)
**Date:** 2026-02-18
**Project:** FluSight Edge

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Flu Markets](#2-current-flu-markets)
3. [Market Resolution Mechanics](#3-market-resolution-mechanics)
4. [CLOB API for Trading](#4-clob-api-for-trading)
5. [Order Book Depth and Liquidity](#5-order-book-depth-and-liquidity)
6. [Historical Market Data](#6-historical-market-data)
7. [Market Creation Timing](#7-market-creation-timing)
8. [Fee Structure](#8-fee-structure)
9. [Strategic Implications](#9-strategic-implications)

---

## 1. Executive Summary

Polymarket runs weekly prediction markets on the U.S. CDC FluSurv-NET cumulative influenza hospitalization rate per 100,000 population. These are bracket-style markets (6 outcomes per week) that resolve based on official CDC data. Key findings:

- **Active market as of 2026-02-18:** Week 6, 2026 (ending Feb 20) -- $38.5K volume, 60-70 bracket leading at 72%
- **No trading fees** on flu hospitalization markets (feesEnabled=false)
- **Thin liquidity:** Order books show $1.8K-$3.3K depth at best levels; $2K-$5K deployment would cause meaningful price impact
- **UMA bond:** $500 per market, $5 reward per proposer
- **Resolution:** Automatic via UMA Optimistic Oracle with CDC FluSurv-NET as the sole data source
- **Bracket structure shifted** from {<30, 30-40, 40-50, 50-60, 60-70, 70+} in Weeks 2-4 to {<50, 50-60, 60-70, 70-80, 80-90, 90+} in Weeks 5-6, tracking the rising cumulative rate
- **Market creator address:** `0x91430CaD2d3975766499717fA0D66A78D814E5c5`
- **Resolver address:** `0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d`

---

## 2. Current Flu Markets

### 2.1 Active Market: Week 6, 2026 (Event ID: 207515)

| Field | Value |
|-------|-------|
| **Slug** | `flu-hospitalization-rate-week-6-2026` |
| **Created** | 2026-02-13T15:29:20Z |
| **End Date** | 2026-02-20T00:00:00Z |
| **Total Volume** | $38,554.68 |
| **Closed** | No (active) |
| **Neg Risk Market ID** | `0xf5dc5fcba3bf3bca1d28e8c24af04bf30aeae49e76f3e95dbc0e3a2f3bd2e000` |

**Bracket Structure and Live Prices (as of 2026-02-18):**

| Bracket | Yes Price | Volume | Condition ID |
|---------|-----------|--------|--------------|
| <50 | $0.0195 | $2,864 | `0x88284c8e63ca0bd5c8ff57d0a908d84ff61c852cf667b8e96599d344ca6ee6df` |
| 50-60 | $0.0055 | $3,409 | `0x8bd39ab64e67946f42a2111fabf8bee43bf9ab7c7f0de8d677d5ce8714df90c9` |
| **60-70** | **$0.72** | **$19,192** | `0x23fb7144dc397df0d15e31bcf25dc1aa00fe9a776272897cbef1866418d3de1d` |
| 70-80 | $0.165 | $8,216 | `0xc3e1823245cd95c4478680ede7c67519720f2307cea68a929f479e439a5febdf` |
| 80-90 | $0.022 | $2,236 | `0x4d0aa5f98363d9a9e4934be0a8773a353c963bb3bbf362458def1743a20fe382` |
| 90+ | $0.0085 | $2,637 | `0x2b9a7bebd71adb291d22eff6f1541c057ea4c31494a47ff3df498b7058624005` |

**Market parameters:**
- `orderMinSize`: 5 (shares)
- `orderPriceMinTickSize`: 0.001 for tail brackets, 0.01 for 60-70 and 70-80
- `rewardsMinSize`: 20 (shares)
- `rewardsMaxSpread`: 3.5-4.5 (cents)
- `negRisk`: true (neg-risk framework)

### 2.2 Recently Resolved Markets

**Week 5, 2026 (Event ID: 200426)** -- Resolved to **60-70**

| Field | Value |
|-------|-------|
| Created | 2026-02-06T16:53:58Z |
| End Date | 2026-02-13 |
| Volume | $32,321 |
| Winning Bracket | 60-70 (cumulative rate 67.0 per 100K) |
| Brackets | <50, 50-60, 60-70, 70-80, 80-90, 90+ |

**Week 4, 2026 (Event ID: 193404)** -- Resolved to **60-70**

| Field | Value |
|-------|-------|
| Created | 2026-01-30T15:35:54Z |
| End Date | 2026-02-06 |
| Volume | $62,666 |
| Winning Bracket | 60-70 |
| Brackets | <30, 30-40, 40-50, 50-60, 60-70, 70+ |

**Week 3, 2026 (Event ID: 183658)** -- Resolved to **50-60**

| Field | Value |
|-------|-------|
| Created | 2026-01-23T22:33:02Z |
| End Date | 2026-01-30 |
| Volume | $43,708 |
| Winning Bracket | 50-60 |
| Brackets | <30, 30-40, 40-50, 50-60, 60-70, 70+ |

**Week 2, 2026 (Event ID: 177048)** -- Resolved to **50-60**

| Field | Value |
|-------|-------|
| Created | 2026-01-20T16:43:41Z |
| End Date | 2026-01-23 |
| Volume | $13,072 |
| Winning Bracket | 50-60 |
| Brackets | <30, 30-40, 40-50, 50-60, 60-70, 70+ |

### 2.3 Bracket Evolution

The bracket structure is **not static** -- it shifts as the cumulative hospitalization rate rises:

| Period | Brackets |
|--------|----------|
| Weeks 2-4 | <30, 30-40, 40-50, 50-60, 60-70, 70+ |
| Weeks 5-6 | <50, 50-60, 60-70, 70-80, 80-90, 90+ |

This means the market creator adjusts brackets to keep the expected outcome centered, providing meaningful resolution odds across brackets.

---

## 3. Market Resolution Mechanics

### 3.1 Resolution Source

- **Primary source:** CDC FluView / FluSurv-NET (https://www.cdc.gov/fluview/index.html)
- **Specific metric:** Cumulative influenza-associated hospitalization rate per 100,000 population for the United States, as reported for the specified MMWR week
- **No alternatives accepted:** Estimates, projections, state-level reports, or other surveillance metrics do NOT qualify

### 3.2 Resolution Rules

1. The market resolves to whichever bracket contains the cumulative rate
2. If the rate falls **exactly between two brackets**, it resolves to the **higher bracket**
3. **Deadline:** If CDC FluSurv-NET data is not released by 11:59 PM ET on the tenth calendar day following the prior FluView weekly report release, the market resolves to the **lowest bracket**
4. Week 3 had a slightly different formulation: deadline was specifically "February 2, 2026"

### 3.3 UMA Optimistic Oracle

| Parameter | Value |
|-----------|-------|
| **UMA Bond** | $500 USDC per market |
| **UMA Reward** | $5 USDC per proposer |
| **Oracle Version** | Managed OOV2 (MOOV2) -- as of 2025, proposals restricted to 37 whitelisted addresses |
| **Dispute Window** | Typically 2 hours (configurable) |
| **customLiveness** | 0 (uses default) |
| **Adapter Contract** | `UmaCtfAdapter` v3.0 at `0x157Ce2d672854c848c9b79C49a8Cc6cc89176a49` (Polygon) |
| **Resolution Status** | All past markets show `automaticallyResolved: true` |

**Resolution flow:**
1. Market closes at scheduled timestamp (the `endDate`)
2. UMA proposer submits resolution value
3. 2-hour dispute window opens
4. If no dispute: auto-finalized on-chain
5. If disputed: escalated to UMA DVM (commit-reveal vote by UMA token holders, 48-96 hours)
6. 98% of Polymarket markets resolve without dispute

### 3.4 Resolution Timeline Observed

| Market | End Date | UMA End Date (resolution) | Lag |
|--------|----------|--------------------------|-----|
| Week 2 | Jan 23 | -- | ~same day or next |
| Week 3 | Jan 30 | Jan 30 20:25 UTC | Same day, ~8:25 PM UTC |
| Week 4 | Feb 6 | Feb 6 20:41 UTC | Same day, ~8:41 PM UTC |
| Week 5 | Feb 13 | -- | Resolved automatically |

Resolution appears to happen the same day the market closes, typically in the evening UTC.

### 3.5 Resolver and Submitter

| Role | Address |
|------|---------|
| Market submitted by | `0x91430CaD2d3975766499717fA0D66A78D814E5c5` |
| Resolved by | `0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d` |

These are consistent across all observed flu markets.

---

## 4. CLOB API for Trading

### 4.1 py-clob-client Library

| Detail | Value |
|--------|-------|
| **Package** | `py-clob-client` on PyPI |
| **Latest Version** | v0.29.0 (Dec 2025) |
| **Python Requirement** | 3.9.10+ |
| **Web3 Pin** | web3==6.14.0 (required to avoid conflicts) |
| **CLOB Host** | `https://clob.polymarket.com` |
| **Chain** | Polygon (chain_id=137) |

**Installation:**
```bash
pip install py-clob-client
```

### 4.2 Authentication

**Two-tier system:**

**L1 (Private Key):**
- Signs EIP-712 messages proving wallet ownership
- Used to create/derive L2 credentials
- Headers: `POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_NONCE`

**L2 (API Key):**
- HMAC-SHA256 signed requests (expire after 30 seconds)
- Generated from L1 via `create_or_derive_api_creds()`
- Headers: `POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_API_KEY`, `POLY_PASSPHRASE`

**Signature types:**
- `signature_type=0`: Standard EOA (MetaMask, hardware wallets)
- `signature_type=1`: Email/Magic wallet (exported key)
- `signature_type=2`: Browser wallet proxy (Coinbase, etc.)

### 4.3 Key API Methods

**Read-only (no auth required):**

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookParams

client = ClobClient("https://clob.polymarket.com")

# Market data
markets = client.get_markets()                    # All markets (paginated via next_cursor)
book = client.get_order_book(token_id)             # Single order book
books = client.get_order_books([BookParams(...)])   # Batch order books
mid = client.get_midpoint(token_id)                # Mid price
bid = client.get_price(token_id, side="BUY")       # Best bid
ask = client.get_price(token_id, side="SELL")       # Best ask
last = client.get_last_trade_price(token_id)       # Last trade
```

**Authenticated (L2 required):**

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs
from py_clob_client.order_builder.constants import BUY, SELL

client = ClobClient("https://clob.polymarket.com",
                     key=PRIVATE_KEY, chain_id=137,
                     signature_type=0, funder=FUNDER_ADDRESS)
client.set_api_creds(client.create_or_derive_api_creds())

# Limit order (GTC)
order = OrderArgs(token_id="<id>", price=0.45, size=100.0, side=BUY)
signed = client.create_order(order)
resp = client.post_order(signed, OrderType.GTC)

# Market order (FOK - Fill or Kill)
mo = MarketOrderArgs(token_id="<id>", amount=25.0, side=BUY,
                     order_type=OrderType.FOK)
signed = client.create_market_order(mo)
resp = client.post_order(signed, OrderType.FOK)

# Order management
open_orders = client.get_orders(OpenOrderParams())
client.cancel(order_id)
client.cancel_all()
trades = client.get_trades()
```

**Order types:**
- `GTC` -- Good Till Cancelled (stays open until filled or cancelled)
- `FOK` -- Fill or Kill (must fill entirely or cancel immediately)
- `GTD` -- Good Till Date (expires at specified time)

### 4.4 Token Allowances (Required for EOA wallets)

Before trading, EOA wallets must approve USDC and Conditional Tokens for three contracts:

| Contract | Address |
|----------|---------|
| Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |

**USDC on Polygon:** `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
**Conditional Tokens:** `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`

### 4.5 Rate Limits

- Public endpoints: ~100 requests/minute
- Authenticated endpoints: Higher, volume-dependent
- HTTP 429 indicates rate limit exceeded
- Recommended: exponential backoff with jitter

### 4.6 Known Issues

- The `/book` endpoint has been reported to serve stale data (GitHub issue #180), while `/price` serves live data. Cross-reference both for production use.

---

## 5. Order Book Depth and Liquidity

### 5.1 Live Order Book Snapshot (Week 6 -- 2026-02-18)

**60-70 Bracket (market leader at $0.72):**

| Side | Levels | Top of Book | Depth (Top 10) |
|------|--------|-------------|-----------------|
| Bids | 12 | $0.61 x 10 shares | ~$1,821 |
| Asks | 14 | $0.82 x 58 shares | ~$3,275 |
| **Spread** | | **$0.61 / $0.82 = 21 cent spread** | |

Full bid ladder: $0.01(174), $0.04(55), $0.05(5), $0.07(100), $0.11(64), $0.12(1332), $0.18(44), $0.51(20), $0.60(16), $0.61(10)
Full ask ladder: $0.82(58), $0.85(117), $0.91(30), $0.92(7), $0.94(16), $0.95(26), $0.96(75), $0.97(357), $0.98(400), $0.99(2188)

**70-80 Bracket (second most active at $0.165):**

| Side | Levels | Top of Book | Depth (Top 10) |
|------|--------|-------------|-----------------|
| Bids | 5 | $0.15 x 38 shares | ~$265 |
| Asks | 23 | $0.84 x 210 shares | ~$15,570 |
| **Spread** | | **$0.15 / $0.84 = 69 cent spread** | |

**Tail Brackets (<50, 50-60, 80-90, 90+):**

All tail brackets show similar patterns:
- Bids clustered at $0.001-$0.01 with 1,000-5,000 share depth
- Asks clustered at $0.99-$0.999 with 2,500-10,000 share depth
- These are essentially "no" markets with token bids and deep ask-side liquidity

### 5.2 Slippage Analysis for $2K-$5K Deployment

**Critical finding: These are very thin markets.**

For the 60-70 bracket (most liquid):
- A $2,000 market buy would walk through the entire ask side (only ~$3.3K available in top 10 levels)
- Best ask at $0.82 has only 58 shares ($47.56), jumping to $0.85 (117 shares = $99.45)
- A $2,000 order would likely move the price from $0.82 to $0.95+ (13+ cent slippage)

For the 70-80 bracket:
- Bid side has only $265 total across 5 levels
- A $2,000 sell would completely exhaust all bids

**Recommendation:** Limit orders only. Use GTC orders placed inside the spread. Market orders would suffer 5-15% slippage on positions over $500 in these markets. Consider deploying $500-$1,000 per bracket maximum to avoid excessive price impact.

### 5.3 Liquidity Rewards

Polymarket offers liquidity rewards for market makers on these markets:
- `rewardsMinSize`: 20 shares minimum per side
- `rewardsMaxSpread`: 3.5-4.5 cents maximum spread to qualify
- This explains why some liquidity exists despite low volumes

---

## 6. Historical Market Data

### 6.1 Resolved Market Summary

| Week | CDC Cumulative Rate | Winning Bracket | Volume | Created | End Date |
|------|-------------------|-----------------|--------|---------|----------|
| Week 2 | 50-60 range | 50-60 | $13,072 | Jan 20 | Jan 23 |
| Week 3 | 50-60 range | 50-60 | $43,708 | Jan 23 | Jan 30 |
| Week 4 | 60-70 range | 60-70 | $62,666 | Jan 30 | Feb 6 |
| Week 5 | ~67.0 per 100K | 60-70 | $32,321 | Feb 6 | Feb 13 |

**Volume trend:** Volumes peaked at Week 4 ($62.7K) and have been moderate ($32-43K) otherwise. Week 2 was notably low ($13K) -- likely an early-season market with less interest.

### 6.2 CDC FluSurv-NET Context (2025-2026 Season)

- **Peak weekly rate:** 12.8 per 100K in Week 52 (second highest since 2010-11)
- **Cumulative as of Week 5:** 67.0 per 100K (second highest at this point since 2010-11)
- **Trend:** Weekly rates declining (2.3 per 100K in Week 5, down from peak), but cumulative continues to climb
- **Current trajectory:** Cumulative rate likely to land 70-80 for Week 6 based on declining weekly additions

### 6.3 Accessing Historical Data

**Gamma API:**
```
GET https://gamma-api.polymarket.com/events?slug=flu-hospitalization-rate-week-{N}-2026
```
Returns full event JSON with all nested market data, prices, volumes, condition IDs, and resolution status.

**Dune Analytics:**
- General Polymarket dashboards exist: https://dune.com/rchen8/polymarket
- Historical accuracy tracking: https://dune.com/alexmccullough/how-accurate-is-polymarket
- No flu-specific Dune dashboard was found
- Raw on-chain data (Polygon) can be queried for all trades and resolutions

**Polymarket Analytics:**
- https://polymarketanalytics.com provides market tracking and trader analysis

---

## 7. Market Creation Timing

### 7.1 Observed Pattern

| Market | Created | End Date | Days Open | Gap from Prior Resolution |
|--------|---------|----------|-----------|--------------------------|
| Week 2 | Jan 20, 16:43 UTC | Jan 23 | ~3 days | -- |
| Week 3 | Jan 23, 22:33 UTC | Jan 30 | ~7 days | Same day as Week 2 end |
| Week 4 | Jan 30, 15:35 UTC | Feb 6 | ~7 days | Same day as Week 3 end |
| Week 5 | Feb 6, 16:53 UTC | Feb 13 | ~7 days | Same day as Week 4 end |
| Week 6 | Feb 13, 15:29 UTC | Feb 20 | ~7 days | Same day as Week 5 end |

**Key finding:** New markets are created **the same day the prior market ends**, typically in the afternoon UTC (15:29-16:53 UTC, or roughly 10:30 AM - 12:00 PM ET). The pattern is highly consistent:

1. Prior week's market closes (end date)
2. New market created same day, afternoon ET
3. New market opens for ~7 days
4. Brackets may be adjusted based on current cumulative rate trajectory

### 7.2 Market Creator

All markets submitted by: `0x91430CaD2d3975766499717fA0D66A78D814E5c5`

This appears to be a Polymarket team account or an approved market creator. Users cannot create their own markets -- they must be proposed via Discord (#market-suggestion) or Twitter/X (@polymarket).

### 7.3 Initial Price Seeding

- Markets open with `acceptingOrdersTimestamp` set slightly before creation
- The `clearBookOnStart: true` flag suggests the order book is wiped clean at market start
- Initial liquidity likely comes from:
  1. The market creator placing seed orders
  2. Polymarket liquidity reward program incentivizing market makers
  3. Algorithmic traders detecting new market events

---

## 8. Fee Structure

### 8.1 Flu Market Fees

**Flu hospitalization markets have NO trading fees.**

All observed markets show `feesEnabled: false` and `feeType: null`. This is consistent with the general Polymarket policy where most markets are fee-free.

### 8.2 General Polymarket Fee Schedule (for reference)

Fee-enabled markets (NOT flu) use the formula:

```
fee(p) = p * (1 - p) * feeRate
```

Where `p` is the share price and `feeRate` is market-specific.

| Market Type | Fee Rate | Peak Fee (at p=0.50) | Maker Rebate |
|-------------|----------|---------------------|--------------|
| Sports (NCAAB, Serie A) | 0.0175 | 0.44% | 25% |
| Crypto (5-min, 15-min) | 0.25 | 1.56% | 20% |
| **Flu hospitalization** | **0** | **0%** | **N/A** |

### 8.3 Transaction Costs for Flu Markets

Even without explicit fees, traders face:
- **Spread cost:** 21 cents on the 60-70 bracket, 69 cents on 70-80 -- this is the dominant cost
- **Slippage:** Walking the book for orders > $500 incurs significant additional cost
- **Gas (Polygon):** Negligible (<$0.01 per transaction)

---

## 9. Strategic Implications

### 9.1 Edge Opportunities

1. **Information asymmetry:** The market resolves to CDC FluSurv-NET data. Anyone who can model the cumulative hospitalization rate better than the crowd has edge.
2. **Cumulative nature:** Since the metric is cumulative (not weekly), it only goes up. The question is "by how much" each week, not "up or down."
3. **Bracket structure shifts:** The market creator adjusts brackets weekly. Anticipating the bracket structure gives a timing advantage on new markets.
4. **Early market entry:** New markets open with wide spreads and thin books -- first movers can place limit orders at favorable prices.

### 9.2 Liquidity Constraints

- Total weekly volume: $13K-$63K (mostly concentrated in the leading bracket)
- Order book depth: $1K-$3K at best levels
- **Maximum deployable capital without excessive slippage: ~$1,000 per bracket via limit orders**
- For $2K-$5K total deployment: spread across 2-3 brackets with GTC limit orders placed inside the spread
- Use limit orders exclusively; market orders would suffer 5-15% slippage

### 9.3 Trading Strategy Recommendations

1. **Place limit orders at or near fair value immediately when new markets open** (typically same day as prior resolution, ~3:30-5:00 PM UTC)
2. Target the **2nd and 3rd most likely brackets** where spreads are widest and edge is largest
3. Use **GTC orders** with sizes of 50-200 shares per level
4. Monitor CDC FluView releases (typically Fridays) for resolution data
5. Consider providing two-sided liquidity to earn Polymarket liquidity rewards
6. The `rewardsMinSize=20` and `rewardsMaxSpread=3.5-4.5` parameters define the qualification thresholds

### 9.4 Technical Integration Requirements

To trade programmatically:
1. Polygon wallet with USDC funding
2. `py-clob-client` v0.29.0 installed
3. Token approvals for Exchange, Neg Risk Exchange, and Neg Risk Adapter contracts
4. L1/L2 authentication configured
5. Monitor Gamma API for new event creation: `GET https://gamma-api.polymarket.com/events?slug=flu-hospitalization-rate-week-{N}-2026`
6. Query CLOB for order book: `GET https://clob.polymarket.com/book?token_id={token_id}`

### 9.5 Risk Factors

- **Market discontinuation:** Polymarket may stop creating flu markets if volume drops or the flu season ends
- **Bracket surprise:** Bracket structures change weekly without advance notice
- **Resolution edge cases:** CDC data revisions, delayed publications, or FluSurv-NET methodology changes
- **Counterparty risk:** Polymarket is non-custodial (on-chain settlement), but regulatory risk exists
- **Stale order book data:** Known issue with `/book` endpoint; cross-reference with `/price`
- **Restricted market:** All flu markets show `restricted: true` -- may have geographic or user restrictions

---

## Appendix A: CLOB Token IDs for Active Week 6 Market

| Bracket | Yes Token ID | No Token ID |
|---------|-------------|-------------|
| <50 | `111798012724214451494479663539959137845382030183186530704653855119391184304999` | `92941113996336669237681643055324881415248514659003033057566882295319068520501` |
| 50-60 | `27010835276582692964559343798498449299486165435942018772219720493264999724819` | `86697142423851331564739157433049067991796548629293936706642412968881843389683` |
| 60-70 | `21766706205757451195660126639336662594129947469564752711315357586790013936679` | `111625333359868252907798102216722914759605129886295656176447522701893597571782` |
| 70-80 | `33630033779250885789657455931056525847026580126819482168433457024460257285912` | `105860571026288772321525008665870093547131841404721074997886215322804153800166` |
| 80-90 | `113995741527271201599056893042466069807113817691744665812046953238290222029678` | `106833841050182651774893985865812556140161016753612133113820850702939404293482` |
| 90+ | `41021338120395641238000557404355963150831258396174334573478388169566055267609` | `25425362922266940678152103996340977026964576621077350338278866120574456761794` |

## Appendix B: Gamma API Query Examples

```bash
# Get current/active flu event
curl "https://gamma-api.polymarket.com/events?slug=flu-hospitalization-rate-week-6-2026"

# Get all markets for an event (by neg risk market ID)
curl "https://gamma-api.polymarket.com/markets?neg_risk_market_id=0xf5dc5fcba3bf3bca1d28e8c24af04bf30aeae49e76f3e95dbc0e3a2f3bd2e000"

# Get order book for a specific bracket
curl "https://clob.polymarket.com/book?token_id=21766706205757451195660126639336662594129947469564752711315357586790013936679"

# Get price
curl "https://clob.polymarket.com/price?token_id=21766706205757451195660126639336662594129947469564752711315357586790013936679&side=buy"
```

## Appendix C: Key Contract Addresses (Polygon)

| Contract | Address |
|----------|---------|
| USDC | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| Conditional Tokens | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |
| UMA CTF Adapter v3.0 | `0x157Ce2d672854c848c9b79C49a8Cc6cc89176a49` |

---

*Report generated 2026-02-18. All prices and order book data are point-in-time snapshots and will change.*
