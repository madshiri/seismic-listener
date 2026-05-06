"""
simulator.py — Simulated seismic data agencies for local testing.

Exposes two FastAPI app objects:
  - app_a : primary agency (full 150 events)
  - app_b : fallback agency (first 143 events)

Launch manually:
  uvicorn simulator:app_a --port 8000
  uvicorn simulator:app_b --port 8001

Bad records are injected at fixed indices (shared by both agencies):
  - Every 30th event (index 29, 59, 89, ...): Mw=15.0  (out of range)
  - Every 50th event (index 49, 99, 149):     depth=+30.0 (out of range)

Events are filtered by the `since` query parameter (ISO 8601, UTC).
"""

import random
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Event generation
# ---------------------------------------------------------------------------

_TOTAL_EVENTS = 150
_SEED = 42


def _generate_events(total: int, seed: int) -> list[dict]:
    """Generate a fixed list of seismic event dicts with a seeded RNG.

    Time gaps between events are intentionally unequal to simulate
    realistic irregular inter-event intervals.

    Bad records are injected at:
      - Every 30th event (1-based): Mw set to 15.0
      - Every 50th event (1-based): depth set to +30.0
    """
    rng = random.Random(seed)

    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    events = []
    current_time = base_time

    for i in range(1, total + 1):
        # Irregular gap: between 1 and 60 minutes.
        gap_minutes = rng.randint(1, 60)
        current_time += timedelta(minutes=gap_minutes)

        lat   = rng.uniform(-60.0, 60.0)
        lon   = rng.uniform(-180.0, 180.0)
        depth = rng.uniform(-100.0, 0.0)
        Mw    = rng.uniform(0.0, 8.0)
        dist  = rng.uniform(0.0, 5000.0)
        azi   = rng.uniform(-180.0, 180.0)
        loclat = rng.uniform(-90.0, 90.0)
        loclon = rng.uniform(-180.0, 180.0)

        # Inject bad records.
        if i % 30 == 0:
            Mw = 15.0       # invalid: exceeds [0.0, 9.0]
        if i % 50 == 0:
            depth = +30.0   # invalid: outside [-100.0, 0.0]

        events.append({
            "eid":       i,
            "timestamp": current_time.isoformat(),
            "lat":       round(lat, 6),
            "lon":       round(lon, 6),
            "depth":     round(depth, 6),
            "Mw":        round(Mw, 2),
            "dist":      round(dist, 3),
            "azi":       round(azi, 6),
            "loclat":    round(loclat, 6),
            "loclon":    round(loclon, 6),
        })

    return events


# Generate once at import time — shared across both apps.
_ALL_EVENTS: list[dict] = _generate_events(_TOTAL_EVENTS, _SEED)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_agency(name: str, coverage_fraction: float) -> FastAPI:
    """Create a FastAPI app simulating one seismic data agency.

    Args:
        name:              Agency name, used in the app title and responses.
        coverage_fraction: Fraction of the 150 events this agency serves.
                           e.g. 1.0 → all 150, 143/150 → first 143.

    Returns:
        A FastAPI application with a single GET /events endpoint.
    """
    n_events = round(_TOTAL_EVENTS * coverage_fraction)
    agency_events = _ALL_EVENTS[:n_events]

    app = FastAPI(title=f"Seismic Agency {name}")

    _EPOCH_ZERO = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()

    @app.get("/events")
    def get_events(
        since: str = Query(
            default=_EPOCH_ZERO,
            description=(
                "ISO 8601 UTC timestamp. Only events after this time are returned. "
                "Defaults to epoch zero so all events are returned on first run."
            ),
        ),
    ) -> JSONResponse:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid 'since' format: {since!r}. Expected ISO 8601."},
            )

        filtered = [
            e for e in agency_events
            if datetime.fromisoformat(e["timestamp"]) > since_dt
        ]
        return JSONResponse(content=filtered)

    return app


# ---------------------------------------------------------------------------
# App instances
# ---------------------------------------------------------------------------

app_a: FastAPI = make_agency(name="A", coverage_fraction=1.0)
app_b: FastAPI = make_agency(name="B", coverage_fraction=143 / 150)
