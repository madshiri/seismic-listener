# Seismic Listener

A fault-tolerant seismic event listener that polls two remote agencies for JSON data, validates incoming records, deduplicates across agency switches, and persists clean events to a local SQLite database.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Tools and Technologies](#tools-and-technologies)
- [Design Decisions](#design-decisions)
- [Installation](#installation)
- [Running the Simulator](#running-the-simulator)
- [Running the Listener](#running-the-listener)
- [Running the Tests](#running-the-tests)
- [CLI Reference](#cli-reference)
- [AI Assistant](#ai-assistant)

---

## Overview

The listener polls a primary agency (A) every `m` minutes. If agency A fails, it switches immediately to a fallback agency (B). After a configurable number of polls on B, it probes A again and switches back only if A responds successfully. All events are validated against strict field constraints before storage. Invalid records are logged to an anomaly audit file. Duplicates that arise during agency switching are silently ignored via a composite primary key `(eid, timestamp)`.

---

## Project Structure

```
seismic_listener/
├── config.py        — AgencyConfig and AppConfig dataclasses
├── models.py        — SeismicEvent Pydantic model with field validation
├── db.py            — SQLite schema setup and core queries
├── fetcher.py       — Single-agency HTTP fetch (no state, no retry logic)
├── failover.py      — Primary/fallback switching state machine
├── processor.py     — Validation, deduplication, anomaly logging, and storage
├── simulator.py     — Two FastAPI apps simulating agency A and B for testing
└── cli.py           — Argument parsing, logging setup, and polling loop

├──tests/
    ├── test_models.py   — SeismicEvent field validation tests
    ├── test_db.py       — Database setup and query tests
    ├── test_fetcher.py  — HTTP fetch and failure handling tests
    └── test_processor.py — Validation, dedup, and anomaly logging tests
```

---

## Tools and Technologies

| Layer | Tool / Library | Purpose |
|---|---|---|
| Language | Python 3.11+ | Core implementation |
| Data validation | Pydantic v2 | SeismicEvent model and field constraints |
| HTTP client | requests | Fetching data from agencies |
| Database | SQLite (stdlib) | Persistent event storage |
| Web framework | FastAPI + Uvicorn | Simulated agency endpoints |
| Testing | pytest | Test runner |
| Mocking | unittest.mock | HTTP layer mocking in fetcher tests |

---

## Design Decisions

### Separation of concerns

Each file has a single responsibility. `fetcher.py` knows only how to make one HTTP request. `failover.py` owns all switching state. `processor.py` owns validation, deduplication, and anomaly logging. `cli.py` owns the loop and nothing else. This makes each component independently testable and replaceable.

### Strict validation with Pydantic v2

All field bounds from the specification are enforced at parse time using Pydantic's `ge`/`le` constraints. Timestamps use `AwareDatetime`, which rejects naive datetimes outright. This means invalid data is caught immediately on arrival, before it touches the database, and is logged to the anomaly file for auditing.

### Deduplication via composite primary key

Events are deduplicated using `INSERT OR IGNORE` on a composite primary key `(eid, timestamp)`. This avoids a separate `SELECT` before every insert and correctly handles the case where the same event is delivered by both agencies during a switch. There is no in-memory seen-set — the database is the single source of truth.

### One HTTP attempt per agency per poll

There is no per-request retry logic. Each agency gets exactly one attempt per poll cycle. This keeps the fetcher simple and stateless. The failover mechanism at the router level provides resilience at a coarser granularity, which is appropriate for a polling system with a configurable interval.

### Lazy anomaly log creation

The anomaly log file is opened only when the first invalid record is encountered in a batch. Batches with no invalid records never create or touch the file. This avoids creating empty log files during normal operation and makes it easy to check whether any anomalies have ever been recorded.

### Clean shutdown on SIGINT / SIGTERM

The polling loop checks a shutdown flag between the end of a poll cycle and the start of the sleep. The sleep itself runs in one-second increments so the listener responds to signals within one second rather than waiting out the full poll interval. The current poll cycle always completes before exit to avoid partial writes.

### UTC everywhere

All timestamps are stored and compared as UTC ISO 8601 strings with explicit offsets (e.g. `2024-01-01T12:00:00+00:00`). `datetime.now(timezone.utc)` is used throughout instead of `datetime.utcnow()` or local time. Lexicographic ordering of ISO 8601 strings matches chronological order, so `MAX(timestamp)` in SQLite is correct without any conversion.

### Single connection passed by the caller

`cli.py` opens one SQLite connection at startup and passes it to all functions that need it. This avoids repeated open/close overhead and keeps connection lifecycle explicit and visible in one place.

---

## Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install pydantic requests fastapi uvicorn pytest
```

---

## Running the Simulator

The simulator exposes two FastAPI apps on separate ports. Launch each in its own terminal:

```bash
# Terminal 1 — primary agency (all 150 events)
uvicorn simulator:app_a --port 8000

# Terminal 2 — fallback agency (first 143 events)
uvicorn simulator:app_b --port 8001
```

Both agencies filter events by the `since` query parameter and inject bad records at fixed indices (every 30th event has `Mw=15.0`, every 50th has `depth=+30.0`) to exercise the anomaly logging pipeline.

---

## Running the Listener

With the simulator running, start the listener with default settings:

```bash
python cli.py
```

Or override individual settings:

```bash
python cli.py \
  --primary-url http://localhost:8000/events \
  --fallback-url http://localhost:8001/events \
  --poll-interval 1 \
  --primary-retry-after 3 \
  --db-path seismic.db \
  --anomaly-log anomalies.log \
  --log-level DEBUG
```

---

## Running the Tests

```bash
pytest tests/ -v
```

Tests use in-memory SQLite and `tmp_path` fixtures so they leave no files on disk and require no running services.

---

## CLI Reference

| Argument | Default | Description |
|---|---|---|
| `--primary-url` | `http://localhost:8000/events` | URL of the primary agency |
| `--primary-timeout` | `10.0` | Request timeout in seconds for primary |
| `--fallback-url` | `http://localhost:8001/events` | URL of the fallback agency |
| `--fallback-timeout` | `10.0` | Request timeout in seconds for fallback |
| `--poll-interval` | `5` | Polling interval in minutes |
| `--db-path` | `seismic.db` | Path to the SQLite database file |
| `--anomaly-log` | `anomalies.log` | Path to the anomaly audit log |
| `--primary-retry-after` | `3` | Fallback polls before re-probing primary |
| `--log-level` | `INFO` | Log verbosity: DEBUG, INFO, WARNING, ERROR |

---

## AI Assistant

This project was developed with [Claude Sonnet 4.6](https://www.anthropic.com/claude) as an AI coding assistant. Claude contributed to all phases of development including architecture discussion, file-by-file implementation, code review, and bug fixing.

All design decisions were made collaboratively, with Claude explaining trade-offs and Mohammad making the final calls on behaviour, strictness, and scope.
