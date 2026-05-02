"""
db.py — SQLite connection helper and schema bootstrap.
All DB access in this project goes through get_connection().
"""

import sqlite3
import logging
from pathlib import Path
from config import cfg

logger = logging.getLogger(__name__)

DB_PATH = Path(cfg.DB_PATH)


def get_connection() -> sqlite3.Connection:
    """Return a sqlite3 connection with row_factory set to Row."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def bootstrap_schema() -> None:
    """Create all tables and indexes if they don't exist yet."""
    ddl = """
    CREATE TABLE IF NOT EXISTS kb_chunks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        heading     TEXT    NOT NULL,
        keywords    TEXT,
        content     TEXT    NOT NULL,
        embedding   BLOB    NOT NULL,
        source_file TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS response_cache (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        question    TEXT    NOT NULL,
        answer      TEXT    NOT NULL,
        embedding   BLOB    NOT NULL,
        hit_count   INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS conversations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT    NOT NULL,
        role        TEXT    NOT NULL,
        content     TEXT    NOT NULL,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_conv_session
        ON conversations(session_id, created_at);
    """
    with get_connection() as conn:
        conn.executescript(ddl)
        conn.commit()
    logger.info("DB schema bootstrapped at %s", DB_PATH)
