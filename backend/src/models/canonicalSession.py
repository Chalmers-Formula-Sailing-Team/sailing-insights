from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.models.raceModels import Race

# =========================
# Base domain objects
# =========================


@dataclass(slots=True)
class Channel:
    """
    Time series data.

    A channel keeps its own native timeline. This is important because
    different sensors may have different sample rates.
    """

    name: str
    timestamps: np.ndarray
    values: np.ndarray
    unit: str | None = None
    source: str | None = None
    is_derived: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.timestamps) != len(self.values):
            raise ValueError(
                f"Channel '{self.name}' has mismatched timestamps and values length: "
                f"{len(self.timestamps)} != {len(self.values)}"
            )

        if not isinstance(self.timestamps, np.ndarray):
            raise TypeError(f"Channel '{self.name}' timestamps must be a numpy array")

        if not isinstance(self.values, np.ndarray):
            raise TypeError(f"Channel '{self.name}' values must be a numpy array")

        if self.timestamps.ndim != 1:
            raise ValueError(f"Channel '{self.name}' timestamps must be 1D")

        # values may be 1D or 2D depending on signal type
        if self.values.shape[0] != self.timestamps.shape[0]:
            raise ValueError(
                f"Channel '{self.name}' values first dimension must match timestamps length"
            )


@dataclass(slots=True)
class Event:
    """
    Interval or point-in-time occurrence.

    Examples:
      - tack
      - gybe
      - start_crossing
      - sensor_dropout
      - mark_rounding
    """

    event_type: str
    start_time: float
    source: str
    end_time: float | None = None
    confidence: float | None = None
    foiling: bool = False
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.end_time is not None and self.end_time < self.start_time:
            raise ValueError(
                f"Event '{self.event_type}' end_time cannot be before start_time"
            )
        if self.source is None:
            raise ValueError(f"Event '{self.event_type}' must have a source")


@dataclass(slots=True)
class Metric:
    """
    Scalar analysis result.

    Examples:
      - avg_upwind_speed
      - max_heel
      - number_of_tacks
      - best_vmg
    """

    name: str
    value: Any
    unit: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source is None:
            raise ValueError(f"Metric '{self.name}' must have a source")
        if self.unit is None:
            raise ValueError(f"Metric '{self.name}' must have a unit")


@dataclass(slots=True)
class Artifact:
    """
    Structured non-scalar, non-timeseries analysis output.

    Use this for things that do not fit neatly into Channel/Event/Metric:
      - polar tables
      - detected segments
      - model fit objects
      - summary tables
      - diagnostic payloads
    """

    name: str
    data: Any
    artifact_type: str
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionMetadata:
    """
    Static metadata about the session itself.
    """

    session_id: str
    session_name: str = ""
    source_type: str | None = None  # e.g. "garmin", "strava", "nmea"
    athlete_id: str | None = None
    boat_id: str | None = None
    start_at: np.datetime64 | None = None
    end_at: np.datetime64 | None = None
    timezone: str | None = None
    location: str | None = None
    notes: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            self.start_at is not None
            and self.end_at is not None
            and self.end_at < self.start_at
        ):
            raise ValueError("SessionMetadata ended_at cannot be before started_at")


@dataclass(slots=True)
class ProvenanceRecord:
    """
    Records which analyzer or pipeline step created or modified something.

    For channel modifications, use ``changes`` to describe what happened to the
    channel data, for example removing invalid samples from ``values``.
    """

    producer: str
    produced_type: str  # "channel", "event", "metric", "artifact"
    produced_name: str
    action: str = "created"  # e.g. "created", "modified"
    inputs: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    # Example: {"field": "values", "operation": "remove_values", "count": 3}
    changes: list[dict[str, Any]] = field(default_factory=list)


# =========================
# Canonical Session
# =========================


