"""
test_db.py — Tests for database setup and core query functions.

Covers:
  - init_db creates the events table.
  - insert_event returns True on first insert.
  - insert_event returns False on duplicate (eid, timestamp).
  - Two events with same eid but different timestamp are both inserted.
  - Two events with same timestamp but different eid are both inserted.
  - get_latest_timestamp returns None on empty table.
  - get_latest_timestamp returns the most recent timestamp across multiple events.
  - get_latest_timestamp returns a timezone-aware datetime.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from db import get_latest_timestamp, init_db, insert_event
from models import SeismicEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """Provide a fresh in-memory SQLite connection per test."""
    connection = sqlite3.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS_BASE = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_event(eid: int = 1, timestamp: datetime = _TS_BASE, **overrides) -> SeismicEvent:
    """Return a valid SeismicEvent with optional field overrides."""
    fields = {
        "eid":       eid,
        "timestamp": timestamp,
        "lat":       0.0,
        "lon":       0.0,
        "depth":     -10.0,
        "Mw":        5.0,
        "dist":      100.0,
        "azi":       0.0,
        "loclat":    0.0,
        "loclon":    0.0,
    }
    fields.update(overrides)
    return SeismicEvent(**fields)


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

class TestInitDb:
    def test_events_table_exists_after_init(self, conn):
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events';"
        ).fetchone()
        assert row is not None

    def test_init_db_is_idempotent(self, conn):
        # Calling init_db a second time must not raise or duplicate the table.
        init_db(conn)
        rows = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='events';"
        ).fetchone()
        assert rows[0] == 1


# ---------------------------------------------------------------------------
# insert_event
# ---------------------------------------------------------------------------

class TestInsertEvent:
    def test_first_insert_returns_true(self, conn):
        event = _make_event()
        assert insert_event(conn, event, "AgencyA") is True

    def test_duplicate_returns_false(self, conn):
        event = _make_event()
        insert_event(conn, event, "AgencyA")
        assert insert_event(conn, event, "AgencyA") is False

    def test_duplicate_from_different_agency_returns_false(self, conn):
        event = _make_event()
        insert_event(conn, event, "AgencyA")
        # Same (eid, timestamp) from fallback agency is still a duplicate.
        assert insert_event(conn, event, "AgencyB") is False

    def test_same_eid_different_timestamp_both_inserted(self, conn):
        ts1 = _TS_BASE
        ts2 = _TS_BASE + timedelta(hours=1)
        assert insert_event(conn, _make_event(eid=1, timestamp=ts1), "AgencyA") is True
        assert insert_event(conn, _make_event(eid=1, timestamp=ts2), "AgencyA") is True
        count = conn.execute("SELECT COUNT(*) FROM events;").fetchone()[0]
        assert count == 2

    def test_same_timestamp_different_eid_both_inserted(self, conn):
        assert insert_event(conn, _make_event(eid=1, timestamp=_TS_BASE), "AgencyA") is True
        assert insert_event(conn, _make_event(eid=2, timestamp=_TS_BASE), "AgencyA") is True
        count = conn.execute("SELECT COUNT(*) FROM events;").fetchone()[0]
        assert count == 2

    def test_source_agency_stored_correctly(self, conn):
        event = _make_event()
        insert_event(conn, event, "AgencyA")
        row = conn.execute("SELECT source_agency FROM events WHERE eid=1;").fetchone()
        assert row[0] == "AgencyA"


# ---------------------------------------------------------------------------
# get_latest_timestamp
# ---------------------------------------------------------------------------

class TestGetLatestTimestamp:
    def test_returns_none_on_empty_table(self, conn):
        assert get_latest_timestamp(conn) is None

    def test_returns_most_recent_timestamp(self, conn):
        ts1 = _TS_BASE
        ts2 = _TS_BASE + timedelta(hours=1)
        ts3 = _TS_BASE + timedelta(hours=2)
        insert_event(conn, _make_event(eid=1, timestamp=ts1), "AgencyA")
        insert_event(conn, _make_event(eid=2, timestamp=ts3), "AgencyA")
        insert_event(conn, _make_event(eid=3, timestamp=ts2), "AgencyA")
        assert get_latest_timestamp(conn) == ts3

    def test_returns_timezone_aware_datetime(self, conn):
        insert_event(conn, _make_event(), "AgencyA")
        result = get_latest_timestamp(conn)
        assert result is not None
        assert result.tzinfo is not None

    def test_returns_exact_timestamp_for_single_event(self, conn):
        insert_event(conn, _make_event(timestamp=_TS_BASE), "AgencyA")
        assert get_latest_timestamp(conn) == _TS_BASE
