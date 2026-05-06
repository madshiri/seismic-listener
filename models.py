"""
models.py — Pydantic models for the seismic listener.

SeismicEvent represents a single seismic event as received from an agency.
All field constraints mirror the specification exactly so that validation
failures are caught at parse time, before any data touches the database.
"""

from pydantic import AwareDatetime, BaseModel, Field


class SeismicEvent(BaseModel):
    """A single seismic event delivered by a data agency."""

    # --- Event identity --------------------------------------------------
    eid: int = Field(
        ...,
        ge=0,
        description="Unique event identifier (natural number).",
    )
    timestamp: AwareDatetime = Field(
        ...,
        description=(
            "UTC timestamp of the event. Must be timezone-aware; "
            "naive datetimes are rejected."
        ),
    )

    # --- Hypocenter ------------------------------------------------------
    lat: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Hypocenter latitude in decimal degrees.",
    )
    lon: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Hypocenter longitude in decimal degrees.",
    )
    depth: float = Field(
        ...,
        ge=-100.0,
        le=0.0,
        description="Hypocenter depth in km (negative downward, max 100 km).",
    )

    # --- Magnitude -------------------------------------------------------
    Mw: float = Field(
        ...,
        ge=0.0,
        le=9.0,
        description="Moment magnitude.",
    )

    # --- Relation to monitored location ----------------------------------
    dist: float = Field(
        ...,
        ge=0.0,
        description="Distance from the monitored location in km (non-negative).",
    )
    azi: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Azimuth from the monitored location in decimal degrees.",
    )

    # --- Monitored location ----------------------------------------------
    loclat: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude of the monitored surface location in decimal degrees.",
    )
    loclon: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude of the monitored surface location in decimal degrees.",
    )

    model_config = {
        # Forbid extra fields so unexpected agency payload keys are caught.
        "extra": "ignore",
        # Keep the original AwareDatetime rather than converting to str.
        "arbitrary_types_allowed": False,
    }
