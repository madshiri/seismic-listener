"""
test_processor.py — Tests for the process_records function.

Covers:
  - Valid records are inserted and summary reflects correct counts.
  - Invalid record (Mw=15.0) is rejected, logged to anomaly file, summary increments invalid.
  - Duplicate record is silently skipped and summary increments duplicates.
  - Mixed batch with valid, invalid, and duplicate records returns correct summary counts.
  - Anomaly log file contains one line per invalid record.
  - Anomaly log line contains agency name and eid.
  - Empty batch returns all-zero summary.
  - Anomaly log is not written for duplicates.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from db import init_db
from processor import process_records


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


@pytest.fixture
def anomaly_log(tmp_path) -> Path:
    """Provide a temporary anomaly log file path per test."""
    return tmp_path / "anomalies.log"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS_BASE = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_AGENCY  = "AgencyA"


def _valid_raw(eid: int = 1, timestamp: datetime = _TS_BASE) -> dict:
    """Return a valid raw seismic event dict."""
    return {
        "eid":       eid,
        "timestamp": timestamp.isoformat(),
        "lat":       0.0,
        "lon":       0.0,
        "depth":     -10.0,
        "Mw":        5.0,
        "dist":      100.0,
        "azi":       0.0,
        "loclat":    0.0,
        "loclon":    0.0,
    }


def _invalid_mw(eid: int = 99) -> dict:
    """Return a raw dict with an out-of-range Mw (simulates every-30th injection)."""
    return {**_valid_raw(eid=eid), "Mw": 15.0}


def _invalid_depth(eid: int = 98) -> dict:
    """Return a raw dict with an out-of-range depth (simulates every-50th injection)."""
    return {**_valid_raw(eid=eid), "depth": 30.0}


# ---------------------------------------------------------------------------
# Empty batch
# ---------------------------------------------------------------------------

class TestEmptyBatch:
    def test_empty_batch_returns_zero_summary(self, conn, anomaly_log):
        summary = process_records([], _AGENCY, conn, anomaly_log)
        assert summary == {"inserted": 0, "duplicates": 0, "invalid": 0}

    def test_empty_batch_does_not_create_anomaly_log(self, conn, anomaly_log):
        process_records([], _AGENCY, conn, anomaly_log)
        assert not anomaly_log.exists()


# ---------------------------------------------------------------------------
# Valid records
# ---------------------------------------------------------------------------

class TestValidRecords:
    def test_single_valid_record_inserted(self, conn, anomaly_log):
        summary = process_records([_valid_raw(eid=1)], _AGENCY, conn, anomaly_log)
        assert summary["inserted"] == 1
        assert summary["duplicates"] == 0
        assert summary["invalid"] == 0

    def test_multiple_valid_records_all_inserted(self, conn, anomaly_log):
        records = [
            _valid_raw(eid=1, timestamp=_TS_BASE),
            _valid_raw(eid=2, timestamp=_TS_BASE + timedelta(hours=1)),
            _valid_raw(eid=3, timestamp=_TS_BASE + timedelta(hours=2)),
        ]
        summary = process_records(records, _AGENCY, conn, anomaly_log)
        assert summary["inserted"] == 3
        assert summary["duplicates"] == 0
        assert summary["invalid"] == 0


# ---------------------------------------------------------------------------
# Invalid records
# ---------------------------------------------------------------------------

class TestInvalidRecords:
    def test_invalid_mw_increments_invalid_count(self, conn, anomaly_log):
        summary = process_records([_invalid_mw()], _AGENCY, conn, anomaly_log)
        assert summary["invalid"] == 1
        assert summary["inserted"] == 0

    def test_invalid_depth_increments_invalid_count(self, conn, anomaly_log):
        summary = process_records([_invalid_depth()], _AGENCY, conn, anomaly_log)
        assert summary["invalid"] == 1
        assert summary["inserted"] == 0

    def test_invalid_record_not_stored_in_db(self, conn, anomaly_log):
        process_records([_invalid_mw(eid=99)], _AGENCY, conn, anomaly_log)
        count = conn.execute("SELECT COUNT(*) FROM events;").fetchone()[0]
        assert count == 0

    def test_anomaly_log_written_for_invalid_record(self, conn, anomaly_log):
        process_records([_invalid_mw()], _AGENCY, conn, anomaly_log)
        assert anomaly_log.exists()
        assert anomaly_log.stat().st_size > 0

    def test_anomaly_log_contains_one_line_per_invalid(self, conn, anomaly_log):
        records = [_invalid_mw(eid=99), _invalid_depth(eid=98)]
        process_records(records, _AGENCY, conn, anomaly_log)
        lines = anomaly_log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_anomaly_log_line_contains_agency_name(self, conn, anomaly_log):
        process_records([_invalid_mw(eid=99)], _AGENCY, conn, anomaly_log)
        content = anomaly_log.read_text(encoding="utf-8")
        assert _AGENCY in content

    def test_anomaly_log_line_contains_eid(self, conn, anomaly_log):
        process_records([_invalid_mw(eid=99)], _AGENCY, conn, anomaly_log)
        content = anomaly_log.read_text(encoding="utf-8")
        assert "eid=99" in content


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------

class TestDuplicates:
    def test_duplicate_increments_duplicates_count(self, conn, anomaly_log):
        record = _valid_raw(eid=1)
        process_records([record], _AGENCY, conn, anomaly_log)
        summary = process_records([record], _AGENCY, conn, anomaly_log)
        assert summary["duplicates"] == 1
        assert summary["inserted"] == 0

    def test_anomaly_log_not_written_for_duplicate(self, conn, anomaly_log):
        record = _valid_raw(eid=1)
        process_records([record], _AGENCY, conn, anomaly_log)
        # Remove log if created on first insert, then re-check after duplicate.
        if anomaly_log.exists():
            anomaly_log.unlink()
        process_records([record], _AGENCY, conn, anomaly_log)
        assert not anomaly_log.exists()

    def test_duplicate_from_different_agency_not_inserted(self, conn, anomaly_log):
        record = _valid_raw(eid=1)
        process_records([record], "AgencyA", conn, anomaly_log)
        summary = process_records([record], "AgencyB", conn, anomaly_log)
        assert summary["duplicates"] == 1
        assert summary["inserted"] == 0


# ---------------------------------------------------------------------------
# Mixed batch
# ---------------------------------------------------------------------------

class TestMixedBatch:
    def test_mixed_batch_summary_counts_correct(self, conn, anomaly_log):
        # Pre-insert eid=1 to create a duplicate.
        process_records([_valid_raw(eid=1)], _AGENCY, conn, anomaly_log)

        batch = [
            _valid_raw(eid=1),                                          # duplicate
            _valid_raw(eid=2, timestamp=_TS_BASE + timedelta(hours=1)), # valid new
            _valid_raw(eid=3, timestamp=_TS_BASE + timedelta(hours=2)), # valid new
            _invalid_mw(eid=99),                                        # invalid
            _invalid_depth(eid=98),                                     # invalid
        ]
        summary = process_records(batch, _AGENCY, conn, anomaly_log)
        assert summary["inserted"]   == 2
        assert summary["duplicates"] == 1
        assert summary["invalid"]    == 2

    def test_mixed_batch_anomaly_log_has_correct_line_count(self, conn, anomaly_log):
        batch = [
            _valid_raw(eid=1),
            _invalid_mw(eid=99),
            _invalid_depth(eid=98),
        ]
        process_records(batch, _AGENCY, conn, anomaly_log)
        lines = anomaly_log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
