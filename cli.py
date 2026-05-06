"""
cli.py — Entry point for the seismic listener.

Responsibilities:
  - Parse CLI arguments and build AppConfig.
  - Configure application-wide logging.
  - Open the SQLite connection and initialise the schema.
  - Instantiate AgencyRouter.
  - Run the polling loop until SIGINT or SIGTERM is received.
  - Resolve a None latest timestamp to epoch zero before passing to the router.
  - Log a per-poll summary of inserted, duplicate, and invalid records.
  - Finish the current poll cycle cleanly before exiting on signal.

Usage:
  python cli.py [options]
"""

import argparse
import logging
import signal
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from config import AgencyConfig, AppConfig, DEFAULT_CONFIG
from db import get_latest_timestamp, init_db
from failover import AgencyRouter
from processor import process_records

logger = logging.getLogger(__name__)

_EPOCH_ZERO = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

class _ShutdownFlag:
    """Simple flag set by signal handlers to request a clean shutdown."""

    def __init__(self) -> None:
        self.requested = False

    def trigger(self, signum, frame) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — will shut down after current poll.", sig_name)
        self.requested = True


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seismic event listener with primary/fallback agency switching.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--primary-url",
        default=DEFAULT_CONFIG.primary.url,
        help="URL of the primary seismic data agency.",
    )
    parser.add_argument(
        "--primary-timeout",
        type=float,
        default=DEFAULT_CONFIG.primary.timeout,
        metavar="SECONDS",
        help="Request timeout for the primary agency.",
    )
    parser.add_argument(
        "--fallback-url",
        default=DEFAULT_CONFIG.fallback.url,
        help="URL of the fallback seismic data agency.",
    )
    parser.add_argument(
        "--fallback-timeout",
        type=float,
        default=DEFAULT_CONFIG.fallback.timeout,
        metavar="SECONDS",
        help="Request timeout for the fallback agency.",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_CONFIG.poll_interval_minutes,
        metavar="MINUTES",
        help="How often to poll for new events.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_CONFIG.db_path,
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--anomaly-log",
        type=Path,
        default=DEFAULT_CONFIG.anomaly_log_path,
        help="Path to the anomaly audit log file.",
    )
    parser.add_argument(
        "--primary-retry-after",
        type=int,
        default=DEFAULT_CONFIG.primary_retry_after_polls,
        metavar="POLLS",
        help="Number of fallback polls before retrying the primary agency.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Application log verbosity.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------

def _run(config: AppConfig) -> None:
    shutdown = _ShutdownFlag()
    signal.signal(signal.SIGINT, shutdown.trigger)
    signal.signal(signal.SIGTERM, shutdown.trigger)

    conn: sqlite3.Connection = sqlite3.connect(config.db_path)
    logger.info("Opened database at '%s'.", config.db_path)

    try:
        init_db(conn)
        logger.info("Database schema ready.")

        router = AgencyRouter(config)
        poll_count = 0

        logger.info(
            "Listener started. Polling every %d minute(s). "
            "Primary: %s | Fallback: %s.",
            config.poll_interval_minutes,
            config.primary.name,
            config.fallback.name,
        )

        while True:
            poll_count += 1
            # Capture before fetch — agency may switch during the request.
            active_agency = router.active_agency_name
            logger.info("--- Poll #%d | Active agency: %s ---", poll_count, active_agency)

            # Resolve None to epoch zero so the router never receives None.
            latest = get_latest_timestamp(conn)
            since = latest if latest is not None else _EPOCH_ZERO
            logger.debug("Fetching events since %s.", since.isoformat())

            records = router.fetch(since)

            if records is None:
                logger.error(
                    "Poll #%d: both agencies unavailable. No data fetched.", poll_count
                )
            else:
                summary = process_records(
                    records,
                    agency_name=active_agency,
                    conn=conn,
                    anomaly_log_path=config.anomaly_log_path,
                )
                logger.info(
                    "Poll #%d summary — inserted: %d | duplicates: %d | invalid: %d.",
                    poll_count,
                    summary["inserted"],
                    summary["duplicates"],
                    summary["invalid"],
                )

            if shutdown.requested:
                logger.info("Shutdown requested. Exiting after poll #%d.", poll_count)
                break

            # Sleep in 1-second increments so signals are honoured promptly
            # rather than waiting out the full poll interval.
            sleep_seconds = config.poll_interval_minutes * 60
            for _ in range(sleep_seconds):
                if shutdown.requested:
                    break
                time.sleep(1)

    finally:
        conn.close()
        logger.info("Database connection closed. Listener stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    _setup_logging(args.log_level)

    config = AppConfig(
        primary=AgencyConfig(
            name="AgencyA",
            url=args.primary_url,
            timeout=args.primary_timeout,
        ),
        fallback=AgencyConfig(
            name="AgencyB",
            url=args.fallback_url,
            timeout=args.fallback_timeout,
        ),
        poll_interval_minutes=args.poll_interval,
        db_path=args.db_path,
        anomaly_log_path=args.anomaly_log,
        primary_retry_after_polls=args.primary_retry_after,
    )

    _run(config)


if __name__ == "__main__":
    main()
