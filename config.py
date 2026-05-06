"""
config.py — Static configuration for the seismic listener.

Two dataclasses:
  - AgencyConfig : connection settings for a single data agency.
  - AppConfig    : top-level application configuration.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AgencyConfig:
    """Connection settings for one seismic data agency."""

    name: str
    url: str
    timeout: float  # seconds to wait for a response before treating the agency as down


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    primary: AgencyConfig
    fallback: AgencyConfig

    poll_interval_minutes: int          # how often to fetch data
    db_path: Path                       # SQLite database file
    anomaly_log_path: Path              # flat file for anomaly audit trail
    primary_retry_after_polls: int      # how many polls on fallback before re-trying primary

    def __post_init__(self) -> None:
        if self.poll_interval_minutes <= 0:
            raise ValueError("poll_interval_minutes must be a positive integer.")
        if self.primary_retry_after_polls <= 0:
            raise ValueError("primary_retry_after_polls must be a positive integer.")
        if self.primary.name == self.fallback.name:
            raise ValueError("Primary and fallback agencies must have distinct names.")


# ---------------------------------------------------------------------------
# Default configuration — override by constructing your own AppConfig.
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = AppConfig(
    primary=AgencyConfig(
        name="AgencyA",
        url="http://localhost:8000/events",
        timeout=10.0,
    ),
    fallback=AgencyConfig(
        name="AgencyB",
        url="http://localhost:8001/events",
        timeout=10.0,
    ),
    poll_interval_minutes=5,
    db_path=Path("seismic.db"),
    anomaly_log_path=Path("anomalies.log"),
    primary_retry_after_polls=3,
)
