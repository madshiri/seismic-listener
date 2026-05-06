"""
failover.py — Primary/fallback agency switching state machine.

Exposes one class:
  - AgencyRouter : tracks active agency, failure counts, and skip counters.
                   Exposes a single fetch(since) method that handles all
                   switching logic internally.

Switching rules:
  - Primary (A) is always preferred.
  - On a failed poll, consecutive failure count increments and we switch to B.
  - On a successful poll, consecutive failure count resets to zero.
  - While on B, a skip counter increments each poll.
  - When the skip counter reaches primary_retry_after_polls, A is attempted.
    If A succeeds we switch back; if it fails we stay on B and reset the counter.
"""

import logging
from datetime import datetime

from config import AppConfig
from fetcher import fetch_events

logger = logging.getLogger(__name__)


class AgencyRouter:
    """Manages primary/fallback agency selection and switching logic.

    Args:
        config: Application configuration holding both agency configs
                and the primary_retry_after_polls threshold.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._on_primary: bool = True
        self._primary_failures: int = 0   # consecutive failed polls on primary
        self._polls_on_fallback: int = 0  # polls elapsed since switching to fallback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_agency_name(self) -> str:
        """Name of the agency currently being polled."""
        return (
            self._config.primary.name
            if self._on_primary
            else self._config.fallback.name
        )

    def fetch(self, since: datetime) -> list[dict] | None:
        """Fetch events from the active agency, handling all switching logic.

        If on primary and the fetch fails, switches to fallback immediately.
        If on fallback and the skip counter is reached, probes primary first;
        switches back only on success, otherwise stays on fallback and resets
        the skip counter.

        Args:
            since: Timezone-aware lower-bound timestamp passed to the fetcher.

        Returns:
            List of raw event dicts, or None if both active agency and any
            probe attempt fail.
        """
        if self._on_primary:
            return self._fetch_primary(since)

        # Increment only when we enter this poll already on fallback.
        # Polls where we just switched from primary do not count.
        self._polls_on_fallback += 1
        return self._fetch_fallback(since)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_primary(self, since: datetime) -> list[dict] | None:
        cfg = self._config.primary
        logger.debug("Polling primary agency '%s'.", cfg.name)

        result = fetch_events(cfg.url, since, cfg.timeout)

        if result is not None:
            self._on_success_primary()
            return result

        self._on_failure_primary()
        return self._fetch_fallback(since)

    def _fetch_fallback(self, since: datetime) -> list[dict] | None:
        # Probe primary if the skip threshold has been reached.
        if self._polls_on_fallback >= self._config.primary_retry_after_polls:
            probe = self._probe_primary(since)
            if probe is not None:
                return probe
            # Primary probe failed — stay on fallback, reset skip counter.
            self._polls_on_fallback = 0

        cfg = self._config.fallback
        logger.debug("Polling fallback agency '%s'.", cfg.name)

        result = fetch_events(cfg.url, since, cfg.timeout)

        if result is not None:
            logger.debug("Fallback agency '%s' succeeded.", cfg.name)
            return result

        logger.error(
            "Both primary and fallback agencies are unavailable. Returning None."
        )
        return None

    def _probe_primary(self, since: datetime) -> list[dict] | None:
        """Attempt primary as a probe while on fallback.

        Switches back to primary on success, stays on fallback on failure.
        """
        cfg = self._config.primary
        logger.info(
            "Probing primary agency '%s' after %d polls on fallback.",
            cfg.name,
            self._polls_on_fallback,
        )

        result = fetch_events(cfg.url, since, cfg.timeout)

        if result is not None:
            logger.info(
                "Primary agency '%s' is back. Switching from fallback.", cfg.name
            )
            self._on_primary = True
            self._primary_failures = 0
            self._polls_on_fallback = 0
            return result

        logger.warning(
            "Primary agency '%s' probe failed. Staying on fallback.", cfg.name
        )
        return None

    def _on_success_primary(self) -> None:
        if self._primary_failures > 0:
            logger.info(
                "Primary agency '%s' recovered after %d failure(s).",
                self._config.primary.name,
                self._primary_failures,
            )
        self._primary_failures = 0

    def _on_failure_primary(self) -> None:
        self._primary_failures += 1
        logger.warning(
            "Primary agency '%s' failed (consecutive failures: %d). "
            "Switching to fallback '%s'.",
            self._config.primary.name,
            self._primary_failures,
            self._config.fallback.name,
        )
        self._on_primary = False
        self._polls_on_fallback = 0
