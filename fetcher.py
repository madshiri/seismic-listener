"""
fetcher.py — Single-agency HTTP fetch for the seismic listener.

Exposes one function:
  - fetch_events(url, since, timeout) : GET events from one agency URL,
                                        return a list of raw dicts or None on failure.

No retry logic, no agency switching — those concerns belong to failover.py.
The since parameter is always a timezone-aware datetime; the caller is
responsible for resolving the None case before calling this function.
"""

import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


def fetch_events(
    url: str,
    since: datetime,
    timeout: float,
) -> list[dict] | None:
    """Fetch seismic events from a single agency endpoint.

    Sends a GET request to `url` with `since` as a query parameter.
    Returns the parsed JSON payload as a list of dicts on success,
    or None if the request fails for any reason (network error, non-200
    status, or malformed JSON).

    Args:
        url:     Full base URL of the agency endpoint.
        since:   Timezone-aware datetime used as the lower bound for events.
                 Serialised to ISO 8601 and passed as the `since` query param.
        timeout: Seconds to wait for a response before aborting.

    Returns:
        List of raw event dicts, or None on any failure.
    """
    params = {"since": since.isoformat()}

    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.warning("Timeout fetching from %s (timeout=%.1fs).", url, timeout)
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Connection error fetching from %s.", url)
        return None
    except requests.exceptions.HTTPError as exc:
        logger.warning("HTTP %s from %s.", exc.response.status_code, url)
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning("Unexpected request error from %s: %s.", url, exc)
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.warning("Non-JSON response from %s.", url)
        return None

    if not isinstance(payload, list):
        logger.warning("Expected a JSON array from %s, got %s.", url, type(payload).__name__)
        return None

    return payload
