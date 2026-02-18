"""Tests for the Polymarket flu hospitalization market scraper."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trading.polymarket import (
    _parse_market_record,
    _summarize_book,
    bracket_to_range,
    get_active_flu_markets,
    get_order_book_for_bracket,
    insert_price_snapshot,
    map_to_standard_bracket,
    parse_bracket,
    search_flu_markets,
    snapshot_prices,
    upsert_market,
)


# ---------------------------------------------------------------------------
# Fixtures: mock API responses
# ---------------------------------------------------------------------------

MOCK_GAMMA_SEARCH_RESPONSE = {
    "events": [
        {
            "id": 12345,
            "slug": "flu-hospitalization-rate-2026",
            "title": "Flu Hospitalization Rate 2025-2026",
            "markets": [
                {
                    "conditionId": "0xabc123def456",
                    "question": "What will the cumulative flu hospitalization rate be for the 2025-2026 season?",
                    "slug": "flu-hospitalization-rate-2026",
                    "outcomes": '["Under 30", "30-40", "40-50", "50-60", "60-70", "Over 70"]',
                    "outcomePrices": '[0.05, 0.10, 0.20, 0.35, 0.20, 0.10]',
                    "clobTokenIds": '["token_0", "token_1", "token_2", "token_3", "token_4", "token_5"]',
                    "active": True,
                    "closed": False,
                    "volume": "125000.50",
                    "liquidity": "45000.00",
                    "bestBid": "0.34",
                    "bestAsk": "0.36",
                    "lastTradePrice": "0.35",
                    "endDate": "2026-06-30T00:00:00Z",
                    "enableOrderBook": True,
                },
            ],
        },
    ],
    "tags": [],
    "profiles": [],
    "pagination": {"hasMore": False, "totalResults": 1},
}

MOCK_GAMMA_SEARCH_RESPONSE_MULTI = {
    "events": [
        {
            "id": 12345,
            "slug": "flu-hospitalization-rate-2026",
            "title": "Flu Hospitalization Rate 2025-2026",
            "markets": [
                {
                    "conditionId": "0xabc123def456",
                    "question": "What will the cumulative flu hospitalization rate be?",
                    "slug": "flu-hospitalization-rate-2026",
                    "outcomes": '["<30", "30-40", "40-50", "50-60", "60-70", "70+"]',
                    "outcomePrices": '[0.05, 0.10, 0.20, 0.35, 0.20, 0.10]',
                    "clobTokenIds": '["token_0", "token_1", "token_2", "token_3", "token_4", "token_5"]',
                    "active": True,
                    "closed": False,
                    "volume": "125000",
                    "liquidity": "45000",
                },
                {
                    "conditionId": "0xdef789abc012",
                    "question": "What will the weekly flu hospitalization rate be?",
                    "slug": "flu-weekly-rate-2026",
                    "outcomes": '["<5", "5-10", "10+"]',
                    "outcomePrices": '[0.30, 0.50, 0.20]',
                    "clobTokenIds": '["token_a", "token_b", "token_c"]',
                    "active": True,
                    "closed": False,
                    "volume": "50000",
                    "liquidity": "20000",
                },
            ],
        },
    ],
    "tags": [],
    "profiles": [],
}

MOCK_GAMMA_SEARCH_EMPTY = {
    "events": [],
    "tags": [],
    "profiles": [],
    "pagination": {"hasMore": False, "totalResults": 0},
}

MOCK_GAMMA_MARKET_CLOSED = {
    "events": [
        {
            "id": 99999,
            "markets": [
                {
                    "conditionId": "0xclosed111",
                    "question": "Closed market",
                    "slug": "closed-market",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '[0.90, 0.10]',
                    "clobTokenIds": '["tok_y", "tok_n"]',
                    "active": False,
                    "closed": True,
                    "volume": "999",
                },
            ],
        },
    ],
    "tags": [],
    "profiles": [],
}

MOCK_ORDER_BOOK = {
    "market": "token_3",
    "asset_id": "token_3",
    "bids": [
        {"price": "0.34", "size": "500"},
        {"price": "0.33", "size": "1000"},
        {"price": "0.32", "size": "1500"},
    ],
    "asks": [
        {"price": "0.36", "size": "400"},
        {"price": "0.37", "size": "800"},
        {"price": "0.38", "size": "1200"},
    ],
}

MOCK_ORDER_BOOK_EMPTY = {
    "market": "token_empty",
    "asset_id": "token_empty",
    "bids": [],
    "asks": [],
}


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database for testing."""
    db_path = tmp_path / "test.db"
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_path.read_text())
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Bracket parsing tests
# ---------------------------------------------------------------------------

