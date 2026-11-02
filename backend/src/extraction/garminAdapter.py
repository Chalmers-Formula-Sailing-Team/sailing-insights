import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.extraction.metaAdapter import MetaAdapter
from src.extraction.sourceAdapter import SourceAdapter
from src.extraction.utils import build_session_id, parse_datetime
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Metric,
    SessionMetadata,
)
from src.models.job import Job


class GarminAdapter(SourceAdapter):
    """Parses Garmin TCX sessions and sidecar metadata into a canonical session."""

    TCX_SOURCE = "garmin_tcx"

    def __init__(self):
        self.supported_session_files = [".tcx"]

    def can_handle(self, job: Job) -> bool:
        return Path(job.session_path).suffix.lower() in self.supported_session_files

    def parse_job(self, job: Job) -> CanonicalSession:
        tree = ET.parse(job.session_path)
        root = tree.getroot()
        ns = {
            "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
            "ns3": "http://www.garmin.com/xmlschemas/ActivityExtension/v2",
        }

        lats: list[float] = []
        lats_ts: list[np.datetime64] = []
        lons: list[float] = []
        lons_ts: list[np.datetime64] = []
        heart_rates: list[int] = []
        heart_rates_ts: list[np.datetime64] = []
        speeds: list[float] = []
        speeds_ts: list[np.datetime64] = []

        for tp in root.findall(".//tcx:Trackpoint", ns):
            timestamp = tp.findtext("tcx:Time", default=None, namespaces=ns)
            lat = tp.findtext(
                "tcx:Position/tcx:LatitudeDegrees", default=None, namespaces=ns
            )
            lon = tp.findtext(
                "tcx:Position/tcx:LongitudeDegrees", default=None, namespaces=ns
            )
            heart_rate = tp.findtext(
                "tcx:HeartRateBpm/tcx:Value", default=None, namespaces=ns
            )
            speed = tp.findtext(
                "tcx:Extensions/ns3:TPX/ns3:Speed", default=None, namespaces=ns
            )

            parsed_timestamp = parse_datetime(timestamp)

            if parsed_timestamp is not None and lat is not None and lon is not None:
                lats.append(float(lat))
                lats_ts.append(parsed_timestamp)
                lons.append(float(lon))
                lons_ts.append(parsed_timestamp)

            if parsed_timestamp is not None and heart_rate is not None:
                heart_rates.append(int(heart_rate))
                heart_rates_ts.append(parsed_timestamp)

            if parsed_timestamp is not None and speed is not None:
                speeds.append(float(speed))
                speeds_ts.append(parsed_timestamp)

        lats_ts_array, lats_array = self._normalize_channel_samples(
            lats_ts, lats, float
        )
        lons_ts_array, lons_array = self._normalize_channel_samples(
            lons_ts, lons, float
        )
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
                source=self.TCX_SOURCE,
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=lons_ts_array,
                values=lons_array,
                unit="deg",
                source=self.TCX_SOURCE,
            ),
        }

        if heart_rates_array.size > 0:
            channels[ChannelNames.HEART_RATE.value] = Channel(
                name=ChannelNames.HEART_RATE.value,
                timestamps=heart_rates_ts_array,
                values=heart_rates_array,
                unit="bpm",
                source=self.TCX_SOURCE,
            )

        if speeds_array.size > 0:
            channels[ChannelNames.SOG.value] = Channel(
                name=ChannelNames.SOG.value,
                timestamps=speeds_ts_array,
                values=speeds_array,
                unit="m/s",
                source=self.TCX_SOURCE,
            )

        meta_adapter = MetaAdapter(job.meta_path)
        manual_wind_speed = meta_adapter.get_manual_wind_amt()
        manual_wind_gust = meta_adapter.get_manual_wind_gust()
        manual_wind_direction = meta_adapter.get_manual_wind_dir()
        manual_wave_height = meta_adapter.get_manual_wave_height()
        ride_height_offset_cm = meta_adapter.get_ride_height_offset_cm()

        metadata = SessionMetadata(
            session_id=build_session_id(job),
            session_name=meta_adapter.get_session_name(),
            source_type="garmin",
            boat_id=meta_adapter.get_boat_name(),
            start_at=meta_adapter.get_start_ts(),
            end_at=meta_adapter.get_end_ts(),
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

    def _normalize_channel_samples(
        self,
        timestamps: list[np.datetime64],
        values: list[float] | list[int],
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
