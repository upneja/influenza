"""Polymarket flu hospitalization market scraper.

Fetches market listings from the Gamma API (discovery/metadata) and order book
data from the CLOB API (prices/depth). Stores snapshots in SQLite for tracking
price evolution over time.

Gamma API (public, no auth): https://gamma-api.polymarket.com
CLOB API (read-only, no auth for reads): https://clob.polymarket.com
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from config import (
    DB_PATH,
    DEFAULT_BRACKETS,
    POLYMARKET_CLOB_API,
    POLYMARKET_GAMMA_API,
)
from db import get_connection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Keywords used to discover flu hospitalization markets via Gamma search/filter.
FLU_SEARCH_TERMS = [
    "flu hospitalization",
    "FluSurv-NET",
    "influenza hospitalization",
]

# Regex patterns for extracting numeric bracket ranges from outcome strings.
# Covers forms like "<30", "30-40", "40 - 50", "70+", "Under 30", "Over 70",
# "60 to 70", etc.
_BRACKET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "<30" or "Under 30" or "Less than 30"
    (re.compile(r"(?:^<|^under\s+|^less\s+than\s+)(\d+\.?\d*)", re.IGNORECASE), "lt"),
    # "70+" or "Over 70" or "More than 70" or ">70" or "70 or more"
    (re.compile(
        r"(?:^>|^over\s+|^more\s+than\s+|^above\s+)(\d+\.?\d*)"
        r"|^(\d+\.?\d*)\s*\+$"
        r"|^(\d+\.?\d*)\s+or\s+more$",
        re.IGNORECASE,
    ), "gt"),
    # "30-40" or "30 - 40" or "30 to 40"
    (re.compile(r"^(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)$"), "range"),
    (re.compile(r"^(\d+\.?\d*)\s+to\s+(\d+\.?\d*)$", re.IGNORECASE), "range"),
]

# Rate limiting: minimum seconds between consecutive requests to the same host.
_RATE_LIMIT_DELAY = 0.25

# Default HTTP timeout in seconds.
_HTTP_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Bracket parsing
# ---------------------------------------------------------------------------

def parse_bracket(outcome: str) -> str | None:
    """Parse a Polymarket outcome string into our standard bracket format.

    Examples:
        "Under 30"  -> "<30"
        "30-40"     -> "30-40"
        "70+"       -> "70+"
        "60 to 70"  -> "60-70"
        "Over 70"   -> "70+"
        "<30"       -> "<30"

    Returns None if the string doesn't match any known bracket pattern.
    """
    outcome = outcome.strip()

    for pattern, kind in _BRACKET_PATTERNS:
        m = pattern.match(outcome)
        if not m:
            continue
        if kind == "lt":
            return f"<{m.group(1)}"
        elif kind == "gt":
            # Multiple capture groups — find the one that matched.
            val = m.group(1) or m.group(2) or m.group(3)
            return f"{val}+"
        elif kind == "range":
            lo, hi = m.group(1), m.group(2)
            return f"{lo}-{hi}"
    return None


def bracket_to_range(bracket: str) -> tuple[float | None, float | None]:
    """Convert a standard bracket string to (low, high) numeric bounds.

    Returns (None, x) for "<x", (x, None) for "x+", and (lo, hi) for "lo-hi".
    """
    bracket = bracket.strip()
    if bracket.startswith("<"):
        return (None, float(bracket[1:]))
    if bracket.endswith("+"):
        return (float(bracket[:-1]), None)
    parts = bracket.split("-")
    if len(parts) == 2:
        return (float(parts[0]), float(parts[1]))
    raise ValueError(f"Cannot parse bracket: {bracket!r}")


def map_to_standard_bracket(outcome: str, standard: list[str] | None = None) -> str | None:
    """Map a raw outcome string to the closest standard bracket from config.

    If the parsed bracket exactly matches one in ``standard``, return it.
    Otherwise return the parsed bracket (or None if unparseable).
    """
    if standard is None:
        standard = DEFAULT_BRACKETS
    parsed = parse_bracket(outcome)
    if parsed is None:
        return None
    if parsed in standard:
        return parsed
    # Try numeric matching: see if the parsed range overlaps a standard range.
    try:
        parsed_range = bracket_to_range(parsed)
    except ValueError:
        return parsed
    for s in standard:
        try:
            s_range = bracket_to_range(s)
        except ValueError:
            continue
        if parsed_range == s_range:
            return s
    return parsed


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple per-host rate limiter."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        now = time.monotonic()
        last = self._last.get(host, 0.0)
        diff = now - last
        if diff < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - diff)
        self._last[host] = time.monotonic()


_limiter = _RateLimiter()

# Module-level HTTP client for connection pooling (lazy initialization).
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """Return the module-level httpx.Client, creating it on first use."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=_HTTP_TIMEOUT)
    return _client


