"""Database helpers: open a connection and create the tables.

Run once from the project root to create data/app.db:
    python -m backend.app.db
"""

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "app.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_connection():
    """Open the database. Rows can be read by column name, e.g. row["name"]."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite does not check foreign keys unless we switch it on for each connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    """Create all tables from schema.sql. Safe to run again."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def list_tables():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ? ORDER BY name", ("table",)
        ).fetchall()
        return [row["name"] for row in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    create_tables()
    print(f"Database ready: {DB_PATH}")
    for name in list_tables():
        print(" -", name)
