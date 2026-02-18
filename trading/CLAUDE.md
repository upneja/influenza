# Trading Directory

## Components

### polymarket.py — CLOB API Client
- Uses `py-clob-client` library
- Wraps: get markets, get order book, place limit order, cancel order, get positions
- All orders are LIMIT ONLY — never market orders
- Must handle: rate limiting, auth (API key + wallet), order status polling

### kelly.py — Position Sizing
- Fractional Kelly at 0.20x multiplier
- Formula: bet_fraction = 0.20 * (model_prob - market_prob) / (1 - market_prob)
- Minimum edge threshold: 3 cents (model_prob - market_prob >= 0.03)
- Maximum single-market exposure: 15% of total capital

### executor.py — Order Management
- Ladder strategy: spread across adjacent brackets (70% primary, 15% each adjacent)
- Post limit orders 0.5-1 cent inside best available
- Cancel and re-price stale orders after 2 hours
- Maximum 4 trades per day
- Check fill status every 15 minutes

## Safety Rules
- NEVER execute market orders
- NEVER exceed 15% exposure per market
- NEVER trade without minimum 3-cent edge
- All trades logged to SQLite `trades` table with full audit trail
- Paper trade mode via config flag — same code path, just skip actual API calls
