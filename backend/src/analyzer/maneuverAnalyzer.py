from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from src.analyzer.analyzer import Analyzer
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Event,
    Metric,
    ProvenanceRecord,
)


@dataclass(slots=True)
class _ManeuverDetection:
    """Container for one detected maneuver and its derived attributes.

    Attributes:
        index: Zero-based sample index of the maneuver on the selected TWA timeline.
        event_type: Maneuver label, typically ``"tack"`` or ``"gybe"``.
        is_foiling: Whether the maneuver is considered foiling before and after the turn.
        mean_abs_twa_deg: Mean absolute TWA used for tack vs gybe classification.
        avg_speed_before_kn: Mean speed in knots in the pre-maneuver foiling window.
        avg_speed_after_kn: Mean speed in knots in the post-maneuver foiling window.

    Example:
        ``_ManeuverDetection(index=42, event_type="tack", is_foiling=True, ...)``
        represents a foiling tack detected at sample 42.
    """

    index: int
    event_type: str
    is_foiling: bool
    mean_abs_twa_deg: float
    avg_speed_before_kn: float
    avg_speed_after_kn: float


class ManeuverAnalyzer(Analyzer):
    """Detect tacks and gybes from TWA sign changes and boat speed.

    The analyzer prefers a manual-wind-derived TWA channel when more than one TWA
    channel is present. It persists detected maneuvers as canonical session
    ``Event`` objects and also adds summary metrics for maneuver counts and
    foiling percentages.

    Example:
        ``ManeuverAnalyzer(min_maneuver_speed_knots=4.0, foiling_speed_knots=8.0)``
        creates an analyzer with stricter speed thresholds for detection and
        foiling classification.
    """

    REQUIRED_CHANNELS = (ChannelNames.SOG.value,)
    TACK_EVENT_TYPE = "tack"
    GYBE_EVENT_TYPE = "gybe"

    def __init__(
        self,
        min_tack_entry_speed_kn: float = 1.5,
        min_gybe_entry_speed_kn: float = 2.0,
        speed_measure_seconds: float = 4.0,
        min_maneuver_interval_seconds: float = 10.0,
        min_entry_speed_percentage: float = 2 / 3,
        classification_interval_seconds: float = 5.0,
        foiling_interval_seconds: float = 5.0,
        foiling_percentage: float = (3 / 4),
        close_reach_boundary_deg: float = 90.0,
        foiling_speed_knots: float = 6.8,
    ) -> None:
        """Initialize maneuver detection thresholds.

        Args:
            min_maneuver_speed_knots: Minimum speed required before a sign change
                for it to count as a maneuver candidate.
            speed_measure_seconds: How far before a candidate timestamp speed is
                sampled for the minimum-speed check.
            min_maneuver_interval_seconds: Minimum elapsed time between accepted
                maneuvers used to suppress duplicate detections.
            classification_interval_seconds: Time window before the maneuver used
                to classify tack versus gybe from average absolute TWA.
            foiling_interval_seconds: Time window before and after the maneuver
                used to decide whether it was foiling.
            close_reach_boundary_deg: Maximum average absolute TWA that still
                counts as a tack. Larger values are classified as gybes.
            foiling_percentage: Minimum share of samples in both gybe foiling
                windows that must meet ``foiling_speed_knots``.
            foiling_speed_knots: Minimum speed sample value for gybe foiling
                classification.

        Returns:
            None.

        Example:
            ``ManeuverAnalyzer(min_maneuver_interval_seconds=20.0)`` requires at
            least 20 seconds between accepted maneuvers.
        """

        if min_tack_entry_speed_kn < 0:
            raise ValueError("min_tack_entry_speed must be greater than or equal to 0")
        if min_gybe_entry_speed_kn < 0:
            raise ValueError("min_gybe_entry_speed must be greater than or equal to 0")
        if min_entry_speed_percentage < 0 or min_entry_speed_percentage > 1:
            raise ValueError("min_entry_speed_percentage must be in [0,1]")
        if speed_measure_seconds < 0:
            raise ValueError("speed_measure_seconds must be greater than or equal to 0")
        if min_maneuver_interval_seconds < 0:
            raise ValueError(
                "min_maneuver_interval_seconds must be greater than or equal to 0"
            )
        if classification_interval_seconds < 0:
            raise ValueError(
                "classification_interval_seconds must be greater than or equal to 0"
            )
        if foiling_interval_seconds < 0:
            raise ValueError(
                "foiling_interval_seconds must be greater than or equal to 0"
            )
        if foiling_percentage < 0 or foiling_percentage > 1:
            raise ValueError("foiling_percentage must be in [0,1]")
        if close_reach_boundary_deg < 0:
            raise ValueError(
                "close_reach_boundary_deg must be greater than or equal to 0"
            )
        if foiling_speed_knots < 0:
            raise ValueError("foiling_speed_knots must be greater than or equal to 0")

        self.min_tack_entry_speed_kn = float(min_tack_entry_speed_kn)
        self.min_gybe_entry_speed_kn = float(min_gybe_entry_speed_kn)
        self.min_entry_speed_percentage = float(min_entry_speed_percentage)
        self.speed_measure_seconds = float(speed_measure_seconds)
        self.min_maneuver_interval_seconds = float(min_maneuver_interval_seconds)
        self.classification_interval_seconds = float(classification_interval_seconds)
        self.foiling_interval_seconds = float(foiling_interval_seconds)
        self.close_reach_boundary_deg = float(close_reach_boundary_deg)
        self.foiling_speed_knots = float(foiling_speed_knots)
        self.foiling_percentage = float(foiling_percentage)
        self._selected_twa_channel_name: str | None = None
        self._detections: list[_ManeuverDetection] = []
        self._detection_timestamps: list[object] = []
        self._summary_counts = {
            self.TACK_EVENT_TYPE: 0,
            self.GYBE_EVENT_TYPE: 0,
            "foiling_tack": 0,
            "foiling_gybe": 0,
        }

    def analyze(self, session: CanonicalSession) -> CanonicalSession:
        """Run maneuver detection on a canonical session.

        Args:
            session: Canonical session containing at least ``sog`` and one usable
                TWA channel such as ``twa`` or ``twa_manual_wind_direction_deg``.

        Returns:
            The same ``CanonicalSession`` instance with maneuver events, metrics,
            and provenance added when a TWA channel is available. If no usable
            TWA exists, the session is returned unchanged.

        Example:
            ``result = ManeuverAnalyzer().analyze(session)`` adds ``tack`` and
            ``gybe`` events to ``result.events`` when maneuvers are found.
        """

        self._prepare_analysis_state()
        session.require_channels(self.required_channels)

        analyzed_session = self._analyze(session)
        if self._selected_twa_channel_name is None:
            return analyzed_session

        for record in self.build_provenance_records(analyzed_session):
            self._validate_provenance_record(analyzed_session, record)
            analyzed_session.add_provenance(record)

        return analyzed_session

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        """Perform the internal maneuver-analysis pass.

        Args:
            session: Canonical session whose channels are inspected for TWA and
                speed-based maneuver detection.

        Returns:
            The input session with events and metrics added if a TWA channel is
            selected; otherwise the input session unchanged.

        Example:
            If the selected TWA crosses from ``-40`` to ``40`` while speed stays
            above threshold, this method adds a ``tack`` event to the session.
        """

        twa_channel = self._select_twa_channel(session)
        if twa_channel is None:
            return session

        self._selected_twa_channel_name = twa_channel.name
        speed_channel = session.get_channel(ChannelNames.SOG.value)
        latitude_channel = session.get_channel(ChannelNames.LATITUDE.value)
        longitude_channel = session.get_channel(ChannelNames.LONGITUDE.value)

        maneuver_timestamps = np.asarray(twa_channel.timestamps)
        maneuver_timestamps_numeric = self._timestamps_to_numeric(maneuver_timestamps)
        twa_values = np.asarray(twa_channel.values, dtype=float)
        speed_values = self._align_channel_values_to_target_timestamps(
            speed_channel,
            maneuver_timestamps_numeric,
        )
        latitude_values = self._align_channel_values_to_target_timestamps(
            latitude_channel,
            maneuver_timestamps_numeric,
        )
        longitude_values = self._align_channel_values_to_target_timestamps(
            longitude_channel,
            maneuver_timestamps_numeric,
        )

        self._detections = self._detect_maneuvers(
            maneuver_timestamps_numeric,
            twa_values,
            speed_values,
        )
        self._detection_timestamps = [
            maneuver_timestamps[detection.index] for detection in self._detections
        ]

        for detection in self._detections:
            event_timestamp = maneuver_timestamps[detection.index]
            event_latitude = latitude_values[detection.index]
            event_longitude = longitude_values[detection.index]
            session.add_event(
                Event(
                    event_type=detection.event_type,
                    start_time=event_timestamp,
                    source=self.producer,
                    foiling=detection.is_foiling,
                    latitude=(
                        float(event_latitude) if np.isfinite(event_latitude) else None
                    ),
                    longitude=(
                        float(event_longitude) if np.isfinite(event_longitude) else None
                    ),
                    metadata={
                        "foiling_maneuver": detection.is_foiling,
                        "mean_abs_twa_deg": detection.mean_abs_twa_deg,
                        "avg_speed_before_kn": detection.avg_speed_before_kn,
                        "avg_speed_after_kn": detection.avg_speed_after_kn,
                    },
                )
            )

        tack_count = sum(
            1
            for detection in self._detections
            if detection.event_type == self.TACK_EVENT_TYPE
        )
        gybe_count = sum(
            1
            for detection in self._detections
            if detection.event_type == self.GYBE_EVENT_TYPE
        )
        foiling_tack_count = sum(
            1
            for detection in self._detections
            if detection.event_type == self.TACK_EVENT_TYPE and detection.is_foiling
        )
        foiling_gybe_count = sum(
            1
            for detection in self._detections
            if detection.event_type == self.GYBE_EVENT_TYPE and detection.is_foiling
        )

        self._summary_counts = {
            self.TACK_EVENT_TYPE: tack_count,
            self.GYBE_EVENT_TYPE: gybe_count,
            "foiling_tack": foiling_tack_count,
            "foiling_gybe": foiling_gybe_count,
        }

        self._add_metric(
            session,
            MetricNames.TACK_COUNT.value,
            float(tack_count),
            "count",
        )
        self._add_metric(
            session,
            MetricNames.GYBE_COUNT.value,
            float(gybe_count),
            "count",
        )
        self._add_metric(
            session,
            MetricNames.FOILING_TACK_COUNT.value,
            float(foiling_tack_count),
            "count",
        )
        self._add_metric(
            session,
            MetricNames.FOILING_GYBE_COUNT.value,
            float(foiling_gybe_count),
            "count",
        )
        self._add_metric(
            session,
            MetricNames.FOILING_TACK_PERCENTAGE.value,
            self._safe_percentage(foiling_tack_count, tack_count),
            "percent",
        )
        self._add_metric(
            session,
            MetricNames.FOILING_GYBE_PERCENTAGE.value,
            self._safe_percentage(foiling_gybe_count, gybe_count),
            "percent",
        )

        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        """Describe the maneuver outputs produced during analysis.

        Args:
            session: Canonical session after maneuver analysis has run.

        Returns:
            A list of provenance records for maneuver metrics and, when present,
            tack or gybe events. Returns an empty list when no TWA channel was
            selected and therefore no maneuver analysis was performed.

        Example:
            When one tack is detected, the returned provenance includes metric
            records like ``tack_count`` and an event record for ``"tack"``.
        """

        if self._selected_twa_channel_name is None:
            return []

        input_channels = [self._selected_twa_channel_name, ChannelNames.SOG.value]
        config = {
            "twa_channel": self._selected_twa_channel_name,
            "speed_channel": ChannelNames.SOG.value,
            "min_tack_entry_speed_kn": self.min_tack_entry_speed_kn,
            "min_gybe_entry_speed_kn": self.min_gybe_entry_speed_kn,
            "speed_measure_seconds": self.speed_measure_seconds,
            "min_maneuver_interval_seconds": self.min_maneuver_interval_seconds,
            "classification_interval_seconds": self.classification_interval_seconds,
            "foiling_interval_seconds": self.foiling_interval_seconds,
            "foiling_percentage": self.foiling_percentage,
            "close_reach_boundary_deg": self.close_reach_boundary_deg,
            "foiling_speed_knots": self.foiling_speed_knots,
        }
        records = [
            self.make_provenance_record(
                "metric",
                MetricNames.TACK_COUNT.value,
                inputs=input_channels,
                config={**config, "unit": "count"},
                changes=[
                    {
                        "field": "value",
                        "operation": "count_events",
                        "description": "Counted detected tack maneuvers",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                MetricNames.GYBE_COUNT.value,
                inputs=input_channels,
                config={**config, "unit": "count"},
                changes=[
                    {
                        "field": "value",
                        "operation": "count_events",
                        "description": "Counted detected gybe maneuvers",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                MetricNames.FOILING_TACK_COUNT.value,
                inputs=input_channels,
                config={**config, "unit": "count"},
                changes=[
                    {
                        "field": "value",
                        "operation": "count_events",
                        "description": "Counted detected foiling tack maneuvers",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                MetricNames.FOILING_GYBE_COUNT.value,
                inputs=input_channels,
                config={**config, "unit": "count"},
                changes=[
                    {
                        "field": "value",
                        "operation": "count_events",
                        "description": "Counted detected foiling gybe maneuvers",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                MetricNames.FOILING_TACK_PERCENTAGE.value,
                inputs=input_channels,
                config={**config, "unit": "percent"},
                changes=[
                    {
                        "field": "value",
                        "operation": "aggregate_percentage",
                        "description": "Computed foiling tack percentage from detected maneuvers",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                MetricNames.FOILING_GYBE_PERCENTAGE.value,
                inputs=input_channels,
                config={**config, "unit": "percent"},
                changes=[
                    {
                        "field": "value",
                        "operation": "aggregate_percentage",
                        "description": "Computed foiling gybe percentage from detected maneuvers",
                    }
                ],
            ),
        ]

        event_types = {detection.event_type for detection in self._detections}
        if self.TACK_EVENT_TYPE in event_types:
            records.append(
                self.make_provenance_record(
                    "event",
                    self.TACK_EVENT_TYPE,
                    inputs=input_channels,
                    config=config,
                    changes=[
                        {
                            "field": "start_time",
                            "operation": "detect_sign_change_event",
                            "description": "Detected tack events from TWA sign changes and speed filters",
                        }
                    ],
                )
            )
        if self.GYBE_EVENT_TYPE in event_types:
            records.append(
                self.make_provenance_record(
                    "event",
                    self.GYBE_EVENT_TYPE,
                    inputs=input_channels,
                    config=config,
                    changes=[
                        {
                            "field": "start_time",
                            "operation": "detect_sign_change_event",
                            "description": "Detected gybe events from TWA sign changes and speed filters",
                        }
                    ],
                )
            )

        return records

    def print_summary(self) -> None:
        """Print a one-line maneuver summary for logs and local runs.

        Args:
            None.

        Returns:
            None.

        Example:
            Output may look like
            ``maneuvers: 3 tacks (2 foiling, 66.7%), 1 gybes (0 foiling, 0.0%)``.
        """

        tack_count = self._summary_counts[self.TACK_EVENT_TYPE]
        gybe_count = self._summary_counts[self.GYBE_EVENT_TYPE]
        foiling_tack_count = self._summary_counts["foiling_tack"]
        foiling_gybe_count = self._summary_counts["foiling_gybe"]
        print(
            "maneuvers: "
            f"{tack_count} tacks ({foiling_tack_count} foiling, "
            f"{self._safe_percentage(foiling_tack_count, tack_count):.1f}%), "
            f"{gybe_count} gybes ({foiling_gybe_count} foiling, "
            f"{self._safe_percentage(foiling_gybe_count, gybe_count):.1f}%)"
        )
        for detection, timestamp in zip(self._detections, self._detection_timestamps):
            print(
                f"{self._format_timestamp_utc(timestamp)}"
                f" | {detection.event_type}"
                f" | {detection.avg_speed_before_kn:.1f} kn"
                f" | {detection.avg_speed_after_kn:.1f} kn"
            )

    def _prepare_analysis_state(self) -> None:
        """Reset cached analyzer state before a new session is processed.

        Args:
            None.

        Returns:
            None.

        Example:
            Called automatically at the start of ``analyze(session)`` so counts
            from a previous session do not leak into the next run.
        """

        super()._prepare_analysis_state()
        self._selected_twa_channel_name = None
        self._detections = []
        self._detection_timestamps = []
        self._summary_counts = {
            self.TACK_EVENT_TYPE: 0,
            self.GYBE_EVENT_TYPE: 0,
            "foiling_tack": 0,
            "foiling_gybe": 0,
        }

    def _add_metric(
        self, session: CanonicalSession, name: str, value: float, unit: str
    ) -> None:
        """Add one maneuver summary metric to the session.

        Args:
            session: Session that will receive the metric.
            name: Metric name such as ``"tack_count"``.
            value: Numeric metric value to persist.
            unit: Metric unit string such as ``"count"`` or ``"percent"``.

        Returns:
            None.

        Example:
            ``_add_metric(session, "gybe_count", 2.0, "count")`` stores a gybe
            count metric sourced from this analyzer.
        """

        session.add_metric(
            Metric(
                name=name,
                value=value,
                unit=unit,
                source=self.producer,
                metadata={
                    "twa_channel": self._selected_twa_channel_name,
                    "speed_channel": ChannelNames.SOG.value,
                },
            )
        )

    def _select_twa_channel(self, session: CanonicalSession) -> Channel | None:
        """Choose the best available TWA channel for maneuver detection.

        Args:
            session: Session whose channels may contain imported and/or derived
                TWA variants.

        Returns:
            The preferred TWA ``Channel`` instance, or ``None`` if the session
            does not contain any usable TWA channel.

        Example:
            If both ``twa`` and ``twa_manual_wind_direction_deg`` exist, this
            method prefers the manual-wind-derived variant.
        """

        twa_channels = [
            channel
            for channel in session.channels.values()
            if channel.name == ChannelNames.TWA.value or channel.name.startswith("twa_")
        ]
        if not twa_channels:
            return None

        manual_metric_name = MetricNames.MANUAL_WIND_DIRECTION.value

        def score(channel: Channel) -> tuple[int, int]:
            reference_name = channel.metadata.get("wind_direction_reference")
            if reference_name == manual_metric_name:
                return (100, -len(channel.name))
            if channel.name.endswith(manual_metric_name):
                return (90, -len(channel.name))
            if (
                channel.name == ChannelNames.TWA.value
                and channel.source == "TWAAnalyzer"
                and session.has_metric(manual_metric_name)
            ):
                return (80, 0)
            if channel.name == ChannelNames.TWA.value:
                return (70, 0)
            if reference_name == ChannelNames.TWD_EXTERNAL.value:
                return (60, -len(channel.name))
            if channel.name.endswith(ChannelNames.TWD_EXTERNAL.value):
                return (50, -len(channel.name))
            return (10, -len(channel.name))

        return max(twa_channels, key=score)

    def _detect_maneuvers(
        self,
        timestamps: np.ndarray,
        twa_values: np.ndarray,
        speed_values: np.ndarray,
    ) -> list[_ManeuverDetection]:
        """Detect maneuver candidates and classify them as tacks or gybes.

        Args:
            timestamps: Numeric timestamps in seconds aligned to the TWA samples.
            twa_values: Signed TWA values in degrees on the maneuver timeline.
            speed_values: Speed values in knots aligned to the same timeline.

        Returns:
            A list of ``_ManeuverDetection`` entries sorted in time order. The
            list is empty when no maneuver passes the sign-change, speed, and
            de-duplication rules.

        Example:
            A transition from ``-35`` to ``35`` with adequate speed becomes one
            tack detection, while closely spaced repeated sign flips are reduced
            to the first accepted candidate.
        """

        if len(timestamps) < 3:
            return []

        signs = np.sign(twa_values)
        valid_twa = np.isfinite(twa_values)
        signs = np.where(valid_twa, signs, np.nan)

        sign_change = (
            valid_twa[1:]
            & valid_twa[:-1]
            & np.isfinite(signs[1:])
            & np.isfinite(signs[:-1])
            & (signs[1:] != signs[:-1])
        )
        if not np.any(sign_change):
            return []

        candidate_indices = np.flatnonzero(sign_change) + 1
        candidate_indices = candidate_indices[
            np.isfinite(
                self._interpolate_values_at_times(
                    timestamps,
                    speed_values,
                    timestamps[candidate_indices] - self.speed_measure_seconds,
                )
            )
        ]
        if candidate_indices.size == 0:
            return []

        # this filter makes sure that only one event is detected in a time interval
        # so that drifting or unclean maneuvers are only deteced as one
        candidate_indices = self._remove_duplicates(candidate_indices, timestamps)

        detections: list[_ManeuverDetection] = []
        for index in candidate_indices:
            event_type = self._determine_event_type(
                index,
                timestamps,
                twa_values,
            )

            maneuver_time = float(timestamps[index])
            entry_speed_mask = self._window_mask(
                timestamps,
                maneuver_time - self.speed_measure_seconds,
                maneuver_time,
                include_end=False,
            )

            if event_type == self.TACK_EVENT_TYPE:
                # throw out maneuver when entry speed is too low (e.g. capsized)
                perc_above_tack_speed = (
                    speed_values[entry_speed_mask] >= self.min_tack_entry_speed_kn
                ).mean()

                if perc_above_tack_speed < self.min_entry_speed_percentage:
                    continue

            else:
                # throw out maneuver when entry speed is too low (e.g. capsized)
                perc_above_gybe_speed = (
                    speed_values[entry_speed_mask] >= self.min_gybe_entry_speed_kn
                ).mean()
                if perc_above_gybe_speed < self.min_entry_speed_percentage:
                    continue

            detections.append(
                _ManeuverDetection(
                    index=int(index),
                    event_type=event_type,
                    is_foiling=self._is_foiling(
                        index, timestamps, speed_values, event_type
                    ),
                    mean_abs_twa_deg=20,
                    avg_speed_before_kn=self._mean_finite(
                        speed_values[
                            self._window_mask(
                                timestamps,
                                maneuver_time - self.foiling_interval_seconds,
                                maneuver_time,
                                include_end=False,
                            )
                        ]
                    ),
                    avg_speed_after_kn=self._mean_finite(
                        speed_values[
                            self._window_mask(
                                timestamps,
                                maneuver_time,
                                maneuver_time + self.foiling_interval_seconds,
                                include_start=False,
                                include_end=True,
                            )
                        ]
                    ),
                )
            )

        return detections

    def _is_foiling(
        self,
        index: int,
        timestamps: np.ndarray,
        speed_values: np.ndarray,
        event_type: str,
    ) -> bool:
        """Current implementation: x percentage of datapoints must be above foiilng
        speed before and after the maneuver. Configured with foiling_interval_seconds,
        foiling_percentage and foiling_speed_knots
        """
        maneuver_time = float(timestamps[index])
        entry_foiling_mask = self._window_mask(
            timestamps,
            maneuver_time - self.foiling_interval_seconds,
            maneuver_time,
            include_end=False,
        )

        exit_foiling_mask = self._window_mask(
            timestamps,
            maneuver_time,
            maneuver_time + self.foiling_interval_seconds,
            include_start=False,
            include_end=True,
        )

        if event_type == self.TACK_EVENT_TYPE:
            # needs to be dialed in once I actually manage foiling gybes
            return False
        else:
            entry_foiling_percentage = (
                speed_values[entry_foiling_mask] >= self.foiling_speed_knots
            ).mean()
            exit_foiling_percentage = (
                speed_values[exit_foiling_mask] >= self.foiling_speed_knots
            ).mean()

            return bool(
                (entry_foiling_percentage >= self.foiling_percentage)
                and (exit_foiling_percentage >= self.foiling_percentage)
            )

    def _determine_event_type(
        self, index: int, timestamps: np.ndarray, twa_values: np.ndarray
    ) -> str:
        """Determines if a given event is a tack or a gybe based on twa. if twa changes trough 0 its a tack it it changes trough 180 its a gybe. make sure to also get the correct event if 0 or 180 are not exactly in the twa values."""

        if index <= 0 or index >= len(twa_values):
            raise ValueError(
                "maneuver index must have a previous TWA sample and be within "
                "the TWA array"
            )
        if len(timestamps) != len(twa_values):
            raise ValueError("timestamps and twa_values must have the same length")

        maneuver_time = float(timestamps[index])
        if not np.isfinite(maneuver_time):
            raise ValueError("maneuver timestamp must be finite")

        before_mask = self._window_mask(
            timestamps,
            maneuver_time - self.classification_interval_seconds,
            maneuver_time,
            include_end=False,
        )
        after_mask = self._window_mask(
            timestamps,
            maneuver_time,
            maneuver_time + self.classification_interval_seconds,
        )

        before_twa = twa_values[before_mask]
        after_twa = twa_values[after_mask]
        if not np.any(np.isfinite(before_twa)):
            before_twa = np.asarray([twa_values[index - 1]], dtype=float)
        if not np.any(np.isfinite(after_twa)):
            after_twa = np.asarray([twa_values[index]], dtype=float)

        before_twa = before_twa[np.isfinite(before_twa)]
        after_twa = after_twa[np.isfinite(after_twa)]
        if before_twa.size == 0 or after_twa.size == 0:
            raise ValueError(
                "cannot determine maneuver event type without finite TWA values "
                "before and after the maneuver"
            )

        before_radians = np.deg2rad(before_twa)
        after_radians = np.deg2rad(after_twa)
        previous_twa = float(
            np.rad2deg(
                np.arctan2(
                    np.mean(np.sin(before_radians)),
                    np.mean(np.cos(before_radians)),
                )
            )
        )
        current_twa = float(
            np.rad2deg(
                np.arctan2(
                    np.mean(np.sin(after_radians)),
                    np.mean(np.cos(after_radians)),
                )
            )
        )

        if np.isclose(previous_twa, -180.0):
            previous_twa = 180.0
        if np.isclose(current_twa, -180.0):
            current_twa = 180.0

        previous_sign = np.sign(previous_twa)
        current_sign = np.sign(current_twa)
        if previous_sign == 0 or current_sign == 0:
            return self.TACK_EVENT_TYPE

        abs_delta = abs(current_twa - previous_twa)
        if abs_delta > 180.0:
            return self.GYBE_EVENT_TYPE
        if np.isclose(abs_delta, 180.0):
            mean_abs_twa = (abs(previous_twa) + abs(current_twa)) / 2.0
            if mean_abs_twa > self.close_reach_boundary_deg:
                return self.GYBE_EVENT_TYPE

        return self.TACK_EVENT_TYPE

    def _align_channel_values_to_target_timestamps(
        self, channel: Channel, target_timestamps: np.ndarray
    ) -> np.ndarray:
        """Interpolate a channel onto a target timestamp array.

        Args:
            channel: Source channel whose values should be aligned.
            target_timestamps: Numeric timestamps, in seconds, that define the
                desired output timeline.

        Returns:
            A float numpy array of channel values interpolated onto
            ``target_timestamps``. Values outside the source bounds are ``NaN``.

        Example:
            Boat-speed samples at 2 Hz can be aligned onto a 1 Hz TWA timeline
            before running maneuver detection.
        """

        source_timestamps = self._timestamps_to_numeric(channel.timestamps)
        source_values = np.asarray(channel.values, dtype=float)
        return self._interpolate_values_at_times(
            source_timestamps,
            source_values,
            target_timestamps,
        )

    def _interpolate_values_at_times(
        self,
        source_timestamps: np.ndarray,
        source_values: np.ndarray,
        query_timestamps: np.ndarray,
    ) -> np.ndarray:
        """Linearly interpolate values at requested timestamps.

        Args:
            source_timestamps: Numeric source timestamps in seconds.
            source_values: Float values sampled at ``source_timestamps``.
            query_timestamps: Numeric timestamps where interpolated values are
                requested.

        Returns:
            A float numpy array matching ``query_timestamps``. Samples outside the
            source time range are set to ``NaN``.

        Example:
            ``_interpolate_values_at_times([0, 10], [4, 6], [5])`` returns
            approximately ``[5.0]``.
        """

        valid_mask = np.isfinite(source_timestamps) & np.isfinite(source_values)
        if not np.any(valid_mask):
            return np.full(np.asarray(query_timestamps).shape, np.nan, dtype=float)

        source_timestamps = source_timestamps[valid_mask]
        source_values = source_values[valid_mask]

        sort_order = np.argsort(source_timestamps, kind="stable")
        source_timestamps = source_timestamps[sort_order]
        source_values = source_values[sort_order]

        unique_timestamps, unique_indices = np.unique(
            source_timestamps, return_index=True
        )
        source_timestamps = unique_timestamps
        source_values = source_values[unique_indices]

        query_array = np.asarray(query_timestamps, dtype=float)
        if source_timestamps.size == 1:
            interpolated = np.full(query_array.shape, source_values[0], dtype=float)
            interpolated[
                (query_array < source_timestamps[0])
                | (query_array > source_timestamps[0])
            ] = np.nan
            return interpolated

        interpolated = np.interp(query_array, source_timestamps, source_values)
        outside_bounds = (query_array < source_timestamps[0]) | (
            query_array > source_timestamps[-1]
        )
        interpolated[outside_bounds] = np.nan
        return interpolated

    def _remove_duplicates(
        self, candidate_indices: np.ndarray, timestamps: np.ndarray
    ) -> np.ndarray:
        """Keep only the first maneuver candidate in each minimum-interval group.

        Args:
            candidate_indices: Sorted candidate sample indices.
            timestamps: Numeric timestamps aligned with those indices.

        Returns:
            A numpy array containing only accepted candidate indices. Candidates
            that occur too soon after the last accepted one are discarded.

        Example:
            With a 15-second minimum interval, candidates at ``[10, 14, 31]``
            keep ``10`` and ``31`` but drop ``14``.
        """

        if candidate_indices.size == 0:
            return np.array([], dtype=int)

        kept_indices = [int(candidate_indices[0])]
        last_kept_time = float(timestamps[candidate_indices[0]])
        for index in candidate_indices[1:]:
            candidate_time = float(timestamps[index])
            if candidate_time - last_kept_time >= self.min_maneuver_interval_seconds:
                kept_indices.append(int(index))
                last_kept_time = candidate_time

        return np.asarray(kept_indices, dtype=int)

    def _window_mask(
        self,
        timestamps: np.ndarray,
        start_time: float,
        end_time: float,
        *,
        include_start: bool = True,
        include_end: bool = True,
    ) -> np.ndarray:
        """Build a boolean mask for samples inside a time interval.

        Args:
            timestamps: Numeric timestamps in seconds.
            start_time: Window start.
            end_time: Window end.
            include_start: Whether the start boundary is included.
            include_end: Whether the end boundary is included.

        Returns:
            A boolean numpy mask selecting finite timestamps between
            ``start_time`` and ``end_time``.

        Example:
            ``_window_mask([0, 5, 10], 4, 10)`` selects the samples at ``5`` and
            ``10``.
        """
        lower_bound_mask = (
            timestamps >= start_time if include_start else timestamps > start_time
        )
        upper_bound_mask = (
            timestamps <= end_time if include_end else timestamps < end_time
        )

        return np.isfinite(timestamps) & lower_bound_mask & upper_bound_mask

    def _mean_finite(self, values: np.ndarray) -> float:
        """Compute the arithmetic mean of finite values only.

        Args:
            values: Array-like numeric values that may include ``NaN``.

        Returns:
            The mean of the finite subset, or ``0.0`` when no finite values are
            present.

        Example:
            ``_mean_finite([4.0, np.nan, 6.0])`` returns ``5.0``.
        """

        finite_values = np.asarray(values, dtype=float)
        finite_values = finite_values[np.isfinite(finite_values)]
        if finite_values.size == 0:
            return 0.0
        return float(np.mean(finite_values))

    def _all_finite_at_or_above(self, values: np.ndarray, threshold: float) -> bool:
        """Return whether every finite sample meets a minimum threshold.

        Args:
            values: Array-like numeric values that may include ``NaN``.
            threshold: Minimum allowed value for each finite sample.

        Returns:
            ``True`` when at least one finite sample exists and all finite samples
            are greater than or equal to ``threshold``; otherwise ``False``.
        """

        finite_values = np.asarray(values, dtype=float)
        finite_values = finite_values[np.isfinite(finite_values)]
        if finite_values.size == 0:
            return False
        return bool(np.all(finite_values >= threshold))

    def _safe_percentage(self, numerator: int, denominator: int) -> float:
        """Compute a percentage while safely handling zero denominators.

        Args:
            numerator: Count of successful or matching items.
            denominator: Total count used as the percentage base.

        Returns:
            ``0.0`` when ``denominator`` is zero or negative, otherwise the
            percentage ``100 * numerator / denominator``.

        Example:
            ``_safe_percentage(2, 4)`` returns ``50.0`` and
            ``_safe_percentage(0, 0)`` returns ``0.0``.
        """

        if denominator <= 0:
            return 0.0
        return 100.0 * float(numerator) / float(denominator)

    def _format_timestamp_utc(self, timestamp: object) -> str:
        """Render a timestamp as an ISO-8601 UTC string."""

        if isinstance(timestamp, np.datetime64):
            timestamp = (
                timestamp.astype("datetime64[ns]").astype(np.int64) / 1_000_000_000.0
            )

        if isinstance(timestamp, datetime):
            datetime_value = (
                timestamp.astimezone(UTC)
                if timestamp.tzinfo is not None
                else timestamp.replace(tzinfo=UTC)
            )
            return datetime_value.isoformat().replace("+00:00", "Z")

        try:
            datetime_value = datetime.fromtimestamp(float(timestamp), tz=UTC)
        except (TypeError, ValueError, OSError, OverflowError):
            return str(timestamp)

        return datetime_value.isoformat().replace("+00:00", "Z")

    def _timestamps_to_numeric(self, timestamps: np.ndarray) -> np.ndarray:
        """Convert mixed timestamp arrays into float seconds.

        Args:
            timestamps: Numpy array containing numeric, ``datetime64``, or Python
            ``datetime`` timestamps.

        Returns:
            A float numpy array in seconds suitable for interpolation and window
            calculations. Unparseable timestamps become ``NaN``.

        Example:
            ``datetime64`` session timestamps are converted into Unix seconds so
            they can be compared against maneuver window durations.
        """

        timestamp_array = np.asarray(timestamps)

        if np.issubdtype(timestamp_array.dtype, np.number):
            return timestamp_array.astype(float, copy=False)

        if np.issubdtype(timestamp_array.dtype, np.datetime64):
            return (
                timestamp_array.astype("datetime64[ns]").astype(np.int64).astype(float)
                / 1_000_000_000.0
            )

        numeric_timestamps = np.empty(timestamp_array.shape[0], dtype=float)
        for index, timestamp in enumerate(timestamp_array.tolist()):
            if timestamp is None:
                numeric_timestamps[index] = np.nan
                continue

            if isinstance(timestamp, np.datetime64):
                numeric_timestamps[index] = (
                    timestamp.astype("datetime64[ns]").astype(np.int64)
                    / 1_000_000_000.0
                )
                continue

            if isinstance(timestamp, datetime):
                numeric_timestamps[index] = float(timestamp.timestamp())
                continue

            try:
                numeric_timestamps[index] = float(timestamp)
            except (TypeError, ValueError):
                numeric_timestamps[index] = np.nan

        return numeric_timestamps
