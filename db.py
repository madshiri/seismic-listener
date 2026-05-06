"""
db.py — SQLite database setup and core queries for the seismic listener.

Exposes three functions:
  - init_db(conn)              : create tables if they do not exist.
  - insert_event(conn, event, source_agency) : insert with dedup via INSERT OR IGNORE.
  - get_latest_timestamp(conn) : return the most recent event timestamp, or None.

Connection lifecycle is managed by the caller (cli.py). All functions
accept an open sqlite3.Connection and do not open or close it themselves.
"""

import sqlite3
from datetime import datetime, timezone

from models import SeismicEvent


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    eid             INTEGER  NOT NULL,
    timestamp       TEXT     NOT NULL,   -- ISO 8601 with UTC offset, e.g. 2024-01-01T12:00:00+00:00
    lat             REAL     NOT NULL,
    lon             REAL     NOT NULL,
    depth           REAL     NOT NULL,
    Mw              REAL     NOT NULL,
    dist            REAL     NOT NULL,
    azi             REAL     NOT NULL,
    loclat          REAL     NOT NULL,
    loclon          REAL     NOT NULL,
    source_agency   TEXT     NOT NULL,   -- name of the agency that delivered this event
    inserted_at     TEXT     NOT NULL,   -- ISO 8601 wall-clock time of local insertion

    PRIMARY KEY (eid, timestamp)         -- composite key drives INSERT OR IGNORE dedup
);
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """Create the events table if it does not already exist.

    Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS.
    """
    conn.execute(_CREATE_EVENTS_TABLE)
    conn.commit()


def insert_event(
    conn: sqlite3.Connection,
    event: SeismicEvent,
    source_agency: str,
) -> bool:
    """Persist a seismic event, silently ignoring duplicates.

    Deduplication is handled by the composite PRIMARY KEY (eid, timestamp):
    if a row with the same (eid, timestamp) already exists, the INSERT is
    ignored and this function returns False. Returns True when the row is
    newly inserted.

    Args:
        conn:          Open SQLite connection.
        event:         Validated SeismicEvent instance.
        source_agency: Name of the agency that delivered the event.

    Returns:
        True if the event was inserted, False if it was a duplicate.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO events (
            eid, timestamp, lat, lon, depth, Mw,
            dist, azi, loclat, loclon,
            source_agency, inserted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.eid,
            event.timestamp.isoformat(),
            event.lat,
            event.lon,
            event.depth,
            event.Mw,
            event.dist,
            event.azi,
            event.loclat,
            event.loclon,
            source_agency,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return cursor.rowcount == 1


def get_latest_timestamp(conn: sqlite3.Connection) -> datetime | None:
    """Return the UTC timestamp of the most recently stored event.

    Returns None when the events table is empty (e.g. on first run),
    allowing the caller to decide how far back to request data.

    The value is returned as a timezone-aware datetime (UTC).
    """
    row = conn.execute(
        "SELECT MAX(timestamp) FROM events;"
    ).fetchone()

    if row is None or row[0] is None:
        return None

    return datetime.fromisoformat(row[0])
