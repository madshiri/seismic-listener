"""
test_fetcher.py — Tests for the fetch_events function.

Covers:
  - Valid JSON array is returned as a list of dicts.
  - since is correctly serialised as an ISO 8601 query parameter.
  - Timeout returns None.
  - Connection error returns None.
  - HTTP error (503) returns None.
  - Non-JSON response returns None.
  - JSON object instead of array returns None.
  - Empty array is valid and returned as-is.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from fetcher import fetch_events

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_URL     = "http://localhost:8000/events"
_TIMEOUT = 10.0
_SINCE   = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_SAMPLE_RECORDS = [
    {"eid": 1, "timestamp": "2024-01-01T13:00:00+00:00"},
    {"eid": 2, "timestamp": "2024-01-01T14:00:00+00:00"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(json_data=None, status_code=200, raise_for_status=None, json_raises=False):
    """Build a mock requests.Response."""
    response = MagicMock()
    response.status_code = status_code

    if raise_for_status is not None:
        response.raise_for_status.side_effect = raise_for_status
    else:
        response.raise_for_status.return_value = None

    if json_raises:
        response.json.side_effect = ValueError("No JSON")
    else:
        response.json.return_value = json_data

    return response


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

class TestFetchEventsSuccess:
    def test_valid_array_returned_as_list(self):
        with patch("fetcher.requests.get", return_value=_mock_response(_SAMPLE_RECORDS)):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result == _SAMPLE_RECORDS

    def test_empty_array_returned_as_empty_list(self):
        with patch("fetcher.requests.get", return_value=_mock_response([])):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result == []

    def test_since_serialised_as_iso8601_query_param(self):
        with patch("fetcher.requests.get", return_value=_mock_response([])) as mock_get:
            fetch_events(_URL, _SINCE, _TIMEOUT)
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["since"] == _SINCE.isoformat()

    def test_timeout_forwarded_to_requests(self):
        with patch("fetcher.requests.get", return_value=_mock_response([])) as mock_get:
            fetch_events(_URL, _SINCE, _TIMEOUT)
        _, kwargs = mock_get.call_args
        assert kwargs["timeout"] == _TIMEOUT


# ---------------------------------------------------------------------------
# Failure cases — network / HTTP
# ---------------------------------------------------------------------------

class TestFetchEventsNetworkFailures:
    def test_timeout_returns_none(self):
        with patch("fetcher.requests.get", side_effect=requests.exceptions.Timeout):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result is None

    def test_connection_error_returns_none(self):
        with patch("fetcher.requests.get", side_effect=requests.exceptions.ConnectionError):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result is None

    def test_http_503_returns_none(self):
        http_error = requests.exceptions.HTTPError(response=MagicMock(status_code=503))
        response = _mock_response(status_code=503, raise_for_status=http_error)
        with patch("fetcher.requests.get", return_value=response):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result is None

    def test_generic_request_exception_returns_none(self):
        with patch("fetcher.requests.get", side_effect=requests.exceptions.RequestException):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result is None


# ---------------------------------------------------------------------------
# Failure cases — payload shape
# ---------------------------------------------------------------------------

class TestFetchEventsPayloadFailures:
    def test_non_json_response_returns_none(self):
        response = _mock_response(json_raises=True)
        with patch("fetcher.requests.get", return_value=response):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result is None

    def test_json_object_instead_of_array_returns_none(self):
        response = _mock_response(json_data={"events": _SAMPLE_RECORDS})
        with patch("fetcher.requests.get", return_value=response):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result is None

    def test_json_null_instead_of_array_returns_none(self):
        response = _mock_response(json_data=None)
        with patch("fetcher.requests.get", return_value=response):
            result = fetch_events(_URL, _SINCE, _TIMEOUT)
        assert result is None