class TestParseBracket:
    def test_less_than_symbol(self):
        assert parse_bracket("<30") == "<30"

    def test_less_than_with_decimal(self):
        assert parse_bracket("<30.5") == "<30.5"

    def test_under_keyword(self):
        assert parse_bracket("Under 30") == "<30"

    def test_under_keyword_lowercase(self):
        assert parse_bracket("under 30") == "<30"

    def test_less_than_keyword(self):
        assert parse_bracket("Less than 30") == "<30"

    def test_greater_than_plus(self):
        assert parse_bracket("70+") == "70+"

    def test_greater_than_symbol(self):
        assert parse_bracket(">70") == "70+"

    def test_over_keyword(self):
        assert parse_bracket("Over 70") == "70+"

    def test_more_than_keyword(self):
        assert parse_bracket("More than 70") == "70+"

    def test_or_more_keyword(self):
        assert parse_bracket("70 or more") == "70+"

    def test_range_dash(self):
        assert parse_bracket("30-40") == "30-40"

    def test_range_spaced_dash(self):
        assert parse_bracket("30 - 40") == "30-40"

    def test_range_en_dash(self):
        assert parse_bracket("30\u201340") == "30-40"

    def test_range_to_keyword(self):
        assert parse_bracket("30 to 40") == "30-40"

    def test_range_with_decimals(self):
        assert parse_bracket("30.5-40.5") == "30.5-40.5"

    def test_unrecognized_returns_none(self):
        assert parse_bracket("Yes") is None

    def test_unrecognized_text_returns_none(self):
        assert parse_bracket("something else") is None

    def test_whitespace_stripped(self):
        assert parse_bracket("  <30  ") == "<30"
        assert parse_bracket("  70+  ") == "70+"
        assert parse_bracket("  30-40  ") == "30-40"


class TestBracketToRange:
    def test_less_than(self):
        assert bracket_to_range("<30") == (None, 30.0)

    def test_greater_than(self):
        assert bracket_to_range("70+") == (70.0, None)

    def test_range(self):
        assert bracket_to_range("30-40") == (30.0, 40.0)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            bracket_to_range("invalid")


class TestMapToStandardBracket:
    def test_exact_match(self):
        assert map_to_standard_bracket("<30") == "<30"
        assert map_to_standard_bracket("30-40") == "30-40"
        assert map_to_standard_bracket("70+") == "70+"

    def test_under_maps_to_standard(self):
        assert map_to_standard_bracket("Under 30") == "<30"

    def test_over_maps_to_standard(self):
        assert map_to_standard_bracket("Over 70") == "70+"

    def test_range_keyword_maps(self):
        assert map_to_standard_bracket("40 to 50") == "40-50"

    def test_unrecognized_returns_none(self):
        assert map_to_standard_bracket("Yes") is None

    def test_nonstandard_range_returned_as_is(self):
        # 25-35 doesn't match any standard bracket exactly
        result = map_to_standard_bracket("25-35")
        assert result == "25-35"


# ---------------------------------------------------------------------------
# Market record parsing tests
# ---------------------------------------------------------------------------

class TestParseMarketRecord:
    def test_parses_json_string_fields(self):
        mkt = MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        rec = _parse_market_record(mkt)
        assert rec["condition_id"] == "0xabc123def456"
        assert rec["question"].startswith("What will the cumulative")
        assert len(rec["outcomes"]) == 6
        assert len(rec["outcome_prices"]) == 6
        assert len(rec["clob_token_ids"]) == 6

    def test_brackets_parsed_from_outcomes(self):
        mkt = MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        rec = _parse_market_record(mkt)
        assert rec["brackets"] == ["<30", "30-40", "40-50", "50-60", "60-70", "70+"]

    def test_prices_are_floats(self):
        mkt = MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        rec = _parse_market_record(mkt)
        for p in rec["outcome_prices"]:
            assert isinstance(p, float)
        assert rec["outcome_prices"][0] == pytest.approx(0.05)
        assert rec["outcome_prices"][3] == pytest.approx(0.35)

    def test_volume_liquidity_parsed(self):
        mkt = MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        rec = _parse_market_record(mkt)
        assert rec["volume"] == pytest.approx(125000.50)
        assert rec["liquidity"] == pytest.approx(45000.0)

    def test_handles_already_parsed_lists(self):
        """If outcomes/prices are already lists (not JSON strings), still works."""
        mkt = {
            "conditionId": "0xtest",
            "question": "Test?",
            "outcomes": ["<30", "30-40", "40+"],
            "outcomePrices": [0.3, 0.5, 0.2],
            "clobTokenIds": ["t1", "t2", "t3"],
            "active": True,
            "closed": False,
        }
        rec = _parse_market_record(mkt)
        assert rec["outcomes"] == ["<30", "30-40", "40+"]
        assert rec["outcome_prices"] == [0.3, 0.5, 0.2]

    def test_handles_missing_fields_gracefully(self):
        mkt = {"conditionId": "0xminimal"}
        rec = _parse_market_record(mkt)
        assert rec["condition_id"] == "0xminimal"
        assert rec["question"] == ""
        assert rec["outcomes"] == []
        assert rec["brackets"] == []


