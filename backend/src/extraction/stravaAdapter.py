from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np

from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.extraction.metaAdapter import MetaAdapter
from src.extraction.sourceAdapter import SourceAdapter
from src.extraction.utils import build_session_id
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Metric,
    SessionMetadata,
)
from src.models.job import Job


class StravaAdapter(SourceAdapter):
    """Parses Strava FIT sessions and sidecar metadata into a canonical session."""

    FIT_SOURCE = "strava_fit"
    SEMICIRCLES_TO_DEGREES = 180.0 / (2**31)

    def __init__(self):
        self.supported_session_files = [".fit"]

    def can_handle(self, job: Job) -> bool:
        return Path(job.session_path).suffix.lower() in self.supported_session_files

    def parse_job(self, job: Job) -> CanonicalSession:
        fitdecode = self._load_fitdecode()

        lats: list[float] = []
        lats_ts: list[np.datetime64] = []
        lons: list[float] = []
        lons_ts: list[np.datetime64] = []
        heart_rates: list[int] = []
        heart_rates_ts: list[np.datetime64] = []
        speeds: list[float] = []
        speeds_ts: list[np.datetime64] = []

        with fitdecode.FitReader(job.session_path) as fit:
            for frame in fit:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name != "record":
                    continue

                timestamp = self._parse_fit_timestamp(
                    frame.get_value("timestamp", fallback=None)
                )
                if timestamp is None:
                    continue

                lat = frame.get_value("position_lat", fallback=None)
                lon = frame.get_value("position_long", fallback=None)
                heart_rate = frame.get_value("heart_rate", fallback=None)
                speed = frame.get_value("speed", fallback=None)

                if lat is not None and lon is not None:
                    lats.append(self._semicircles_to_degrees(lat))
                    lats_ts.append(timestamp)
                    lons.append(self._semicircles_to_degrees(lon))
                    lons_ts.append(timestamp)

                if heart_rate is not None:
                    heart_rates.append(int(heart_rate))
                    heart_rates_ts.append(timestamp)

                if speed is not None:
                    speeds.append(float(speed))
                    speeds_ts.append(timestamp)

        lats_ts_array, lats_array = self._normalize_channel_samples(lats_ts, lats, float)
        lons_ts_array, lons_array = self._normalize_channel_samples(lons_ts, lons, float)
        heart_rates_ts_array, heart_rates_array = self._normalize_channel_samples(
            heart_rates_ts, heart_rates, int
        )
        speeds_ts_array, speeds_array = self._normalize_channel_samples(
            speeds_ts, speeds, float
        )

        channels = {
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=lats_ts_array,
                values=lats_array,
                unit="deg",
                source=self.FIT_SOURCE,
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=lons_ts_array,
                values=lons_array,
                unit="deg",
                source=self.FIT_SOURCE,
            ),
        }

        if heart_rates_array.size > 0:
            channels[ChannelNames.HEART_RATE.value] = Channel(
                name=ChannelNames.HEART_RATE.value,
                timestamps=heart_rates_ts_array,
                values=heart_rates_array,
                unit="bpm",
                source=self.FIT_SOURCE,
            )

        if speeds_array.size > 0:
            channels[ChannelNames.SOG.value] = Channel(
                name=ChannelNames.SOG.value,
                timestamps=speeds_ts_array,
                values=speeds_array,
                unit="m/s",
                source=self.FIT_SOURCE,
            )

        meta_adapter = MetaAdapter(job.meta_path)
        manual_wind_speed = meta_adapter.get_manual_wind_amt()
        manual_wind_gust = meta_adapter.get_manual_wind_gust()
        manual_wind_direction = meta_adapter.get_manual_wind_dir()
        manual_wave_height = meta_adapter.get_manual_wave_height()
        ride_height_offset_cm = meta_adapter.get_ride_height_offset_cm()

        inferred_start_at = lats_ts_array[0] if lats_ts_array.size > 0 else None
        inferred_end_at = lats_ts_array[-1] if lats_ts_array.size > 0 else None

        metadata = SessionMetadata(
            session_id=build_session_id(job),
            session_name=meta_adapter.get_session_name(),
            source_type="strava",
            boat_id=meta_adapter.get_boat_name(),
            start_at=meta_adapter.get_start_ts() or inferred_start_at,
            end_at=meta_adapter.get_end_ts() or inferred_end_at,
            location=meta_adapter.get_location(),
            notes=meta_adapter.get_notes(),
            extras={
                "exportedAt": meta_adapter.get_exported_at(),
                **(
                    {"rideHeightOffsetCm": ride_height_offset_cm}
                    if ride_height_offset_cm is not None
                    else {}
                ),
            },
        )

        metrics: dict[str, Metric] = {}
        if manual_wind_speed is not None:
            metrics[MetricNames.MANUAL_WIND_SPEED.value] = Metric(
                name=MetricNames.MANUAL_WIND_SPEED.value,
                value=manual_wind_speed,
                unit="kn",
                source=MetricNames.MANUAL_WIND_SOURCE.value,
                metadata={"input_field": "windSpeed"},
            )
        if manual_wind_gust is not None:
            metrics[MetricNames.MANUAL_WIND_GUST.value] = Metric(
                name=MetricNames.MANUAL_WIND_GUST.value,
                value=manual_wind_gust,
                unit="kn",
                source=MetricNames.MANUAL_WIND_SOURCE.value,
                metadata={"input_field": "windGust"},
            )
        if manual_wind_direction is not None:
            metrics[MetricNames.MANUAL_WIND_DIRECTION.value] = Metric(
                name=MetricNames.MANUAL_WIND_DIRECTION.value,
                value=float(manual_wind_direction),
                unit="deg",
                source=MetricNames.MANUAL_WIND_SOURCE.value,
                metadata={"input_field": "windDirection"},
            )
        if manual_wave_height is not None:
            metrics[MetricNames.MANUAL_WAVE_HEIGHT.value] = Metric(
                name=MetricNames.MANUAL_WAVE_HEIGHT.value,
                value=manual_wave_height,
                unit="m",
                source=MetricNames.MANUAL_WIND_SOURCE.value,
                metadata={"input_field": "waveHeightM"},
            )

        return CanonicalSession(
            metadata=metadata,
            channels=channels,
            metrics=metrics,
            races=meta_adapter.get_races(),
        )

    def _load_fitdecode(self) -> Any:
        try:
            return import_module("fitdecode")
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "StravaAdapter requires the 'fitdecode' package to parse .fit files."
            ) from exc

    def _parse_fit_timestamp(self, value: Any) -> np.datetime64 | None:
        if not isinstance(value, datetime):
            return None

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)

        return np.datetime64(value.replace(tzinfo=None), "ns")

    def _semicircles_to_degrees(self, value: Any) -> float:
        return float(value) * self.SEMICIRCLES_TO_DEGREES

    def _normalize_channel_samples(
        self,
        timestamps: list[np.datetime64],
        values: list[Any],
        value_dtype: type,
    ) -> tuple[np.ndarray, np.ndarray]:
        if not timestamps:
            return (
                np.array([], dtype="datetime64[ms]"),
                np.array([], dtype=value_dtype),
            )

        timestamps_array = np.array(timestamps, dtype="datetime64[ms]")
        values_array = np.array(values, dtype=value_dtype)

        order = np.argsort(timestamps_array, kind="stable")
        sorted_timestamps = timestamps_array[order]
        sorted_values = values_array[order]

        dedupe_mask = np.ones(sorted_timestamps.shape[0], dtype=bool)
        dedupe_mask[:-1] = sorted_timestamps[:-1] != sorted_timestamps[1:]

        return sorted_timestamps[dedupe_mask], sorted_values[dedupe_mask]
