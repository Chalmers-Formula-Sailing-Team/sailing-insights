from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.constants.ChannelNames import ChannelNames
from src.models.canonicalSession import CanonicalSession, ProvenanceRecord
from src.transformer.channelTransformer import ChannelTransformer


class ExclusionZoneTransformer(ChannelTransformer):
    """
    Base class for coordinate-based exclusion zones.

    A concrete zone implementation provides a polygon in (lat, lon) points.
    The transformer then:
    1) finds lat/lon samples inside that polygon
    2) converts those sample runs into excluded time spans
    3) removes samples from every channel whose timestamp is inside
       any excluded span.
    """

    REQUIRED_CHANNELS = (
        ChannelNames.LATITUDE.value,
        ChannelNames.LONGITUDE.value,
    )
    _NANOSECONDS_PER_SECOND = 1_000_000_000
    _FLOAT_EPSILON = 1e-12

    def __init__(self) -> None:
        self._excluded_spans_ns: list[tuple[int, int]] = []
        self._removed_samples_per_channel: dict[str, int] = {}

    @property
    @abstractmethod
    def zone_name(self) -> str:
        """Human-readable zone name (for example: 'Langedrag')."""

    @property
    @abstractmethod
    def polygon_coordinates(self) -> Sequence[tuple[float, float]]:
        """Polygon vertices as (lat, lon) tuples."""

    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        self._excluded_spans_ns = []
        self._removed_samples_per_channel = {}

        polygon = self._build_polygon(self.polygon_coordinates)
        lat_channel = session.get_channel(ChannelNames.LATITUDE.value)
        lon_channel = session.get_channel(ChannelNames.LONGITUDE.value)

        if len(lat_channel.timestamps) != len(lon_channel.timestamps):
            raise ValueError(
                f"{ChannelNames.LATITUDE.value} and "
                f"{ChannelNames.LONGITUDE.value} channels must have equal "
                "timestamp counts"
            )

        if not np.array_equal(lat_channel.timestamps, lon_channel.timestamps):
            raise ValueError(
                f"{ChannelNames.LATITUDE.value} and "
                f"{ChannelNames.LONGITUDE.value} channels must share identical timestamps "
                "for zone exclusion"
            )

        if len(lat_channel.timestamps) > 0:
            lat_timestamps_ns = self._timestamps_to_ns(lat_channel.timestamps)
            inside_mask = self._points_in_polygon(
                lat_values=np.asarray(lat_channel.values, dtype=float),
                lon_values=np.asarray(lon_channel.values, dtype=float),
                polygon=polygon,
            )
            self._excluded_spans_ns = self._mask_to_time_spans(
                timestamps_ns=lat_timestamps_ns, true_mask=inside_mask
            )

        for channel_name, channel in session.channels.items():
            channel_timestamps_ns = self._timestamps_to_ns(channel.timestamps)
            excluded_mask = self._timestamps_within_spans(
                timestamps_ns=channel_timestamps_ns,
                spans_ns=self._excluded_spans_ns,
            )
            removed_count = int(np.count_nonzero(excluded_mask))
            self._removed_samples_per_channel[channel_name] = removed_count

            if removed_count > 0:
                keep_mask = ~excluded_mask
                channel.timestamps = channel.timestamps[keep_mask]
                channel.values = channel.values[keep_mask]

        return session

    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        records: list[ProvenanceRecord] = []

        for channel_name in session.channels:
            removed_count = self._removed_samples_per_channel.get(channel_name, 0)
            operation = "remove_by_time_span" if removed_count else "noop"
            description = (
                f"Removed {removed_count} sample(s) inside exclusion zone '{self.zone_name}'"
                if removed_count
                else f"No samples were inside exclusion zone '{self.zone_name}'"
            )

            inputs = sorted(
                {
                    ChannelNames.LATITUDE.value,
                    ChannelNames.LONGITUDE.value,
                    channel_name,
                }
            )
            records.append(
                self.make_provenance_record(
                    channel_name,
                    inputs=inputs,
                    config={
                        "zone_name": self.zone_name,
                        "excluded_spans_ns": [
                            {"start_ns": start_ns, "end_ns": end_ns}
                            for start_ns, end_ns in self._excluded_spans_ns
                        ],
                    },
                    changes=[
                        {
                            "field": "values",
                            "operation": operation,
                            "count": removed_count,
                            "description": description,
                        }
                    ],
                )
            )

        return records

    def print_summary(self) -> None:
        total_removed_samples = sum(self._removed_samples_per_channel.values())
        affected_channels = sum(
            1
            for removed_count in self._removed_samples_per_channel.values()
            if removed_count > 0
        )
        print(
            f"exclusion zone '{self.zone_name}': "
            f"removed {total_removed_samples} sample(s) across "
            f"{affected_channels} channel(s) in {len(self._excluded_spans_ns)} time windows"
        )

    def _build_polygon(self, coordinates: Sequence[tuple[float, float]]) -> np.ndarray:
        polygon = np.asarray(coordinates, dtype=float)
        if polygon.ndim != 2 or polygon.shape[1] != 2:
            raise ValueError(
                "polygon_coordinates must be a sequence of (lat, lon) pairs"
            )

        # Support explicitly closed rings (first point repeated as last point).
        # The point-in-polygon loop already closes the polygon implicitly.
        if polygon.shape[0] >= 2 and np.allclose(polygon[0], polygon[-1]):
            polygon = polygon[:-1]

        if polygon.shape[0] < 3:
            raise ValueError("polygon_coordinates must contain at least 3 points")
        return polygon

    def _timestamps_to_ns(self, timestamps: np.ndarray) -> np.ndarray:
        if len(timestamps) == 0:
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
            "Unsupported timestamp value type for exclusion zone filtering: "
            f"{type(value).__name__}"
        )

    def _points_in_polygon(
        self, lat_values: np.ndarray, lon_values: np.ndarray, polygon: np.ndarray
    ) -> np.ndarray:
        inside = np.zeros(lat_values.shape[0], dtype=bool)

        polygon_lat = polygon[:, 0]
        polygon_lon = polygon[:, 1]
        point_count = polygon.shape[0]

        for point_idx, (lat, lon) in enumerate(
            zip(lat_values, lon_values, strict=True)
        ):
            contains = False

            for vertex_idx in range(point_count):
                next_idx = (vertex_idx + 1) % point_count
                lat_a = float(polygon_lat[vertex_idx])
                lon_a = float(polygon_lon[vertex_idx])
                lat_b = float(polygon_lat[next_idx])
                lon_b = float(polygon_lon[next_idx])

                if self._point_on_segment(lat, lon, lat_a, lon_a, lat_b, lon_b):
                    contains = True
                    break

                crosses_edge = (lon_a > lon) != (lon_b > lon)
                if not crosses_edge:
                    continue

                intersect_lat = lat_a + (lon - lon_a) * (lat_b - lat_a) / (
                    lon_b - lon_a
                )
                if lat < intersect_lat:
                    contains = not contains

            inside[point_idx] = contains

        return inside

    def _point_on_segment(
        self,
        point_lat: float,
        point_lon: float,
        lat_a: float,
        lon_a: float,
        lat_b: float,
        lon_b: float,
    ) -> bool:
        cross = (point_lon - lon_a) * (lat_b - lat_a) - (point_lat - lat_a) * (
            lon_b - lon_a
        )
        if abs(cross) > self._FLOAT_EPSILON:
            return False

        dot = (point_lat - lat_a) * (lat_b - lat_a) + (point_lon - lon_a) * (
            lon_b - lon_a
        )
        if dot < -self._FLOAT_EPSILON:
            return False

        segment_length_sq = (lat_b - lat_a) ** 2 + (lon_b - lon_a) ** 2
        if segment_length_sq <= self._FLOAT_EPSILON:
            return (
                abs(point_lat - lat_a) <= self._FLOAT_EPSILON
                and abs(point_lon - lon_a) <= self._FLOAT_EPSILON
            )

        if dot - segment_length_sq > self._FLOAT_EPSILON:
            return False

        return True

    def _mask_to_time_spans(
        self, timestamps_ns: np.ndarray, true_mask: np.ndarray
    ) -> list[tuple[int, int]]:
        included_indices = np.flatnonzero(true_mask)
        if included_indices.size == 0:
            return []

        split_points = np.where(np.diff(included_indices) != 1)[0] + 1
        contiguous_groups = np.split(included_indices, split_points)

        return [
            (int(timestamps_ns[group[0]]), int(timestamps_ns[group[-1]]))
            for group in contiguous_groups
        ]

    def _timestamps_within_spans(
        self, timestamps_ns: np.ndarray, spans_ns: Sequence[tuple[int, int]]
    ) -> np.ndarray:
        if len(timestamps_ns) == 0 or not spans_ns:
            return np.zeros(timestamps_ns.shape[0], dtype=bool)

        mask = np.zeros(timestamps_ns.shape[0], dtype=bool)
        for start_ns, end_ns in spans_ns:
            mask |= (timestamps_ns >= start_ns) & (timestamps_ns <= end_ns)

        return mask