def _get_json(url: str, params: dict[str, Any] | None = None,
              timeout: float = _HTTP_TIMEOUT) -> Any:
    """GET a URL and return parsed JSON. Raises on HTTP errors."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    _limiter.wait(host)
    try:
        client = _get_client()
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP %s from %s: %s", exc.response.status_code, url,
                     exc.response.text[:500])
        raise
    except httpx.RequestError as exc:
        logger.error("Request error for %s: %s", url, exc)
        raise


# ---------------------------------------------------------------------------
# Gamma API — market discovery
# ---------------------------------------------------------------------------

def search_flu_markets(search_terms: list[str] | None = None,
                       include_closed: bool = False) -> list[dict]:
    """Search Gamma for flu hospitalization markets via /public-search.

    Tries each search term and de-duplicates by condition_id.
    Returns raw market dicts enriched with parsed bracket info.
    """
    if search_terms is None:
        search_terms = FLU_SEARCH_TERMS
    seen_condition_ids: set[str] = set()
    results: list[dict] = []

    for term in search_terms:
        try:
            data = _get_json(
                f"{POLYMARKET_GAMMA_API}/public-search",
                params={
                    "q": term,
                    "limit_per_type": 50,
                    "search_tags": False,
                    "search_profiles": False,
                    "keep_closed_markets": 1 if include_closed else 0,
                },
            )
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.warning("Gamma search failed for term %r, skipping", term)
            continue

        events = data.get("events", []) if isinstance(data, dict) else []
        for event in events:
            markets = event.get("markets", [])
            if not markets:
                continue
            for mkt in markets:
                cid = mkt.get("conditionId", "")
                if not cid or cid in seen_condition_ids:
                    continue
                seen_condition_ids.add(cid)
                results.append(mkt)

    logger.info("Gamma search found %d unique flu market(s)", len(results))
    return results


def fetch_markets_by_slug(slug: str) -> list[dict]:
    """Fetch markets from Gamma /markets endpoint by slug."""
    try:
        data = _get_json(
            f"{POLYMARKET_GAMMA_API}/markets",
            params={"slug": slug},
        )
    except (httpx.HTTPStatusError, httpx.RequestError):
        logger.warning("Gamma /markets fetch failed for slug %r", slug)
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def fetch_events(tag_id: int | None = None, active: bool = True,
                 closed: bool = False, limit: int = 100) -> list[dict]:
    """Fetch events from Gamma /events endpoint with optional tag filter."""
    params: dict[str, Any] = {
        "active": str(active).lower(),
        "closed": str(closed).lower(),
        "archived": "false",
        "limit": limit,
    }
    if tag_id is not None:
        params["tag_id"] = tag_id
    try:
        data = _get_json(f"{POLYMARKET_GAMMA_API}/events", params=params)
    except (httpx.HTTPStatusError, httpx.RequestError):
        logger.warning("Gamma /events fetch failed")
        return []
    return data if isinstance(data, list) else []


def _parse_market_record(mkt: dict) -> dict:
    """Extract a clean record from a raw Gamma market dict.

    Returns a dict with keys:
        condition_id, question, slug, outcomes, outcome_prices,
        clob_token_ids, brackets, active, closed, volume, liquidity,
        best_bid, best_ask, last_trade_price, end_date, raw
    """
    # outcomePrices and clobTokenIds are stored as JSON strings by Gamma.
    outcome_prices_raw = mkt.get("outcomePrices", "[]")
    if isinstance(outcome_prices_raw, str):
        try:
            outcome_prices = json.loads(outcome_prices_raw)
        except json.JSONDecodeError:
            outcome_prices = []
    else:
        outcome_prices = outcome_prices_raw or []

    clob_token_ids_raw = mkt.get("clobTokenIds", "[]")
    if isinstance(clob_token_ids_raw, str):
        try:
            clob_token_ids = json.loads(clob_token_ids_raw)
        except json.JSONDecodeError:
            clob_token_ids = []
    else:
        clob_token_ids = clob_token_ids_raw or []

    outcomes_raw = mkt.get("outcomes", "[]")
    if isinstance(outcomes_raw, str):
        try:
            outcomes = json.loads(outcomes_raw)
        except json.JSONDecodeError:
            outcomes = []
    else:
        outcomes = outcomes_raw or []

    # Parse brackets from outcomes.
    brackets: list[str] = []
    for o in outcomes:
        b = parse_bracket(str(o))
        brackets.append(b if b is not None else str(o))

    # Prices as floats, aligned 1:1 with outcomes.
    prices: list[float] = []
    for p in outcome_prices:
        try:
            prices.append(float(p))
        except (ValueError, TypeError):
            prices.append(0.0)

    return {
        "condition_id": mkt.get("conditionId", ""),
        "question": mkt.get("question", ""),
        "slug": mkt.get("slug", ""),
        "outcomes": outcomes,
        "outcome_prices": prices,
        "clob_token_ids": clob_token_ids,
        "brackets": brackets,
        "active": mkt.get("active", False),
        "closed": mkt.get("closed", False),
        "volume": _safe_float(mkt.get("volume")),
        "liquidity": _safe_float(mkt.get("liquidity")),
        "best_bid": _safe_float(mkt.get("bestBid")),
        "best_ask": _safe_float(mkt.get("bestAsk")),
        "last_trade_price": _safe_float(mkt.get("lastTradePrice")),
        "end_date": mkt.get("endDate"),
        "raw": mkt,
    }


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# CLOB API — order book / prices
# ---------------------------------------------------------------------------

def get_order_book(token_id: str) -> dict | None:
    """Fetch the full order book for a single CLOB token.

    Returns dict with keys: market, asset_id, bids, asks, hash.
    Each bid/ask is {"price": str, "size": str}.
    Returns None on failure, consistent with other CLOB helpers.
    """
    try:
        data = _get_json(
            f"{POLYMARKET_CLOB_API}/book",
            params={"token_id": token_id},
        )
        return data
    except Exception:
        logger.warning("Failed to fetch order book for token %s", token_id)
        return None


def get_order_books(token_ids: list[str]) -> list[dict]:
    """Fetch order books for multiple tokens. Returns list of book dicts."""
    books: list[dict] = []
    for tid in token_ids:
        book = get_order_book(tid)
        if book is not None:
            books.append(book)
        else:
            books.append({"market": tid, "bids": [], "asks": [], "error": "fetch failed"})
    return books


def get_midpoint(token_id: str) -> float | None:
    """Get the midpoint price for a token. Returns None on failure."""
    try:
        data = _get_json(
            f"{POLYMARKET_CLOB_API}/midpoint",
            params={"token_id": token_id},
        )
        return float(data.get("mid", 0))
    except Exception:
        logger.warning("Failed to get midpoint for token %s", token_id)
        return None


def get_price(token_id: str, side: str = "BUY") -> float | None:
    """Get the current price for a token on a given side (BUY or SELL)."""
    try:
        data = _get_json(
            f"{POLYMARKET_CLOB_API}/price",
            params={"token_id": token_id, "side": side},
        )
        return float(data.get("price", 0))
    except Exception:
        logger.warning("Failed to get price for token %s side=%s", token_id, side)
        return None


def get_spread(token_id: str) -> dict | None:
    """Get the spread for a token. Returns dict with bid/ask/spread."""
    try:
        data = _get_json(
            f"{POLYMARKET_CLOB_API}/spread",
            params={"token_id": token_id},
        )
        return data
    except Exception:
        logger.warning("Failed to get spread for token %s", token_id)
        return None


def get_last_trade_price(token_id: str) -> float | None:
    """Get the last trade price for a token."""
    try:
        data = _get_json(
            f"{POLYMARKET_CLOB_API}/last-trade-price",
            params={"token_id": token_id},
        )
        return float(data.get("price", 0))
    except Exception:
        logger.warning("Failed to get last trade price for token %s", token_id)
        return None


def _summarize_book(book: dict) -> dict:
    """Summarize an order book into best bid/ask and depth.

    Returns dict with: best_bid, best_ask, spread, bid_depth, ask_depth,
    bid_levels, ask_levels.
    """
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    best_bid = float(bids[0]["price"]) if bids else None
    best_ask = float(asks[0]["price"]) if asks else None
    spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None

    bid_depth = sum(float(b.get("size", 0)) for b in bids)
    ask_depth = sum(float(a.get("size", 0)) for a in asks)

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "bid_levels": len(bids),
        "ask_levels": len(asks),
    }


# ---------------------------------------------------------------------------
# Composite: active flu markets with enriched data
# ---------------------------------------------------------------------------

def get_active_flu_markets(include_order_books: bool = False) -> list[dict]:
    """Return all active flu hospitalization markets with current prices.

    Each entry is a parsed market record from ``_parse_market_record`` plus,
    if ``include_order_books`` is True, an ``order_books`` key mapping each
    CLOB token_id to its order book summary.
    """
    raw_markets = search_flu_markets()
    parsed: list[dict] = []

    for mkt in raw_markets:
        rec = _parse_market_record(mkt)
        if rec["closed"]:
            continue

        if include_order_books and rec["clob_token_ids"]:
            obs: dict[str, dict] = {}
            for i, tid in enumerate(rec["clob_token_ids"]):
                book = get_order_book(tid)
                if book is not None:
                    summary = _summarize_book(book)
                    outcome_label = rec["outcomes"][i] if i < len(rec["outcomes"]) else f"outcome_{i}"
                    obs[outcome_label] = summary
                else:
                    logger.warning("Order book fetch failed for token %s", tid)
            rec["order_books"] = obs

        parsed.append(rec)

    logger.info("Found %d active flu market(s)", len(parsed))
    return parsed


def get_order_book_for_bracket(condition_id: str, bracket: str,
                               db_path: Path = DB_PATH) -> dict:
    """Return order book for a specific bracket of a flu market.

    Looks up the market by condition_id in the DB (or fetches live), finds the
    CLOB token for the given bracket, and returns the full order book plus
    a summary.
    """
    target = None

    # Try to find the market in DB first.
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT * FROM markets WHERE condition_id = ?",
                (condition_id,),
            ).fetchone()
        if row is not None:
            # Reconstruct a parsed market record from DB data
            brackets_list = json.loads(row["brackets"]) if row["brackets"] else []
            # DB doesn't store clob_token_ids, so we still need Gamma for that
            # Fall through to Gamma search below
    except Exception:
        row = None

    # Search Gamma for full market data (needed for clob_token_ids).
    markets = search_flu_markets()
    for mkt in markets:
        if mkt.get("conditionId") == condition_id:
            target = _parse_market_record(mkt)
            break

    if target is None:
        raise ValueError(f"Market with condition_id={condition_id!r} not found")

    # Find the token_id for the bracket.
    token_id: str | None = None
    for i, b in enumerate(target["brackets"]):
        std = map_to_standard_bracket(b)
        if std == bracket or b == bracket:
            if i < len(target["clob_token_ids"]):
                token_id = target["clob_token_ids"][i]
                break

    if token_id is None:
        raise ValueError(
            f"Bracket {bracket!r} not found in market {condition_id!r}. "
            f"Available brackets: {target['brackets']}"
        )

    book = get_order_book(token_id)
    if book is None:
        book = {"market": token_id, "bids": [], "asks": []}
    return {
        "condition_id": condition_id,
        "bracket": bracket,
        "token_id": token_id,
        "book": book,
        "summary": _summarize_book(book),
    }


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------

def upsert_market(record: dict, db_path: Path = DB_PATH) -> None:
    """Insert or update a market record in the ``markets`` table."""
    now = datetime.now(timezone.utc).isoformat()
    brackets_json = json.dumps(record["brackets"])

    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO markets (condition_id, question, brackets, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(condition_id) DO UPDATE SET
                   question = excluded.question,
                   brackets = excluded.brackets,
                   updated_at = excluded.updated_at""",
            (record["condition_id"], record["question"], brackets_json, now),
        )


