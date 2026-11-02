from __future__ import annotations

import numpy as np
from src.analyzer.analyzer import Analyzer
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Metric,
    ProvenanceRecord,
)


class FoilingAnalyzer(Analyzer):
    REQUIRED_CHANNELS = (ChannelNames.SOG.value,)
    FOILING_CHANNEL_NAME = ChannelNames.FOILING.value
    FOILING_TIME_METRIC_NAME = MetricNames.FOILING_TIME.value
    FOILING_PERCENTAGE_METRIC_NAME = MetricNames.FOILING_PERCENTAGE.value

    def __init__(self, foiling_speed_knots: float = 6.8) -> None:
        if foiling_speed_knots <= 0:
            raise ValueError("foiling_speed_knots must be greater than 0")

        self.foiling_speed_knots = float(foiling_speed_knots)
        self._foiling_time_minutes = 0.0
        self._foiling_percentage = 0.0

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        boat_speed_channel = session.get_channel(ChannelNames.SOG.value)
        foiling_values = self._calculate_foiling_values(boat_speed_channel.values)

        self.add_channel(
            session,
            Channel(
                name=self.FOILING_CHANNEL_NAME,
                timestamps=boat_speed_channel.timestamps.copy(),
                values=foiling_values,
                unit=None,
                source=self.producer,
                is_derived=True,
                metadata={
                    "channel": ChannelNames.SOG.value,
                    "threshold_kn": self.foiling_speed_knots,
                    "comparison": "greater_than_or_equal",
                },
            ),
        )

        self._foiling_time_minutes = self._calculate_foiling_time_minutes(
            boat_speed_channel.timestamps,
            foiling_values,
        )
        self._foiling_percentage = self._calculate_foiling_percentage(
            boat_speed_channel.timestamps,
            foiling_values,
        )

        session.add_metric(
            Metric(
                name=self.FOILING_TIME_METRIC_NAME,
                value=self._foiling_time_minutes,
                unit="min",
                source=self.producer,
                metadata={
                    "channel": ChannelNames.SOG.value,
                    "threshold_kn": self.foiling_speed_knots,
                    "comparison": "greater_than_or_equal",
                },
            )
        )
        session.add_metric(
            Metric(
                name=self.FOILING_PERCENTAGE_METRIC_NAME,
                value=self._foiling_percentage,
                unit="percent",
                source=self.producer,
                metadata={
                    "channel": ChannelNames.SOG.value,
                    "threshold_kn": self.foiling_speed_knots,
                    "comparison": "greater_than_or_equal",
                },
            )
        )
        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        return [
            self.make_provenance_record(
                "channel",
                self.FOILING_CHANNEL_NAME,
                inputs=[ChannelNames.SOG.value],
                config={
                    "channel": ChannelNames.SOG.value,
                    "threshold_kn": self.foiling_speed_knots,
                    "comparison": "greater_than_or_equal",
                },
                changes=[
                    {
                        "field": "values",
                        "operation": "threshold_classification",
                        "description": "Classified foiling samples from boat speed threshold",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                self.FOILING_TIME_METRIC_NAME,
                inputs=[ChannelNames.SOG.value],
                config={
                    "channel": ChannelNames.SOG.value,
                    "threshold_kn": self.foiling_speed_knots,
                    "comparison": "greater_than_or_equal",
                    "unit": "min",
                },
                changes=[
                    {
                        "field": "value",
                        "operation": "aggregate_duration",
                        "description": "Computed total foiling time from boat speed threshold",
                    }
                ],
            ),
            self.make_provenance_record(
                "metric",
                self.FOILING_PERCENTAGE_METRIC_NAME,
                inputs=[ChannelNames.SOG.value],
                config={
                    "channel": ChannelNames.SOG.value,
                    "threshold_kn": self.foiling_speed_knots,
                    "comparison": "greater_than_or_equal",
                    "unit": "percent",
                },
                changes=[
                    {
                        "field": "value",
                        "operation": "aggregate_percentage",
                        "description": "Computed foiling percentage from boat speed threshold",
                    }
                ],
            ),
        ]

    def print_summary(self) -> None:
        print(
            "foiling: "
            f"fly time {self._foiling_time_minutes:.1f} min "
            f"({self._foiling_percentage:.1f}% of session)"
        )

    def _calculate_foiling_values(self, boat_speed_values: np.ndarray) -> np.ndarray:
        speed_values = np.asarray(boat_speed_values, dtype=float)
        return np.isfinite(speed_values) & (speed_values >= self.foiling_speed_knots)

    def _calculate_foiling_time_minutes(
        self, timestamps: np.ndarray, foiling_values: np.ndarray
    ) -> float:
        interval_seconds = self._calculate_interval_seconds(timestamps)
        if interval_seconds.size == 0:
            return 0.0

        valid_intervals = np.isfinite(interval_seconds) & (interval_seconds > 0)
        foiling_duration_seconds = float(
            np.sum(interval_seconds[valid_intervals & foiling_values[:-1]])
        )
        return foiling_duration_seconds / 60.0

    def _calculate_foiling_percentage(
        self, timestamps: np.ndarray, foiling_values: np.ndarray
    ) -> float:
        interval_seconds = self._calculate_interval_seconds(timestamps)
        if interval_seconds.size == 0:
            return 0.0

        valid_intervals = np.isfinite(interval_seconds) & (interval_seconds > 0)
        total_duration_seconds = float(np.sum(interval_seconds[valid_intervals]))
        if total_duration_seconds == 0:
            return 0.0

        foiling_duration_seconds = float(
            np.sum(interval_seconds[valid_intervals & foiling_values[:-1]])
        )
        return 100.0 * foiling_duration_seconds / total_duration_seconds

    def _calculate_interval_seconds(self, timestamps: np.ndarray) -> np.ndarray:
        if len(timestamps) < 2:
            return np.array([], dtype=float)

        if np.issubdtype(timestamps.dtype, np.datetime64):
            return np.diff(timestamps.astype("datetime64[ns]")).astype(np.int64) / 1e9

        return np.diff(np.asarray(timestamps, dtype=float))
