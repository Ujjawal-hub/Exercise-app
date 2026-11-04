"""Database helpers: open a connection and create the tables.

Run once from the project root to create data/app.db:
    python -m backend.app.db
"""

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "app.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# My own (custom) exercises get ids from here upwards. wger ids stay below it.
CUSTOM_ID_START = 1_000_000


def get_connection():
    """Open the database. Rows can be read by column name, e.g. row["name"]."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite does not check foreign keys unless we switch it on for each connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_columns(conn, table):
    """Column names of a table, or an empty set if the table does not exist yet."""
    rows = conn.execute("SELECT name FROM pragma_table_info(?)", (table,)).fetchall()
    return {row["name"] for row in rows}


def upgrade_old_database(conn):
    """Bring a database made by an older schema.sql up to date. Safe to run again.

    "CREATE TABLE IF NOT EXISTS" never changes a table that already exists,
    so new columns must be added here by hand.
    """
    # Added in step 3: exercises.source ('wger' or 'custom').
    columns = table_columns(conn, "exercises")
    if columns and "source" not in columns:
        conn.execute(
            "ALTER TABLE exercises ADD COLUMN source TEXT NOT NULL DEFAULT 'wger' "
            "CHECK (source IN ('wger', 'custom'))"
        )

    # Added in step 3 part 3: source and reviewed flag for my custom exercises.
    # Empty (NULL) for the wger exercises that are already there.
    columns = table_columns(conn, "exercises")
    if columns and "source_name" not in columns:
        conn.execute("ALTER TABLE exercises ADD COLUMN source_name TEXT")
    if columns and "source_url" not in columns:
        conn.execute("ALTER TABLE exercises ADD COLUMN source_url TEXT")
    if columns and "reviewed" not in columns:
        conn.execute(
            "ALTER TABLE exercises ADD COLUMN reviewed INTEGER CHECK (reviewed IN (0, 1))"
        )

    # Added in step 3: form_guides.name and form_guides.demo_url.
    # The old form tables were never filled, so the simplest upgrade is to drop
    # them and let schema.sql create them again. Refuse if they hold any data.
    columns = table_columns(conn, "form_guides")
    if columns and "name" not in columns:
        if conn.execute("SELECT COUNT(*) FROM form_guides").fetchone()[0]:
            raise RuntimeError("form_guides has data; upgrade it by hand, not by dropping it.")
        conn.execute("DROP TABLE IF EXISTS form_mistakes")
        conn.execute("DROP TABLE IF EXISTS form_steps")
        conn.execute("DROP TABLE form_guides")

    # Added in step 3 part 4: routines.reviewed (0 = draft, 1 = checked by me).
    columns = table_columns(conn, "routines")
    if columns and "reviewed" not in columns:
        conn.execute(
            "ALTER TABLE routines ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0 "
            "CHECK (reviewed IN (0, 1))"
        )

    # Added in step 3 part 2: form_guides.reviewed (0 = draft, 1 = checked by me).
    # Read the columns again: the block above may have just dropped the table.
    columns = table_columns(conn, "form_guides")
    if columns and "reviewed" not in columns:
        conn.execute(
            "ALTER TABLE form_guides ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0 "
            "CHECK (reviewed IN (0, 1))"
        )


def create_tables():
    """Create all tables from schema.sql (upgrading an old database first). Safe to run again."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        upgrade_old_database(conn)
        conn.commit()
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
