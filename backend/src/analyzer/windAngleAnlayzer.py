from __future__ import annotations

from datetime import datetime

import numpy as np
from src.analyzer.analyzer import Analyzer
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.models.canonicalSession import CanonicalSession, Channel, ProvenanceRecord


class TWAAnalyzer(Analyzer):
    REQUIRED_CHANNELS = (ChannelNames.COG.value,)
    TWA_CHANNEL_NAME = ChannelNames.TWA.value
    EXTERNAL_WIND_DIRECTION_CHANNEL_NAME = ChannelNames.TWD_EXTERNAL.value
    MANUAL_WIND_DIRECTION_METRIC_NAME = MetricNames.MANUAL_WIND_DIRECTION.value

    def __init__(self) -> None:
        self._produced_channel_name: str | None = None
        self._wind_reference_name: str | None = None
        self._wind_reference_type: str | None = None
        self._wind_direction_alignment: str | None = None
        self._summary_reference_label = "no wind direction reference"

    def analyze(self, session: CanonicalSession) -> CanonicalSession:
        self._prepare_analysis_state()
        session.require_channels(self.required_channels)

        analyzed_session = self._analyze(session)
        if self._produced_channel_name is None:
            return analyzed_session

        for record in self.build_provenance_records(analyzed_session):
            self._validate_provenance_record(analyzed_session, record)
            analyzed_session.add_provenance(record)

        return analyzed_session

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        cog_channel = session.get_channel(ChannelNames.COG.value)
        wind_reference = self._resolve_wind_reference(
            session, cog_channel.timestamps, len(cog_channel.values)
        )
        if wind_reference is None:
            self._summary_reference_label = "no wind direction reference"
            return session

        (
            wind_direction_values,
            reference_name,
            reference_type,
            reference_alignment,
            summary_reference_label,
        ) = wind_reference

        twa_values = self._wrap_signed(
            wind_direction_values - np.asarray(cog_channel.values, dtype=float)
        )
        twa_channel_name = self._resolve_output_channel_name(session, reference_name)

        produced_channel_name = self.add_channel(
            session,
            Channel(
                name=twa_channel_name,
                timestamps=cog_channel.timestamps.copy(),
                values=twa_values,
                unit="deg",
                source=self.producer,
                is_derived=True,
                metadata={
                    "channels": [ChannelNames.COG.value],
                    "wind_direction_reference": reference_name,
                    "wind_direction_reference_type": reference_type,
                    "wind_direction_alignment": reference_alignment,
                    "method": "signed_wrapped_difference_wind_direction_minus_cog",
                },
            ),
        )

        self._produced_channel_name = produced_channel_name
        self._wind_reference_name = reference_name
        self._wind_reference_type = reference_type
        self._wind_direction_alignment = reference_alignment
        self._summary_reference_label = summary_reference_label
        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        if (
            self._produced_channel_name is None
            or self._wind_reference_name is None
            or self._wind_reference_type is None
            or self._wind_direction_alignment is None
        ):
            return []

        return [
            self.make_provenance_record(
                "channel",
                self._produced_channel_name,
                inputs=[ChannelNames.COG.value, self._wind_reference_name],
                config={
                    "channels": [ChannelNames.COG.value],
                    "wind_direction_reference": self._wind_reference_name,
                    "wind_direction_reference_type": self._wind_reference_type,
                    "wind_direction_alignment": self._wind_direction_alignment,
                    "method": "signed_wrapped_difference_wind_direction_minus_cog",
                    "unit": "deg",
                },
                changes=[
                    {
                        "field": "values",
                        "operation": "calculate_true_wind_angle_from_cog_and_wind_direction",
                        "description": "Computed signed TWA from course over ground and wind direction",
                    }
                ],
            )
        ]

    def print_summary(self) -> None:
        produced_channel_name = self._produced_channel_name or self.TWA_CHANNEL_NAME
        print(
            f"twa: twa from {self._summary_reference_label} ({produced_channel_name})"
        )

    def _resolve_wind_reference(
        self,
        session: CanonicalSession,
        cog_timestamps: np.ndarray,
        target_sample_count: int,
    ) -> tuple[np.ndarray, str, str, str, str] | None:
        manual_wind_direction = self._get_manual_wind_direction(session)
        if manual_wind_direction is not None:
            return (
                np.full(target_sample_count, manual_wind_direction, dtype=float),
                self.MANUAL_WIND_DIRECTION_METRIC_NAME,
                "metric",
                "constant_manual_direction",
                "manual wind entry",
            )

        if session.has_channel(self.EXTERNAL_WIND_DIRECTION_CHANNEL_NAME):
            aligned_values = self._align_external_wind_direction_to_cog_timestamps(
                session.get_channel(self.EXTERNAL_WIND_DIRECTION_CHANNEL_NAME),
                cog_timestamps,
            )
            if aligned_values is not None:
                return (
                    aligned_values,
                    self.EXTERNAL_WIND_DIRECTION_CHANNEL_NAME,
                    "channel",
                    "circular_interpolation_to_cog_timestamps",
                    "wind dir channel",
                )

        return None

    def _get_manual_wind_direction(self, session: CanonicalSession) -> float | None:
        if not session.has_metric(self.MANUAL_WIND_DIRECTION_METRIC_NAME):
            return None

        metric_value = session.get_metric(self.MANUAL_WIND_DIRECTION_METRIC_NAME).value
        try:
            wind_direction = float(metric_value)
        except (TypeError, ValueError):
            return None

        if not np.isfinite(wind_direction):
            return None

        return float(wind_direction % 360.0)

    def _align_external_wind_direction_to_cog_timestamps(
        self,
        wind_channel: Channel,
        target_timestamps: np.ndarray,
    ) -> np.ndarray | None:
        source_timestamps = self._timestamps_to_numeric(wind_channel.timestamps)
        target_timestamps_numeric = self._timestamps_to_numeric(target_timestamps)
        source_values = np.asarray(wind_channel.values, dtype=float)

        valid_mask = np.isfinite(source_timestamps) & np.isfinite(source_values)
        if not np.any(valid_mask):
            return None

        source_timestamps = source_timestamps[valid_mask]
        source_values = source_values[valid_mask]

        if source_timestamps.size == 1:
            return np.full(
                target_timestamps_numeric.shape[0],
                float(source_values[0] % 360.0),
                dtype=float,
            )

        sort_order = np.argsort(source_timestamps, kind="stable")
        source_timestamps = source_timestamps[sort_order]
        source_values = source_values[sort_order]

        unique_timestamps, unique_indices = np.unique(
            source_timestamps, return_index=True
        )
        source_timestamps = unique_timestamps
        source_values = source_values[unique_indices]

        if source_timestamps.size == 1:
            return np.full(
                target_timestamps_numeric.shape[0],
                float(source_values[0] % 360.0),
                dtype=float,
            )

        unwrapped_radians = np.unwrap(np.radians(source_values))
        interpolated_radians = np.interp(
            target_timestamps_numeric,
            source_timestamps,
            unwrapped_radians,
        )
        return np.degrees(interpolated_radians) % 360.0

    def _resolve_output_channel_name(
        self, session: CanonicalSession, reference_name: str
    ) -> str:
        if not session.has_channel(self.TWA_CHANNEL_NAME):
            return self.TWA_CHANNEL_NAME
        return f"{self.TWA_CHANNEL_NAME}_{reference_name}"

    def _timestamps_to_numeric(self, timestamps: np.ndarray) -> np.ndarray:
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

    def _wrap_signed(self, angle_values: np.ndarray) -> np.ndarray:
        wrapped_angles = ((angle_values + 180.0) % 360.0) - 180.0
        wrapped_angles[np.isnan(angle_values)] = np.nan
        return wrapped_angles

    def _prepare_analysis_state(self) -> None:
        super()._prepare_analysis_state()
        self._produced_channel_name = None
        self._wind_reference_name = None
        self._wind_reference_type = None
        self._wind_direction_alignment = None
        self._summary_reference_label = "no wind direction reference"

    def _producer_suffix(self) -> str:
        return "twaAnalyzer"
        return "twaAnalyzer"
        return "twaAnalyzer"
        return "twaAnalyzer"