@dataclass(slots=True)
class CanonicalSession:
    """
    Implements the in-system contract for a session.

    This is the central object passed through the pipeline:
      extraction -> normalization -> analysis -> persistence

    It contains:
      - metadata about the session
      - raw and derived channels
      - events detected during analysis
      - scalar metrics
      - arbitrary artifacts for richer outputs
      - provenance records for traceability
    """

    metadata: SessionMetadata

    channels: dict[str, Channel] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    metrics: dict[str, Metric] = field(default_factory=dict)
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    races: list[Race] = field(default_factory=list)

    REQUIRED_CHANNELS: tuple[str, str] = ("lat", "lon")

    def __post_init__(self) -> None:
        missing = [
            channel_name
            for channel_name in self.REQUIRED_CHANNELS
            if channel_name not in self.channels
        ]
        if missing:
            raise ValueError(
                f"CanonicalSession requires channels: {list(self.REQUIRED_CHANNELS)}; "
                f"missing {missing}"
            )

        if not len(self.channels["lat"].values) == len(self.channels["lon"].values):
            raise ValueError("lat and lon channels must have same amount of values")

    # -------------------------
    # Channel methods
    # -------------------------

    def add_channel(self, channel: Channel, overwrite: bool = False) -> None:
        if channel.name in self.channels and not overwrite:
            raise ValueError(f"Channel '{channel.name}' already exists")
        self.channels[channel.name] = channel

    def get_channel(self, name: str) -> Channel:
        try:
            return self.channels[name]
        except KeyError as exc:
            raise KeyError(f"Channel '{name}' not found") from exc

    def has_channel(self, name: str) -> bool:
        return name in self.channels

    def require_channels(self, names: list[str]) -> None:
        missing = [name for name in names if name not in self.channels]
        if missing:
            raise KeyError(f"Missing required channels: {missing}")

    # -------------------------
    # Event methods
    # -------------------------

    def add_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(
        self,
        event_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> list[Event]:
        result = self.events

        if event_type is not None:
            result = [e for e in result if e.event_type == event_type]

        if start_time is not None:
            result = [e for e in result if e.start_time >= start_time]

        if end_time is not None:
            result = [
                e
                for e in result
                if (e.end_time if e.end_time is not None else e.start_time) <= end_time
            ]

        return result

    # -------------------------
    # Metric methods
    # -------------------------

    def add_metric(self, metric: Metric, overwrite: bool = False) -> None:
        if metric.name in self.metrics and not overwrite:
            raise ValueError(f"Metric '{metric.name}' already exists")
        self.metrics[metric.name] = metric

    def get_metric(self, name: str) -> Metric:
        try:
            return self.metrics[name]
        except KeyError as exc:
            raise KeyError(f"Metric '{name}' not found") from exc

    def has_metric(self, name: str) -> bool:
        return name in self.metrics

    # -------------------------
    # Artifact methods
    # -------------------------

    def add_artifact(self, artifact: Artifact, overwrite: bool = False) -> None:
        if artifact.name in self.artifacts and not overwrite:
            raise ValueError(f"Artifact '{artifact.name}' already exists")
        self.artifacts[artifact.name] = artifact

    def get_artifact(self, name: str) -> Artifact:
        try:
            return self.artifacts[name]
        except KeyError as exc:
            raise KeyError(f"Artifact '{name}' not found") from exc

    # -------------------------
    # Provenance methods
    # -------------------------

    def add_provenance(self, record: ProvenanceRecord) -> None:
        self.provenance.append(record)

    # -------------------------
    # Convenience / summary
    # -------------------------

    @property
    def start_time(self) -> float | None:
        if self.metadata.start_at is not None:
            return self.metadata.start_at

        if not self.channels:
            return None

        starts = [
            float(channel.timestamps[0])
            for channel in self.channels.values()
            if len(channel.timestamps) > 0
        ]
        return min(starts) if starts else None

    @property
    def end_time(self) -> float | None:
        if self.metadata.end_at is not None:
            return self.metadata.end_at

        if not self.channels:
            return None

        ends = [
            float(channel.timestamps[-1])
            for channel in self.channels.values()
            if len(channel.timestamps) > 0
        ]
        return max(ends) if ends else None

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.metadata.session_id,
            "source_type": self.metadata.source_type,
            "channel_count": len(self.channels),
            "event_count": len(self.events),
            "metric_count": len(self.metrics),
            "artifact_count": len(self.artifacts),
            "start_time": self.start_time,
            "end_time": self.end_time,
        }
