-- FluSight Edge Database Schema

-- Raw signal observations
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_name TEXT NOT NULL,
    epiweek INTEGER NOT NULL,
    value REAL NOT NULL,
    raw_value REAL NOT NULL,
    unit TEXT NOT NULL,
    geography TEXT NOT NULL DEFAULT 'national',
    fetched_at TEXT NOT NULL,
    source_url TEXT,
    metadata TEXT,  -- JSON blob
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(signal_name, epiweek, geography, fetched_at)
);

-- FluSurv-NET revision history (for backfill model)
CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    epiweek INTEGER NOT NULL,
    report_epiweek INTEGER NOT NULL,  -- When this version was published
    lag INTEGER NOT NULL,  -- report_epiweek - epiweek
    cumulative_rate REAL NOT NULL,
    weekly_rate REAL,
    geography TEXT NOT NULL DEFAULT 'network_all',
    fetched_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(epiweek, report_epiweek, geography)
);

-- Model predictions
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    target_epiweek INTEGER NOT NULL,
    bracket TEXT NOT NULL,
    probability REAL NOT NULL,
    point_estimate REAL,
    metadata TEXT,  -- JSON: model params, feature importances, etc.
    created_at TEXT DEFAULT (datetime('now'))
);

-- Polymarket state
CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL UNIQUE,
    question TEXT NOT NULL,
    target_epiweek INTEGER,
    brackets TEXT NOT NULL,  -- JSON array of bracket strings
    resolved BOOLEAN DEFAULT FALSE,
    resolution_bracket TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Market prices (snapshots)
CREATE TABLE IF NOT EXISTS market_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    bracket TEXT NOT NULL,
    bid REAL,
    ask REAL,
    last_price REAL,
    volume REAL,
    snapshot_at TEXT NOT NULL,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

-- Trades
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    bracket TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    price REAL NOT NULL,
    size REAL NOT NULL,
    model_prob REAL NOT NULL,
    market_prob REAL NOT NULL,
    edge REAL NOT NULL,
    kelly_fraction REAL NOT NULL,
    order_id TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'filled', 'partial', 'cancelled', 'failed')),
    paper BOOLEAN DEFAULT TRUE,
    created_at TEXT DEFAULT (datetime('now')),
    filled_at TEXT,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

-- P&L tracking
CREATE TABLE IF NOT EXISTS pnl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL,
    bracket TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,  -- NULL until resolved
    size REAL NOT NULL,
    pnl REAL,  -- NULL until resolved
    resolved BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_signals_name_week ON signals(signal_name, epiweek);
CREATE INDEX IF NOT EXISTS idx_revisions_week ON revisions(epiweek);
CREATE INDEX IF NOT EXISTS idx_revisions_lag ON revisions(lag);
CREATE INDEX IF NOT EXISTS idx_predictions_week ON predictions(target_epiweek);
CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);
CREATE INDEX IF NOT EXISTS idx_market_prices_condition ON market_prices(condition_id);
