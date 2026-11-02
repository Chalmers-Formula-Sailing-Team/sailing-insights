from __future__ import annotations

import numpy as np
from src.analyzer.analyzer import Analyzer
from src.constants.ChannelNames import ChannelNames
from src.models.canonicalSession import CanonicalSession, Channel, ProvenanceRecord

_NANOSECONDS_PER_SECOND = 1_000_000_000.0


class COGAnalyzer(Analyzer):
    REQUIRED_CHANNELS = (
        ChannelNames.LATITUDE.value,
        ChannelNames.LONGITUDE.value,
    )
    COG_CHANNEL_NAME = ChannelNames.COG.value

    def __init__(self) -> None:
        self._average_course_deg: float | None = None

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        return self.cog(session)

    def cog(self, session: CanonicalSession) -> CanonicalSession:
        lat_channel = session.get_channel(ChannelNames.LATITUDE.value)
        lon_channel = session.get_channel(ChannelNames.LONGITUDE.value)

        self._validate_track_channels(lat_channel, lon_channel)

        self.add_channel(
            session,
            Channel(
                name=self.COG_CHANNEL_NAME,
                timestamps=lat_channel.timestamps.copy(),
                values=self._calculate_cog_values(
                    np.asarray(lat_channel.values, dtype=float),
                    np.asarray(lon_channel.values, dtype=float),
                ),
                unit="deg",
                source=self.producer,
                is_derived=True,
                metadata={
                    "channels": list(self.REQUIRED_CHANNELS),
                    "method": "initial_bearing_previous_sample",
                },
            ),
        )
        self._average_course_deg = self._calculate_average_course_deg(
            session.get_channel(self.COG_CHANNEL_NAME).values
        )

        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        return [
            self.make_provenance_record(
                "channel",
                self.COG_CHANNEL_NAME,
                inputs=list(self.REQUIRED_CHANNELS),
                config={
                    "method": "initial_bearing_previous_sample",
                    "channels": list(self.REQUIRED_CHANNELS),
                    "unit": "deg",
                },
                changes=[
                    {
                        "field": "values",
                        "operation": "calculate_course_over_ground",
                        "description": "Computed course over ground from consecutive lat/lon samples",
                    }
                ],
            )
        ]

    def _validate_track_channels(
        self, lat_channel: Channel, lon_channel: Channel
    ) -> None:
        if len(lat_channel.timestamps) != len(lon_channel.timestamps):
            raise ValueError(
                "COGAnalyzer requires "
                f"'{ChannelNames.LATITUDE.value}' and '{ChannelNames.LONGITUDE.value}' "
                "to have equal timestamp counts"
            )

        if not np.array_equal(lat_channel.timestamps, lon_channel.timestamps):
            raise ValueError(
                "COGAnalyzer requires "
                f"'{ChannelNames.LATITUDE.value}' and '{ChannelNames.LONGITUDE.value}' "
                "to share identical timestamps"
            )

    def _calculate_cog_values(
        self, lat_values: np.ndarray, lon_values: np.ndarray
    ) -> np.ndarray:
        sample_count = len(lat_values)
        if sample_count == 0:
            return np.array([], dtype=float)

        cog_values = np.full(sample_count, np.nan, dtype=float)
        if sample_count < 2:
            return cog_values

        valid_samples = np.isfinite(lat_values) & np.isfinite(lon_values)
        pair_mask = valid_samples[:-1] & valid_samples[1:]
        if not np.any(pair_mask):
            return cog_values

        lat_a = np.radians(lat_values[:-1][pair_mask])
        lon_a = np.radians(lon_values[:-1][pair_mask])
        lat_b = np.radians(lat_values[1:][pair_mask])
        lon_b = np.radians(lon_values[1:][pair_mask])

        delta_lon = lon_b - lon_a
        y = np.sin(delta_lon) * np.cos(lat_b)
        x = np.cos(lat_a) * np.sin(lat_b) - np.sin(lat_a) * np.cos(lat_b) * np.cos(
            delta_lon
        )
        bearings = (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0

        movement_mask = ~np.isclose(x, 0.0, atol=1e-12) | ~np.isclose(
            y, 0.0, atol=1e-12
        )
        target_indices = np.nonzero(pair_mask)[0][movement_mask] + 1
        cog_values[target_indices] = bearings[movement_mask]

        return cog_values

    def print_summary(self) -> None:
        average_course = (
            str(self._average_course_deg)
            if self._average_course_deg is not None
            else "n/a"
        )
        print(f"average_course: {average_course} deg")

    def _calculate_average_course_deg(self, cog_values: np.ndarray) -> float | None:
        valid_values = cog_values[np.isfinite(cog_values)]
        if valid_values.size == 0:
            return None

        angles_rad = np.radians(valid_values)
        mean_sin = float(np.mean(np.sin(angles_rad)))
        mean_cos = float(np.mean(np.cos(angles_rad)))
        if np.isclose(mean_sin, 0.0, atol=1e-12) and np.isclose(
            mean_cos, 0.0, atol=1e-12
        ):
            return None

        return float((np.degrees(np.arctan2(mean_sin, mean_cos)) + 360.0) % 360.0)

    def _producer_suffix(self) -> str:
        return "cogAnalyzer"


class TurnRateAnalyzer(Analyzer):
    REQUIRED_CHANNELS = (ChannelNames.COG.value, ChannelNames.SOG.value)
    TURN_RATE_CHANNEL_NAME = ChannelNames.TURN_RATE.value

    def __init__(self, min_speed_knots: float = 1.0) -> None:
        if min_speed_knots < 0:
            raise ValueError("min_speed_knots must be greater than or equal to 0")

        self.min_speed_knots = float(min_speed_knots)
        self._average_abs_turn_rate_deg_s: float | None = None

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        cog_channel = session.get_channel(ChannelNames.COG.value)
        speed_channel = session.get_channel(ChannelNames.SOG.value)
        aligned_speed_values = self._align_speed_values_to_cog_timestamps(
            speed_channel,
            cog_channel.timestamps,
        )
        turn_rate_values = self._calculate_turn_rate_values(
            np.asarray(cog_channel.values, dtype=float),
            aligned_speed_values,
            cog_channel.timestamps,
        )

        self.add_channel(
            session,
            Channel(
                name=self.TURN_RATE_CHANNEL_NAME,
                timestamps=cog_channel.timestamps.copy(),
                values=turn_rate_values,
                unit="deg/s",
                source=self.producer,
                is_derived=True,
                metadata={
                    "channels": [
                        ChannelNames.COG.value,
                        ChannelNames.SOG.value,
                    ],
                    "method": "signed_circular_difference_over_elapsed_seconds",
                    "time_delta_source": "channel_timestamps",
                    "min_speed_kn": self.min_speed_knots,
                    "speed_alignment": "linear_interpolation_to_cog_timestamps",
                },
            ),
        )
        self._average_abs_turn_rate_deg_s = self._calculate_average_abs_turn_rate_deg_s(
            turn_rate_values
        )
        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        return [
            self.make_provenance_record(
                "channel",
                self.TURN_RATE_CHANNEL_NAME,
                inputs=[ChannelNames.COG.value, ChannelNames.SOG.value],
                config={
                    "channels": [
                        ChannelNames.COG.value,
                        ChannelNames.SOG.value,
                    ],
                    "method": "signed_circular_difference_over_elapsed_seconds",
                    "time_delta_source": "channel_timestamps",
                    "min_speed_kn": self.min_speed_knots,
                    "speed_alignment": "linear_interpolation_to_cog_timestamps",
                    "unit": "deg/s",
                },
                changes=[
                    {
                        "field": "values",
                        "operation": "calculate_turn_rate_from_course_over_ground",
                        "description": "Computed signed turn rate from consecutive COG samples and elapsed time",
                    }
                ],
            )
        ]

    def print_summary(self) -> None:
        average_abs_turn_rate = (
            f"{self._average_abs_turn_rate_deg_s:.3f}"
            if self._average_abs_turn_rate_deg_s is not None
            else "n/a"
        )
        print(f"average_abs_turn_rate: {average_abs_turn_rate} deg/s")

    def _calculate_turn_rate_values(
        self, cog_values: np.ndarray, speed_values: np.ndarray, timestamps: np.ndarray
    ) -> np.ndarray:
        sample_count = len(cog_values)
        turn_rate_values = np.full(sample_count, np.nan, dtype=float)
        if sample_count < 2:
            return turn_rate_values

        dt_seconds = self._calculate_interval_seconds(timestamps)
        dcog = self._circular_diff_deg(cog_values[1:], cog_values[:-1])
        speed_mask = (
            np.isfinite(speed_values[1:])
            & np.isfinite(speed_values[:-1])
            & (speed_values[1:] > self.min_speed_knots)
            & (speed_values[:-1] > self.min_speed_knots)
        )
        valid_mask = (
            np.isfinite(dcog)
            & np.isfinite(dt_seconds)
            & (dt_seconds > 0.0)
            & speed_mask
        )
        if not np.any(valid_mask):
            return turn_rate_values

        trailing_values = turn_rate_values[1:]
        trailing_values[valid_mask] = dcog[valid_mask] / dt_seconds[valid_mask]
        return turn_rate_values

    def _align_speed_values_to_cog_timestamps(
        self, speed_channel: Channel, cog_timestamps: np.ndarray
    ) -> np.ndarray:
        speed_values = np.asarray(speed_channel.values, dtype=float)
        if speed_values.size == 0:
            return np.full(len(cog_timestamps), np.nan, dtype=float)

        if len(speed_channel.timestamps) == len(cog_timestamps) and np.array_equal(
            speed_channel.timestamps, cog_timestamps
        ):
            return speed_values

        source_mask = self._finite_timestamp_mask(
            speed_channel.timestamps
        ) & np.isfinite(speed_values)
        if not np.any(source_mask):
            return np.full(len(cog_timestamps), np.nan, dtype=float)

        source_timestamps = speed_channel.timestamps[source_mask]
        source_values = speed_values[source_mask]
        if source_values.size == 1:
            return np.full(len(cog_timestamps), source_values[0], dtype=float)

        (
            normalized_source_times,
            normalized_target_times,
        ) = self._normalize_timestamps_for_interpolation(
            source_timestamps,
            cog_timestamps,
        )
        source_order = np.argsort(normalized_source_times, kind="stable")
        normalized_source_times = normalized_source_times[source_order]
        source_values = source_values[source_order]
        unique_source_times, unique_source_values = self._deduplicate_samples(
            normalized_source_times,
            source_values,
        )

        if unique_source_values.size == 1:
            return np.full(len(cog_timestamps), unique_source_values[0], dtype=float)

        return np.interp(
            normalized_target_times,
            unique_source_times,
            unique_source_values,
            left=unique_source_values[0],
            right=unique_source_values[-1],
        )

    def _calculate_interval_seconds(self, timestamps: np.ndarray) -> np.ndarray:
        if len(timestamps) < 2:
            return np.array([], dtype=float)

        if np.issubdtype(timestamps.dtype, np.datetime64):
            return (
                np.diff(timestamps.astype("datetime64[ns]")).astype(np.int64)
                / _NANOSECONDS_PER_SECOND
            )

        return np.diff(np.asarray(timestamps, dtype=float))

    def _circular_diff_deg(
        self, current_deg: np.ndarray, previous_deg: np.ndarray
    ) -> np.ndarray:
        current_values = np.asarray(current_deg, dtype=float)
        previous_values = np.asarray(previous_deg, dtype=float)
        return ((current_values - previous_values + 180.0) % 360.0) - 180.0

    def _normalize_timestamps_for_interpolation(
        self,
        source_timestamps: np.ndarray,
        target_timestamps: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        source_is_datetime = np.issubdtype(source_timestamps.dtype, np.datetime64)
        target_is_datetime = np.issubdtype(target_timestamps.dtype, np.datetime64)

        if source_is_datetime != target_is_datetime:
            raise ValueError(
                "TurnRateAnalyzer requires speed and COG timestamps to use compatible types"
            )

        if source_is_datetime:
            source_ns = source_timestamps.astype("datetime64[ns]").astype(np.int64)
            target_ns = target_timestamps.astype("datetime64[ns]").astype(np.int64)
            origin_ns = min(int(source_ns[0]), int(target_ns[0]))
            return (
                (source_ns - origin_ns) / _NANOSECONDS_PER_SECOND,
                (target_ns - origin_ns) / _NANOSECONDS_PER_SECOND,
            )

        source_numeric = np.asarray(source_timestamps, dtype=float)
        target_numeric = np.asarray(target_timestamps, dtype=float)
        origin = min(float(source_numeric[0]), float(target_numeric[0]))
        return source_numeric - origin, target_numeric - origin

    def _finite_timestamp_mask(self, timestamps: np.ndarray) -> np.ndarray:
        if np.issubdtype(timestamps.dtype, np.datetime64):
            return ~np.isnat(timestamps)
        return np.isfinite(np.asarray(timestamps, dtype=float))

    def _deduplicate_samples(
        self, timestamps: np.ndarray, values: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        deduplicated_timestamps: list[float] = []
        deduplicated_values: list[float] = []

        for timestamp, value in zip(timestamps, values, strict=False):
            if deduplicated_timestamps and np.isclose(
                deduplicated_timestamps[-1],
                timestamp,
            ):
                deduplicated_timestamps[-1] = float(timestamp)
                deduplicated_values[-1] = float(value)
                continue

            deduplicated_timestamps.append(float(timestamp))
            deduplicated_values.append(float(value))

        return (
            np.asarray(deduplicated_timestamps, dtype=float),
            np.asarray(deduplicated_values, dtype=float),
        )

    def _calculate_average_abs_turn_rate_deg_s(
        self, turn_rate_values: np.ndarray
    ) -> float | None:
        valid_values = turn_rate_values[np.isfinite(turn_rate_values)]
        if valid_values.size == 0:
            return None

        return float(np.mean(np.abs(valid_values)))
        return float(np.mean(np.abs(valid_values)))
        return float(np.mean(np.abs(valid_values)))
        return float(np.mean(np.abs(valid_values)))
