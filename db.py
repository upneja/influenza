"""SQLite database helpers for FluSight Edge."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import DB_PATH

def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize database from schema.sql."""
    schema = Path(__file__).parent / "schema.sql"
    with get_connection(db_path) as conn:
        conn.executescript(schema.read_text())

@contextmanager
def get_connection(db_path: Path = DB_PATH):
    """Get a database connection with WAL mode and foreign keys enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def insert_signal(signal_name: str, epiweek: int, value: float, raw_value: float,
                  unit: str, geography: str, fetched_at: str, source_url: str = "",
                  metadata: dict | None = None, db_path: Path = DB_PATH) -> None:
    """Insert a signal observation, ignoring duplicates."""
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO signals
               (signal_name, epiweek, value, raw_value, unit, geography, fetched_at, source_url, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal_name, epiweek, value, raw_value, unit, geography, fetched_at,
             source_url, json.dumps(metadata) if metadata else None)
        )

def insert_revision(epiweek: int, report_epiweek: int, lag: int, cumulative_rate: float,
                    weekly_rate: float | None, geography: str, fetched_at: str,
                    db_path: Path = DB_PATH) -> None:
    """Insert a FluSurv-NET revision record, ignoring duplicates."""
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO revisions
               (epiweek, report_epiweek, lag, cumulative_rate, weekly_rate, geography, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (epiweek, report_epiweek, lag, cumulative_rate, weekly_rate, geography, fetched_at)
        )

def get_signals(signal_name: str, epiweek: int | None = None,
                geography: str | None = None, db_path: Path = DB_PATH) -> list[dict]:
    """Query signal observations."""
    query = "SELECT * FROM signals WHERE signal_name = ?"
    params: list = [signal_name]
    if epiweek is not None:
        query += " AND epiweek = ?"
        params.append(epiweek)
    if geography is not None:
        query += " AND geography = ?"
        params.append(geography)
    query += " ORDER BY epiweek DESC, fetched_at DESC"
    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def get_revisions(epiweek: int | None = None, db_path: Path = DB_PATH) -> list[dict]:
    """Query FluSurv-NET revision history."""
    query = "SELECT * FROM revisions"
    params: list = []
    if epiweek is not None:
        query += " WHERE epiweek = ?"
        params.append(epiweek)
    query += " ORDER BY epiweek, lag"
    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def get_revision_curves(db_path: Path = DB_PATH) -> list[dict]:
    """Get revision curves: for each epiweek, the rate at each lag."""
    query = """
        SELECT epiweek, lag, cumulative_rate, geography
        FROM revisions
        ORDER BY epiweek, lag
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]
