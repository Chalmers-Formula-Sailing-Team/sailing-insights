from __future__ import annotations

import numpy as np
from src.analyzer.analyzer import Analyzer
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.models.canonicalSession import CanonicalSession, Metric, ProvenanceRecord
from src.utils.geo import haversine_distance_m, meters_to_nm


class SessionAnalyzer(Analyzer):
    REQUIRED_CHANNELS = (
        ChannelNames.SOG.value,
        ChannelNames.LATITUDE.value,
        ChannelNames.LONGITUDE.value,
    )
    MAX_SPEED_METRIC_NAME = MetricNames.MAX_BOAT_SPEED.value
    SESSION_DISTANCE_METRIC_NAME = MetricNames.SESSION_DISTANCE.value
    SESSION_DURATION_METRIC_NAME = MetricNames.SESSION_DURATION.value

    def __init__(self) -> None:
        self._summary_metrics: list[tuple[str, float, str]] = []

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        speed_channel = session.get_channel(ChannelNames.SOG.value)
        if len(speed_channel.values) == 0:
            raise ValueError(
                "SessionAnalyzer requires "
                f"'{ChannelNames.SOG.value}' to contain samples"
            )

        max_boat_speed_value = float(np.max(speed_channel.values))
        session_distance_nm = self._calculate_distance_nm(session)
        session_duration_min = self._calculate_duration_min(session)

        session.add_metric(
            Metric(
                name=self.MAX_SPEED_METRIC_NAME,
                value=max_boat_speed_value,
                unit=speed_channel.unit
                if speed_channel.unit is not None
                else "unknown",
                source=self.producer,
                metadata={"channel": ChannelNames.SOG.value},
            )
        )
        session.add_metric(
            Metric(
                name=self.SESSION_DISTANCE_METRIC_NAME,
                value=session_distance_nm,
                unit="nm",
                source=self.producer,
                metadata={"channels": list(self.REQUIRED_CHANNELS[1:])},
            )
        )
        session.add_metric(
            Metric(
                name=self.SESSION_DURATION_METRIC_NAME,
                value=session_duration_min,
                unit="min",
                source=self.producer,
                metadata={
                    "channel": ChannelNames.LATITUDE.value,
                    "method": "max_timestamp_minus_min_timestamp",
                },
            )
        )
        self._summary_metrics = [
            (
                self.MAX_SPEED_METRIC_NAME,
                max_boat_speed_value,
                speed_channel.unit or "unknown",
            ),
            (self.SESSION_DISTANCE_METRIC_NAME, session_distance_nm, "nm"),
            (self.SESSION_DURATION_METRIC_NAME, session_duration_min, "min"),
        ]
        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        return [
            self.make_provenance_record(
                "metric",
                self.MAX_SPEED_METRIC_NAME,
                inputs=[ChannelNames.SOG.value],
                config={"method": "max", "channel": ChannelNames.SOG.value},
                changes=[
                    {
                        "field": "value",
                        "operation": "aggregate_max",
                        "description": "Computed max session boat speed from speed samples",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                self.SESSION_DISTANCE_METRIC_NAME,
                inputs=list(self.REQUIRED_CHANNELS[1:]),
                config={
                    "method": "haversine_sum",
                    "channels": list(self.REQUIRED_CHANNELS[1:]),
                    "unit": "nm",
                },
                changes=[
                    {
                        "field": "value",
                        "operation": "aggregate_distance",
                        "description": "Computed total session distance from lat/lon track",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                self.SESSION_DURATION_METRIC_NAME,
                inputs=[ChannelNames.LATITUDE.value],
                config={
                    "method": "max_minus_min_timestamp",
                    "channel": ChannelNames.LATITUDE.value,
                    "unit": "min",
                },
                changes=[
                    {
                        "field": "value",
                        "operation": "aggregate_duration",
                        "description": "Computed session duration from lat timestamps",
                    }
                ],
            ),
        ]

    def _calculate_distance_nm(self, session: CanonicalSession) -> float:
        lat_values = np.asarray(
            session.get_channel(ChannelNames.LATITUDE.value).values, dtype=float
        )
        lon_values = np.asarray(
            session.get_channel(ChannelNames.LONGITUDE.value).values, dtype=float
        )

        if len(lat_values) != len(lon_values):
            raise ValueError(
                "SessionAnalyzer requires "
                f"'{ChannelNames.LATITUDE.value}' and "
                f"'{ChannelNames.LONGITUDE.value}' lengths to match"
            )

        if len(lat_values) < 2:
            return 0.0

        valid = np.isfinite(lat_values) & np.isfinite(lon_values)
        pair_mask = valid[:-1] & valid[1:]

        if not np.any(pair_mask):
            return 0.0

        distance_m = haversine_distance_m(
            lat_values[:-1][pair_mask],
            lon_values[:-1][pair_mask],
            lat_values[1:][pair_mask],
            lon_values[1:][pair_mask],
        )

        return float(np.sum(meters_to_nm(distance_m)))

    def _calculate_duration_min(self, session: CanonicalSession) -> float:
        lat_timestamps = np.asarray(
            session.get_channel(ChannelNames.LATITUDE.value).timestamps
        )
        if len(lat_timestamps) == 0:
            return 0.0

        if np.issubdtype(lat_timestamps.dtype, np.datetime64):
            valid_timestamps = lat_timestamps[~np.isnat(lat_timestamps)]
            if len(valid_timestamps) < 2:
                return 0.0
            duration = valid_timestamps.max() - valid_timestamps.min()
            return float(duration / np.timedelta64(1, "m"))

        valid_timestamps = lat_timestamps[np.isfinite(lat_timestamps.astype(float))]
        if len(valid_timestamps) < 2:
            return 0.0

        duration_seconds = float(np.max(valid_timestamps) - np.min(valid_timestamps))
        return duration_seconds / 60.0

    def print_summary(self) -> None:
        for metric_name, value, unit in self._summary_metrics:
            print(f"{metric_name}: {value} {unit}")
