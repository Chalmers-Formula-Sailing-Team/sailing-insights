from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.constants.ChannelNames import ChannelNames
from src.models.canonicalSession import CanonicalSession, ProvenanceRecord
from src.transformer.channelTransformer import ChannelTransformer


@dataclass(slots=True)
class _InterpolationStats:
    inserted_samples: int = 0
    interpolated_gaps: int = 0
    skipped_gaps: int = 0
    target_frequency_duration_ns: int = 0
    total_duration_ns: int = 0

    @property
    def quality_percent(self) -> float | None:
        if self.total_duration_ns == 0:
            return None
        return 100.0 * self.target_frequency_duration_ns / self.total_duration_ns


@dataclass(frozen=True, slots=True)
class InterpolationSummary:
    frequency_hz: float
    total_inserted_samples: int
    session_quality_percent: float | None
    channel_quality_percent: dict[str, float | None]


class InterpolationTransformer(ChannelTransformer):
    REQUIRED_CHANNELS = ()
    _NANOSECONDS_PER_SECOND = 1_000_000_000

    def __init__(self, *, max_gap_seconds: float, frequency_hz: float) -> None:
        if max_gap_seconds <= 0:
            raise ValueError("max_gap_seconds must be greater than 0")
        if frequency_hz <= 0:
            raise ValueError("frequency_hz must be greater than 0")

        self.max_gap_seconds = float(max_gap_seconds)
        self.frequency_hz = float(frequency_hz)
        self.step_seconds = 1.0 / self.frequency_hz
        self.max_gap_ns = int(round(self.max_gap_seconds * self._NANOSECONDS_PER_SECOND))
        self.step_ns = int(round(self.step_seconds * self._NANOSECONDS_PER_SECOND))
        self._channel_stats: dict[str, _InterpolationStats] = {}
        self._excluded_spans_ns: list[tuple[int, int]] = []

    @property
    def summary(self) -> InterpolationSummary:
        total_inserted_samples = sum(
            stats.inserted_samples for stats in self._channel_stats.values()
        )
        target_frequency_duration_ns = sum(
            stats.target_frequency_duration_ns for stats in self._channel_stats.values()
        )
        total_duration_ns = sum(
            stats.total_duration_ns for stats in self._channel_stats.values()
        )
        session_quality_percent = (
            100.0 * target_frequency_duration_ns / total_duration_ns
            if total_duration_ns > 0
            else None
        )

        return InterpolationSummary(
            frequency_hz=self.frequency_hz,
            total_inserted_samples=total_inserted_samples,
            session_quality_percent=session_quality_percent,
            channel_quality_percent={
                channel_name: stats.quality_percent
                for channel_name, stats in self._channel_stats.items()
            },
        )

    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        self._channel_stats = {}
        self._excluded_spans_ns = self._extract_excluded_spans(session)

        for channel_name, channel in session.channels.items():
            self._validate_timestamps(channel_name, channel.timestamps)
            stats = _InterpolationStats()

            if channel.timestamps.size < 2:
                self._channel_stats[channel_name] = stats
                continue

            timestamps, values, stats = self._interpolate_channel(
                channel.timestamps,
                channel.values,
            )
            channel.timestamps = timestamps
            channel.values = values
            self._channel_stats[channel_name] = stats

        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        records: list[ProvenanceRecord] = []

        for channel_name in session.channels:
            stats = self._channel_stats[channel_name]
            inserted_samples = stats.inserted_samples
            operation = "interpolate" if inserted_samples > 0 else "noop"
            description = (
                f"Inserted {inserted_samples} interpolated samples"
                if inserted_samples > 0
                else "No interpolation applied"
            )
            records.append(
                self.make_provenance_record(
                    channel_name,
                    inputs=[channel_name],
                    config={
                        "frequency_hz": self.frequency_hz,
                        "step_seconds": self.step_seconds,
                        "max_gap_seconds": self.max_gap_seconds,
                    },
                    changes=[
                        {
                            "field": "timestamps_and_values",
                            "operation": operation,
                            "inserted_samples": inserted_samples,
                            "interpolated_gaps": stats.interpolated_gaps,
                            "skipped_gaps": stats.skipped_gaps,
                            "quality_percent": stats.quality_percent,
                            "description": description,
                        }
                    ],
                )
            )

        return records

    def print_summary(self) -> None:
        summary = self.summary
        quality = (
            f"{summary.session_quality_percent:.1f}%"
            if summary.session_quality_percent is not None
            else "n/a"
        )
        print(
            "interpolation: "
            f"inserted {summary.total_inserted_samples} points, "
            f"session quality at {summary.frequency_hz:g} Hz: {quality}"
        )
        print(
            "interpolation channel quality: "
            f"{self._format_channel_quality(summary.channel_quality_percent)}"
        )

    def _validate_timestamps(
        self, channel_name: str, timestamps: np.ndarray
    ) -> None:
        if timestamps.size < 2:
            return

        timestamps_ns = self._timestamps_to_ns(timestamps)
        if np.any(np.diff(timestamps_ns) <= 0):
            raise ValueError(
                f"Channel '{channel_name}' timestamps must be strictly increasing "
                "for interpolation"
            )

    def _interpolate_channel(
        self, timestamps: np.ndarray, values: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, _InterpolationStats]:
        stats = _InterpolationStats()
        timestamps_ns = self._timestamps_to_ns(timestamps)
        timestamp_segments: list[np.ndarray] = [timestamps_ns[:1]]
        value_segments: list[np.ndarray] = [values[:1]]

        for index in range(timestamps.size - 1):
            start_time_ns = int(timestamps_ns[index])
            end_time_ns = int(timestamps_ns[index + 1])
            gap_ns = end_time_ns - start_time_ns

            insert_timestamps_ns = self._build_insert_timestamps_ns(
                start_time_ns, gap_ns
            )
            if insert_timestamps_ns.size > 0:
                insert_values = self._interpolate_values(
                    start_time_ns,
                    end_time_ns,
                    values[index],
                    values[index + 1],
                    insert_timestamps_ns,
                )
                timestamp_segments.append(insert_timestamps_ns)
                value_segments.append(insert_values)
                stats.inserted_samples += int(insert_timestamps_ns.size)
                stats.interpolated_gaps += 1
            elif gap_ns > self.max_gap_ns:
                stats.skipped_gaps += 1

            timestamp_segments.append(timestamps_ns[index + 1 : index + 2])
            value_segments.append(values[index + 1 : index + 2])

        interpolated_timestamps_ns = np.concatenate(timestamp_segments)
        self._record_quality(stats, interpolated_timestamps_ns)
        return (
            self._timestamps_from_ns(interpolated_timestamps_ns, timestamps),
            np.concatenate(value_segments),
            stats,
        )

    def _build_insert_timestamps_ns(
        self, start_time_ns: int, gap_ns: int
    ) -> np.ndarray:
        if gap_ns > self.max_gap_ns or gap_ns <= self.step_ns:
            return np.array([], dtype=np.int64)

        insert_offsets = np.arange(
            self.step_ns,
            gap_ns,
            self.step_ns,
            dtype=np.int64,
        )
        candidates = start_time_ns + insert_offsets

        for excluded_start_ns, excluded_end_ns in self._excluded_spans_ns:
            candidates = candidates[
                (candidates < excluded_start_ns)
                | (candidates > excluded_end_ns)
            ]

        return candidates

    def _interpolate_values(
        self,
        start_time_ns: int,
        end_time_ns: int,
        start_value: np.ndarray,
        end_value: np.ndarray,
        insert_timestamps_ns: np.ndarray,
    ) -> np.ndarray:
        weights = (insert_timestamps_ns - start_time_ns) / (end_time_ns - start_time_ns)

        if start_value.ndim == 0:
            return start_value + (end_value - start_value) * weights

        reshaped_weights = weights.reshape((-1,) + (1,) * start_value.ndim)
        return start_value + (end_value - start_value) * reshaped_weights

    def _record_quality(
        self, stats: _InterpolationStats, timestamps_ns: np.ndarray
    ) -> None:
        if timestamps_ns.size < 2:
            return

        raw_gaps_ns = np.diff(timestamps_ns)
        adjusted_gaps_ns = self._apply_excluded_spans(
            timestamps_ns=timestamps_ns,
            gaps_ns=raw_gaps_ns,
        )
        stats.total_duration_ns = int(np.sum(adjusted_gaps_ns))
        stats.target_frequency_duration_ns = int(
            np.sum(adjusted_gaps_ns[adjusted_gaps_ns <= self.step_ns])
        )

    def _extract_excluded_spans(
        self, session: CanonicalSession
    ) -> list[tuple[int, int]]:
        spans_ns: list[tuple[int, int]] = []

        for record in session.provenance:
            excluded_spans = record.config.get("excluded_spans_ns")
            if not isinstance(excluded_spans, list):
                continue

            for span in excluded_spans:
                if not isinstance(span, dict):
                    continue

                start_ns = span.get("start_ns")
                end_ns = span.get("end_ns")
                if not isinstance(start_ns, int) or not isinstance(end_ns, int):
                    continue
                if end_ns < start_ns:
                    continue

                spans_ns.append((start_ns, end_ns))

        return self._merge_spans(spans_ns)

    def _merge_spans(self, spans_ns: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not spans_ns:
            return []

        merged_spans: list[tuple[int, int]] = []
        for start_ns, end_ns in sorted(spans_ns):
            if not merged_spans or start_ns > merged_spans[-1][1]:
                merged_spans.append((start_ns, end_ns))
                continue

            merged_start_ns, merged_end_ns = merged_spans[-1]
            merged_spans[-1] = (merged_start_ns, max(merged_end_ns, end_ns))

        return merged_spans

    def _apply_excluded_spans(
        self, timestamps_ns: np.ndarray, gaps_ns: np.ndarray
    ) -> np.ndarray:
        if gaps_ns.size == 0 or not self._excluded_spans_ns:
            return gaps_ns

        adjusted_gaps_ns = gaps_ns.astype(np.int64, copy=True)
        interval_start_ns = timestamps_ns[:-1]
        interval_end_ns = timestamps_ns[1:]

        for excluded_start_ns, excluded_end_ns in self._excluded_spans_ns:
            # Expand the excluded window by one target step on the right so that
            # adjacent kept samples become neighbors on the collapsed timeline.
            overlap_start_ns = np.maximum(interval_start_ns, excluded_start_ns)
            overlap_end_ns = np.minimum(interval_end_ns, excluded_end_ns + self.step_ns)
            overlap_ns = np.maximum(0, overlap_end_ns - overlap_start_ns)
            adjusted_gaps_ns -= overlap_ns.astype(np.int64)

        return np.maximum(adjusted_gaps_ns, 0)

    def _timestamps_to_ns(self, timestamps: np.ndarray) -> np.ndarray:
        if timestamps.size == 0:
            return np.array([], dtype=np.int64)

        if np.issubdtype(timestamps.dtype, np.datetime64):
            return timestamps.astype("datetime64[ns]").astype(np.int64)

        if np.issubdtype(timestamps.dtype, np.number):
            return np.rint(
                timestamps.astype(np.float64) * self._NANOSECONDS_PER_SECOND
            ).astype(np.int64)

        return np.array(
            [self._timestamp_value_to_ns(timestamp) for timestamp in timestamps],
            dtype=np.int64,
        )

    def _timestamp_value_to_ns(self, value: Any) -> int:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return int(np.datetime64(value, "ns").astype(np.int64))

        if isinstance(value, np.datetime64):
            return int(value.astype("datetime64[ns]").astype(np.int64))

        if isinstance(value, (int, float, np.integer, np.floating)):
            return int(round(float(value) * self._NANOSECONDS_PER_SECOND))

        raise TypeError(
            "Unsupported timestamp value type for interpolation: "
            f"{type(value).__name__}"
        )

    def _timestamps_from_ns(
        self, timestamps_ns: np.ndarray, original_timestamps: np.ndarray
    ) -> np.ndarray:
        if np.issubdtype(original_timestamps.dtype, np.datetime64):
            return timestamps_ns.astype("datetime64[ns]")

        if np.issubdtype(original_timestamps.dtype, np.number):
            return timestamps_ns.astype(np.float64) / self._NANOSECONDS_PER_SECOND

        first_timestamp = original_timestamps[0]
        if isinstance(first_timestamp, datetime):
            interpolated_datetimes: list[datetime] = []
            for timestamp_ns in timestamps_ns:
                timestamp = datetime.fromtimestamp(
                    int(timestamp_ns) / self._NANOSECONDS_PER_SECOND,
                    tz=timezone.utc,
                )
                if first_timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=None)
                else:
                    timestamp = timestamp.astimezone(first_timestamp.tzinfo)

                interpolated_datetimes.append(timestamp)

            return np.array(
                interpolated_datetimes,
                dtype=object,
            )

        return timestamps_ns.astype("datetime64[ns]")

    def _format_channel_quality(
        self, channel_quality_percent: dict[str, float | None]
    ) -> str:
        preferred_channels = [
            ChannelNames.LATITUDE.value,
            ChannelNames.LONGITUDE.value,
        ]
        ordered_channels = [
            channel_name
            for channel_name in preferred_channels
            if channel_name in channel_quality_percent
        ]
        ordered_channels.extend(
            sorted(
                channel_name
                for channel_name in channel_quality_percent
                if channel_name not in preferred_channels
            )
        )

        formatted_channels = []
        for channel_name in ordered_channels:
            quality = channel_quality_percent[channel_name]
            formatted_quality = f"{quality:.1f}%" if quality is not None else "n/a"
            formatted_channels.append(f"{channel_name}={formatted_quality}")

        return ", ".join(formatted_channels)
