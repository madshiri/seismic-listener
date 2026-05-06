"""
test_models.py — Tests for SeismicEvent Pydantic model validation.

Covers:
  - Valid event passes validation.
  - Each numeric field rejects values outside its bounds (both edges).
  - Naive datetime is rejected by AwareDatetime.
  - Missing required fields raise ValidationError.
  - eid rejects negative values.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from models import SeismicEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_payload(**overrides) -> dict:
    """Return a fully valid SeismicEvent payload with optional field overrides."""
    base = {
        "eid":       1,
        "timestamp": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "lat":       0.0,
        "lon":       0.0,
        "depth":     -10.0,
        "Mw":        5.0,
        "dist":      100.0,
        "azi":       0.0,
        "loclat":    0.0,
        "loclon":    0.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Valid event
# ---------------------------------------------------------------------------

class TestValidEvent:
    def test_valid_payload_passes(self):
        event = SeismicEvent(**_valid_payload())
        assert event.eid == 1
        assert event.Mw == 5.0
        assert event.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# eid
# ---------------------------------------------------------------------------

class TestEid:
    def test_eid_zero_is_valid(self):
        SeismicEvent(**_valid_payload(eid=0))

    def test_eid_negative_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(eid=-1))


# ---------------------------------------------------------------------------
# timestamp
# ---------------------------------------------------------------------------

class TestTimestamp:
    def test_aware_timestamp_passes(self):
        event = SeismicEvent(**_valid_payload(
            timestamp=datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        ))
        assert event.timestamp.tzinfo is not None

    def test_naive_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(
                timestamp=datetime(2024, 6, 1, 0, 0, 0)  # no tzinfo
            ))


# ---------------------------------------------------------------------------
# lat
# ---------------------------------------------------------------------------

class TestLat:
    def test_lat_lower_bound_valid(self):
        SeismicEvent(**_valid_payload(lat=-90.0))

    def test_lat_upper_bound_valid(self):
        SeismicEvent(**_valid_payload(lat=90.0))

    def test_lat_below_lower_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(lat=-90.1))

    def test_lat_above_upper_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(lat=90.1))


# ---------------------------------------------------------------------------
# lon
# ---------------------------------------------------------------------------

class TestLon:
    def test_lon_lower_bound_valid(self):
        SeismicEvent(**_valid_payload(lon=-180.0))

    def test_lon_upper_bound_valid(self):
        SeismicEvent(**_valid_payload(lon=180.0))

    def test_lon_below_lower_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(lon=-180.1))

    def test_lon_above_upper_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(lon=180.1))


# ---------------------------------------------------------------------------
# depth
# ---------------------------------------------------------------------------

class TestDepth:
    def test_depth_lower_bound_valid(self):
        SeismicEvent(**_valid_payload(depth=-100.0))

    def test_depth_upper_bound_valid(self):
        SeismicEvent(**_valid_payload(depth=0.0))

    def test_depth_below_lower_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(depth=-100.1))

    def test_depth_above_upper_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(depth=0.1))


# ---------------------------------------------------------------------------
# Mw
# ---------------------------------------------------------------------------

class TestMw:
    def test_Mw_lower_bound_valid(self):
        SeismicEvent(**_valid_payload(Mw=0.0))

    def test_Mw_upper_bound_valid(self):
        SeismicEvent(**_valid_payload(Mw=9.0))

    def test_Mw_below_lower_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(Mw=-0.1))

    def test_Mw_above_upper_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(Mw=9.1))


# ---------------------------------------------------------------------------
# dist
# ---------------------------------------------------------------------------

class TestDist:
    def test_dist_zero_is_valid(self):
        SeismicEvent(**_valid_payload(dist=0.0))

    def test_dist_negative_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(dist=-0.1))


# ---------------------------------------------------------------------------
# azi
# ---------------------------------------------------------------------------

class TestAzi:
    def test_azi_lower_bound_valid(self):
        SeismicEvent(**_valid_payload(azi=-180.0))

    def test_azi_upper_bound_valid(self):
        SeismicEvent(**_valid_payload(azi=180.0))

    def test_azi_below_lower_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(azi=-180.1))

    def test_azi_above_upper_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(azi=180.1))


# ---------------------------------------------------------------------------
# loclat
# ---------------------------------------------------------------------------

class TestLoclat:
    def test_loclat_lower_bound_valid(self):
        SeismicEvent(**_valid_payload(loclat=-90.0))

    def test_loclat_upper_bound_valid(self):
        SeismicEvent(**_valid_payload(loclat=90.0))

    def test_loclat_below_lower_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(loclat=-90.1))

    def test_loclat_above_upper_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(loclat=90.1))


# ---------------------------------------------------------------------------
# loclon
# ---------------------------------------------------------------------------

class TestLoclon:
    def test_loclon_lower_bound_valid(self):
        SeismicEvent(**_valid_payload(loclon=-180.0))

    def test_loclon_upper_bound_valid(self):
        SeismicEvent(**_valid_payload(loclon=180.0))

    def test_loclon_below_lower_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(loclon=-180.1))

    def test_loclon_above_upper_bound_rejected(self):
        with pytest.raises(ValidationError):
            SeismicEvent(**_valid_payload(loclon=180.1))


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

class TestMissingFields:
    @pytest.mark.parametrize("field", [
        "eid", "timestamp", "lat", "lon", "depth",
        "Mw", "dist", "azi", "loclat", "loclon",
    ])
    def test_missing_field_rejected(self, field):
        payload = _valid_payload()
        del payload[field]
        with pytest.raises(ValidationError):
            SeismicEvent(**payload)
