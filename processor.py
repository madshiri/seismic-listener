"""
processor.py — Validation, deduplication, anomaly logging, and storage.

Exposes one function:
  - process_records(records, agency_name, conn, anomaly_log_path)
      Validates each raw dict, stores valid events, logs anomalies to a flat
      file, and returns a summary of the poll cycle.

Anomaly policy:
  - Validation failures  → logged to anomaly file + WARNING in app log.
  - Duplicates           → silently ignored at DEBUG level, not anomalies.
  - Successful inserts   → logged at DEBUG level.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from db import insert_event
from models import SeismicEvent

logger = logging.getLogger(__name__)

# Anomaly log line template — pipe-delimited for easy grep/awk parsing.
_ANOMALY_LINE = "{ts} | {agency} | eid={eid} | {error}\n"


def process_records(
    records: list[dict],
    agency_name: str,
    conn: sqlite3.Connection,
    anomaly_log_path: Path,
) -> dict[str, int]:
    """Validate, deduplicate, and store a batch of raw seismic event dicts.

    For each record:
      - Attempts Pydantic validation against SeismicEvent.
      - On failure: writes a line to the anomaly log and increments invalid count.
      - On success: calls insert_event; increments inserted or duplicates count.

    Args:
        records:          Raw dicts as returned by fetcher.fetch_events.
        agency_name:      Name of the agency that delivered this batch.
        conn:             Open SQLite connection (managed by caller).
        anomaly_log_path: Path to the flat anomaly audit log file.

    Returns:
        A dict with keys 'inserted', 'duplicates', and 'invalid', each
        mapping to an integer count for this poll cycle.
    """
    summary = {"inserted": 0, "duplicates": 0, "invalid": 0}

    # Opened lazily on the first anomaly so the file is never created for
    # batches that contain no invalid records.
    anomaly_fh = None

    try:
        for raw in records:
            eid = raw.get("eid", "unknown")

            # --- Validation ----------------------------------------------
            try:
                event = SeismicEvent.model_validate(raw)
            except ValidationError as exc:
                summary["invalid"] += 1
                # Open the log file on the first anomaly in this batch.
                if anomaly_fh is None:
                    try:
                        anomaly_fh = anomaly_log_path.open("a", encoding="utf-8")
                    except OSError as open_exc:
                        logger.error(
                            "Could not open anomaly log '%s': %s. "
                            "Anomalies will not be recorded.",
                            anomaly_log_path, open_exc,
                        )
                _log_anomaly(anomaly_fh, agency_name, eid, exc)
                logger.warning(
                    "Validation failure from agency '%s' for eid=%s: %s",
                    agency_name, eid, exc.error_count(),
                )
                continue

            # --- Deduplication + storage ---------------------------------
            inserted = insert_event(conn, event, agency_name)

            if inserted:
                summary["inserted"] += 1
                logger.debug(
                    "Inserted event eid=%s from agency '%s'.", event.eid, agency_name
                )
            else:
                summary["duplicates"] += 1
                logger.debug(
                    "Duplicate skipped: eid=%s timestamp=%s from agency '%s'.",
                    event.eid, event.timestamp.isoformat(), agency_name,
                )
    finally:
        if anomaly_fh is not None:
            anomaly_fh.close()

    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_anomaly(
    anomaly_fh,
    agency_name: str,
    eid: object,
    exc: ValidationError,
) -> None:
    """Write a single anomaly line to the already-open audit log file handle.

    Each line is pipe-delimited and contains:
      - UTC timestamp of detection
      - Agency name
      - Event ID (or 'unknown' if missing from payload)
      - Human-readable validation error summary

    Does nothing if the file handle is None (e.g. log could not be opened).
    """
    if anomaly_fh is None:
        return

    ts = datetime.now(timezone.utc).isoformat()
    errors = "; ".join(
        f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    line = _ANOMALY_LINE.format(
        ts=ts,
        agency=agency_name,
        eid=eid,
        error=errors,
    )

    try:
        anomaly_fh.write(line)
    except OSError as os_exc:
        logger.error(
            "Could not write to anomaly log: %s", os_exc
        )