def insert_price_snapshot(condition_id: str, bracket: str,
                          bid: float | None, ask: float | None,
                          last_price: float | None, volume: float | None,
                          snapshot_at: str | None = None,
                          db_path: Path = DB_PATH) -> None:
    """Insert a single market_prices row."""
    if snapshot_at is None:
        snapshot_at = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO market_prices
               (condition_id, bracket, bid, ask, last_price, volume, snapshot_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (condition_id, bracket, bid, ask, last_price, volume, snapshot_at),
        )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def snapshot_prices(include_order_books: bool = True,
                    db_path: Path = DB_PATH) -> list[dict]:
    """Take a snapshot of all flu market prices and store in DB.

    For each active flu market:
    1. Upserts the market record.
    2. For each bracket/outcome, fetches the CLOB order book and records
       best bid, best ask, last price, and volume.

    Returns the list of parsed market records (for programmatic use).
    """
    snapshot_at = datetime.now(timezone.utc).isoformat()
    markets = get_active_flu_markets(include_order_books=False)
    snapshot_results: list[dict] = []

    for rec in markets:
        # Upsert market metadata.
        upsert_market(rec, db_path=db_path)

        # Fetch per-bracket order book data.
        for i, outcome in enumerate(rec["outcomes"]):
            bracket = rec["brackets"][i] if i < len(rec["brackets"]) else str(outcome)
            std_bracket = map_to_standard_bracket(bracket) or bracket
            price = rec["outcome_prices"][i] if i < len(rec["outcome_prices"]) else None

            bid: float | None = None
            ask: float | None = None
            last_price: float | None = price

            if include_order_books and i < len(rec["clob_token_ids"]):
                token_id = rec["clob_token_ids"][i]
                book = get_order_book(token_id)
                if book is not None:
                    summary = _summarize_book(book)
                    bid = summary["best_bid"]
                    ask = summary["best_ask"]
                    ltp = get_last_trade_price(token_id)
                    if ltp is not None:
                        last_price = ltp
                else:
                    logger.warning(
                        "Order book fetch failed for %s bracket %s",
                        rec["condition_id"], bracket,
                    )

            insert_price_snapshot(
                condition_id=rec["condition_id"],
                bracket=std_bracket,
                bid=bid,
                ask=ask,
                last_price=last_price,
                volume=rec.get("volume"),
                snapshot_at=snapshot_at,
                db_path=db_path,
            )

        snapshot_results.append(rec)

    logger.info(
        "Snapshot complete: %d market(s), timestamp=%s",
        len(snapshot_results), snapshot_at,
    )
    return snapshot_results


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

def _main() -> None:
    """Quick CLI entry point for testing: python -m trading.polymarket"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("Searching for flu hospitalization markets on Polymarket...")

    markets = get_active_flu_markets(include_order_books=True)
    if not markets:
        logger.warning("No active flu markets found.")
        return

    for m in markets:
        print(f"\n{'='*60}")
        print(f"Question : {m['question']}")
        print(f"Condition: {m['condition_id']}")
        print(f"Slug     : {m['slug']}")
        print(f"Active   : {m['active']}  Closed: {m['closed']}")
        print(f"Volume   : {m['volume']}  Liquidity: {m['liquidity']}")
        print(f"Brackets : {m['brackets']}")
        for i, outcome in enumerate(m["outcomes"]):
            price = m["outcome_prices"][i] if i < len(m["outcome_prices"]) else "?"
            print(f"  {outcome:20s} -> price={price}")
        if "order_books" in m:
            print("Order books:")
            for label, summary in m["order_books"].items():
                print(f"  {label}: bid={summary['best_bid']} ask={summary['best_ask']} "
                      f"spread={summary['spread']} "
                      f"bid_depth={summary['bid_depth']:.1f} ask_depth={summary['ask_depth']:.1f}")


if __name__ == "__main__":
    _main()