# ---------------------------------------------------------------------------
# Order book summary tests
# ---------------------------------------------------------------------------

class TestSummarizeBook:
    def test_normal_book(self):
        summary = _summarize_book(MOCK_ORDER_BOOK)
        assert summary["best_bid"] == pytest.approx(0.34)
        assert summary["best_ask"] == pytest.approx(0.36)
        assert summary["spread"] == pytest.approx(0.02)
        assert summary["bid_depth"] == pytest.approx(3000.0)
        assert summary["ask_depth"] == pytest.approx(2400.0)
        assert summary["bid_levels"] == 3
        assert summary["ask_levels"] == 3

    def test_empty_book(self):
        summary = _summarize_book(MOCK_ORDER_BOOK_EMPTY)
        assert summary["best_bid"] is None
        assert summary["best_ask"] is None
        assert summary["spread"] is None
        assert summary["bid_depth"] == 0.0
        assert summary["ask_depth"] == 0.0

    def test_bids_only(self):
        book = {"bids": [{"price": "0.50", "size": "100"}], "asks": []}
        summary = _summarize_book(book)
        assert summary["best_bid"] == pytest.approx(0.50)
        assert summary["best_ask"] is None
        assert summary["spread"] is None


# ---------------------------------------------------------------------------
# Gamma API search tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestSearchFluMarkets:
    @patch("trading.polymarket._get_json")
    def test_search_returns_markets(self, mock_get):
        mock_get.return_value = MOCK_GAMMA_SEARCH_RESPONSE
        results = search_flu_markets(search_terms=["flu hospitalization"])
        assert len(results) == 1
        assert results[0]["conditionId"] == "0xabc123def456"

    @patch("trading.polymarket._get_json")
    def test_search_deduplicates_across_terms(self, mock_get):
        # Same market found by multiple search terms should appear once.
        mock_get.return_value = MOCK_GAMMA_SEARCH_RESPONSE
        results = search_flu_markets(
            search_terms=["flu hospitalization", "FluSurv-NET", "influenza"]
        )
        assert len(results) == 1

    @patch("trading.polymarket._get_json")
    def test_search_multiple_markets(self, mock_get):
        mock_get.return_value = MOCK_GAMMA_SEARCH_RESPONSE_MULTI
        results = search_flu_markets(search_terms=["flu"])
        assert len(results) == 2

    @patch("trading.polymarket._get_json")
    def test_search_empty_results(self, mock_get):
        mock_get.return_value = MOCK_GAMMA_SEARCH_EMPTY
        results = search_flu_markets(search_terms=["nonexistent"])
        assert results == []

    @patch("trading.polymarket._get_json")
    def test_search_handles_http_error(self, mock_get):
        import httpx

        mock_get.side_effect = httpx.HTTPStatusError(
            "500",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        results = search_flu_markets(search_terms=["flu"])
        assert results == []

    @patch("trading.polymarket._get_json")
    def test_search_skips_failed_terms_continues_others(self, mock_get):
        import httpx

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.RequestError("timeout")
            return MOCK_GAMMA_SEARCH_RESPONSE

        mock_get.side_effect = side_effect
        results = search_flu_markets(
            search_terms=["term_that_fails", "flu hospitalization"]
        )
        assert len(results) == 1


# ---------------------------------------------------------------------------
# get_active_flu_markets tests (mocked)
# ---------------------------------------------------------------------------

class TestGetActiveFluMarkets:
    @patch("trading.polymarket.search_flu_markets")
    def test_filters_closed_markets(self, mock_search):
        raw = MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"] + \
              MOCK_GAMMA_MARKET_CLOSED["events"][0]["markets"]
        mock_search.return_value = raw
        results = get_active_flu_markets(include_order_books=False)
        # Only the open market should be returned.
        assert len(results) == 1
        assert results[0]["condition_id"] == "0xabc123def456"

    @patch("trading.polymarket.get_order_book")
    @patch("trading.polymarket.search_flu_markets")
    def test_includes_order_books_when_requested(self, mock_search, mock_book):
        mock_search.return_value = MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"]
        mock_book.return_value = MOCK_ORDER_BOOK
        results = get_active_flu_markets(include_order_books=True)
        assert len(results) == 1
        assert "order_books" in results[0]
        # Should have an entry per outcome.
        assert len(results[0]["order_books"]) == 6


# ---------------------------------------------------------------------------
# Database persistence tests
# ---------------------------------------------------------------------------

class TestUpsertMarket:
    def test_insert_new_market(self, tmp_db):
        rec = _parse_market_record(
            MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        )
        upsert_market(rec, db_path=tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM markets WHERE condition_id = ?",
            (rec["condition_id"],),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["condition_id"] == "0xabc123def456"
        assert row["question"].startswith("What will the cumulative")
        brackets = json.loads(row["brackets"])
        assert brackets == ["<30", "30-40", "40-50", "50-60", "60-70", "70+"]

    def test_upsert_updates_existing(self, tmp_db):
        rec = _parse_market_record(
            MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        )
        upsert_market(rec, db_path=tmp_db)

        # Update the question and upsert again.
        rec["question"] = "Updated question?"
        upsert_market(rec, db_path=tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM markets WHERE condition_id = ?",
            (rec["condition_id"],),
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["question"] == "Updated question?"


class TestInsertPriceSnapshot:
    def test_insert_snapshot(self, tmp_db):
        # Must insert market first due to foreign key constraint.
        rec = _parse_market_record(
            MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        )
        upsert_market(rec, db_path=tmp_db)

        insert_price_snapshot(
            condition_id="0xabc123def456",
            bracket="50-60",
            bid=0.34,
            ask=0.36,
            last_price=0.35,
            volume=125000.50,
            snapshot_at="2026-02-18T12:00:00Z",
            db_path=tmp_db,
        )

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM market_prices").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["condition_id"] == "0xabc123def456"
        assert rows[0]["bracket"] == "50-60"
        assert rows[0]["bid"] == pytest.approx(0.34)
        assert rows[0]["ask"] == pytest.approx(0.36)
        assert rows[0]["last_price"] == pytest.approx(0.35)

    def test_multiple_snapshots_same_market(self, tmp_db):
        rec = _parse_market_record(
            MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"][0]
        )
        upsert_market(rec, db_path=tmp_db)

        for ts in ["2026-02-18T12:00:00Z", "2026-02-18T13:00:00Z"]:
            insert_price_snapshot(
                condition_id="0xabc123def456",
                bracket="50-60",
                bid=0.34,
                ask=0.36,
                last_price=0.35,
                volume=125000.0,
                snapshot_at=ts,
                db_path=tmp_db,
            )

        conn = sqlite3.connect(str(tmp_db))
        rows = conn.execute("SELECT COUNT(*) FROM market_prices").fetchone()
        conn.close()
        assert rows[0] == 2


# ---------------------------------------------------------------------------
# Snapshot integration test (mocked HTTP, real DB)
# ---------------------------------------------------------------------------

class TestSnapshotPrices:
    @patch("trading.polymarket.get_last_trade_price")
    @patch("trading.polymarket.get_order_book")
    @patch("trading.polymarket.search_flu_markets")
    def test_snapshot_stores_all_brackets(
        self, mock_search, mock_book, mock_ltp, tmp_db
    ):
        mock_search.return_value = (
            MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"]
        )
        mock_book.return_value = MOCK_ORDER_BOOK
        mock_ltp.return_value = 0.35

        results = snapshot_prices(include_order_books=True, db_path=tmp_db)
        assert len(results) == 1

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row

        # Check market was upserted.
        market_rows = conn.execute("SELECT * FROM markets").fetchall()
        assert len(market_rows) == 1

        # Check price snapshots: one per bracket (6 brackets).
        price_rows = conn.execute("SELECT * FROM market_prices").fetchall()
        assert len(price_rows) == 6

        brackets = {r["bracket"] for r in price_rows}
        # Should contain our standard brackets.
        assert "<30" in brackets
        assert "70+" in brackets

        conn.close()

    @patch("trading.polymarket.search_flu_markets")
    def test_snapshot_no_markets_no_crash(self, mock_search, tmp_db):
        mock_search.return_value = []
        results = snapshot_prices(db_path=tmp_db)
        assert results == []

    @patch("trading.polymarket.get_last_trade_price")
    @patch("trading.polymarket.get_order_book")
    @patch("trading.polymarket.search_flu_markets")
    def test_snapshot_without_order_books(
        self, mock_search, mock_book, mock_ltp, tmp_db
    ):
        mock_search.return_value = (
            MOCK_GAMMA_SEARCH_RESPONSE["events"][0]["markets"]
        )
        # Order book should NOT be called when include_order_books=False.
        results = snapshot_prices(include_order_books=False, db_path=tmp_db)
        assert len(results) == 1
        mock_book.assert_not_called()

        conn = sqlite3.connect(str(tmp_db))
        price_rows = conn.execute("SELECT * FROM market_prices").fetchall()
        conn.close()
        # Still writes price rows (using Gamma prices), just no bid/ask from CLOB.
        assert len(price_rows) == 6
