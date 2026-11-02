from __future__ import annotations

import csv
from datetime import datetime, timezone

import numpy as np

from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.extraction.csvSourceAdapter import CsvSourceAdapter
from src.extraction.metaAdapter import MetaAdapter
from src.extraction.utils import build_session_id, parse_datetime
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Metric,
    SessionMetadata,
)
from src.models.job import Job


class SailmonAdapter(CsvSourceAdapter):
    """Parses Sailmon CSV sessions and sidecar metadata into a canonical session."""

    TIME_HEADER = "time"
    SERVER_TIME_HEADER = "servertime"
    LATITUDE_HEADER = "latitude"
    LONGITUDE_HEADER = "longitude"
    HEADING_HEADER = "HDT - Heading True"
    SPEED_HEADER = "SOG - Speed over Ground"
    COURSE_HEADER = "COG - Course over Ground"
    TRUE_WIND_ANGLE_HEADER = "TWA - True Wind Angle"
    TRUE_WIND_DIRECTION_HEADER = "TWD - True Wind Direction"
    HEEL_HEADER = "Heel"
    TRIM_HEADER = "Trim Fore / Aft"
    VMG_HEADER = "VMG - Velocity Made Good"
    TIME_TO_GUN_HEADER = "Time to Gun"
    GPS_SATELLITES_HEADER = "GPS Satellites"
    GPS_HORIZONTAL_ACCURACY_HEADER = "GPS HAcc"
    BATTERY_CHARGE_HEADER = "Battery Charge"
    BATTERY_1_VOLTAGE_HEADER = "Battery 1 Voltage"
    BATTERY_1_CURRENT_HEADER = "Battery 1 Current"
    BATTERY_1_TEMPERATURE_HEADER = "Battery 1 Temperature"

    SAILMON_SOURCE = "sailmon_csv"
    LOCATION_TIMEZONES = {
        "langedrag": "Europe/Stockholm",
        "gothenburg": "Europe/Stockholm",
        "goteborg": "Europe/Stockholm",
        "goeteborg": "Europe/Stockholm",
        "göteborg": "Europe/Stockholm",
        "malcesine": "Europe/Rome",
    }

    @property
    def required_headers(self) -> set[str]:
        return {
            self.TIME_HEADER,
            self.SERVER_TIME_HEADER,
            self.LATITUDE_HEADER,
            self.LONGITUDE_HEADER,
            self.HEADING_HEADER,
            self.SPEED_HEADER,
            self.COURSE_HEADER,
            self.HEEL_HEADER,
            self.TRIM_HEADER,
            self.GPS_SATELLITES_HEADER,
            self.GPS_HORIZONTAL_ACCURACY_HEADER,
            self.BATTERY_CHARGE_HEADER,
            self.BATTERY_1_VOLTAGE_HEADER,
            self.BATTERY_1_CURRENT_HEADER,
            self.BATTERY_1_TEMPERATURE_HEADER,
        }

    def parse_job(self, job: Job) -> CanonicalSession:
        meta_adapter = MetaAdapter(job.meta_path)
        resolved_timezone = self._resolve_timezone_name(
            meta_adapter.get_timezone(),
            meta_adapter.get_location(),
        )

        timestamps: list[np.datetime64] = []
        latitudes: list[float] = []
        longitudes: list[float] = []
        optional_channel_samples: dict[str, dict[str, object]] = {
            ChannelNames.HEADING.value: {
                "header": self.HEADING_HEADER,
                "unit": "deg",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.SOG.value: {
                "header": self.SPEED_HEADER,
                "unit": "m/s",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.COG.value: {
                "header": self.COURSE_HEADER,
                "unit": "deg",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.TWA.value: {
                "header": self.TRUE_WIND_ANGLE_HEADER,
                "unit": "deg",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.TWD.value: {
                "header": self.TRUE_WIND_DIRECTION_HEADER,
                "unit": "deg",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.HEEL.value: {
                "header": self.HEEL_HEADER,
                "unit": "deg",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.PITCH.value: {
                "header": self.TRIM_HEADER,
                "unit": "deg",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.VMG.value: {
                "header": self.VMG_HEADER,
                "unit": "kn",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.TIME_TO_GUN.value: {
                "header": self.TIME_TO_GUN_HEADER,
                "unit": "s",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.GPS_ACCURACY.value: {
                "header": self.GPS_HORIZONTAL_ACCURACY_HEADER,
                "unit": "dop",
                "timestamps": [],
                "values": [],
            },
            ChannelNames.GPS_SATELLITES.value: {
                "header": self.GPS_SATELLITES_HEADER,
                "unit": "amt",
                "timestamps": [],
                "values": [],
            },
        }

        with open(job.session_path, "r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                timestamp = self._parse_row_timestamp(row, resolved_timezone)
                latitude = self._parse_float(row.get(self.LATITUDE_HEADER))
                longitude = self._parse_float(row.get(self.LONGITUDE_HEADER))

                if timestamp is None or latitude is None or longitude is None:
                    continue

                timestamps.append(timestamp)
                latitudes.append(latitude)
                longitudes.append(longitude)

                for sample in optional_channel_samples.values():
                    value = self._parse_float(row.get(sample["header"]))
                    if value is None:
                        continue
                    sample["timestamps"].append(timestamp)
                    sample["values"].append(value)

        lat_timestamps, lat_values = self._normalize_channel_samples(
            timestamps, latitudes, float
        )
        lon_timestamps, lon_values = self._normalize_channel_samples(
            timestamps, longitudes, float
        )

        channels = {
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=lat_timestamps,
                values=lat_values,
                unit="deg",
                source=self.SAILMON_SOURCE,
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=lon_timestamps,
                values=lon_values,
                unit="deg",
                source=self.SAILMON_SOURCE,
            ),
        }

        for channel_name, sample in optional_channel_samples.items():
            channel_timestamps, channel_values = self._normalize_channel_samples(
                sample["timestamps"], sample["values"], float
            )
            if channel_values.size == 0:
                continue

            channels[channel_name] = Channel(
                name=channel_name,
                timestamps=channel_timestamps,
                values=channel_values,
                unit=sample["unit"],
                source=self.SAILMON_SOURCE,
            )

        manual_wind_speed = meta_adapter.get_manual_wind_amt()
        manual_wind_gust = meta_adapter.get_manual_wind_gust()
        manual_wind_direction = meta_adapter.get_manual_wind_dir()
        manual_wave_height = meta_adapter.get_manual_wave_height()
        ride_height_offset_cm = meta_adapter.get_ride_height_offset_cm()

        inferred_start_at = lat_timestamps[0] if lat_timestamps.size > 0 else None
        inferred_end_at = lat_timestamps[-1] if lat_timestamps.size > 0 else None

        metadata = SessionMetadata(
            session_id=build_session_id(job),
            session_name=meta_adapter.get_session_name(),
            source_type="sailmon",
            boat_id=meta_adapter.get_boat_name(),
            start_at=meta_adapter.get_start_ts() or inferred_start_at,
            end_at=meta_adapter.get_end_ts() or inferred_end_at,
            timezone=resolved_timezone,
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

    def _parse_float(self, value: str | None) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    def _parse_row_timestamp(
        self,
        row: dict[str, str | None],
        resolved_timezone: str | None,
    ) -> np.datetime64 | None:
        primary_value = row.get(self.TIME_HEADER)
        server_value = row.get(self.SERVER_TIME_HEADER)

        parsed_primary = self._parse_timestamp_value(primary_value, resolved_timezone)
        if parsed_primary is not None:
            return parsed_primary

        return self._parse_timestamp_value(server_value, resolved_timezone)

    def _parse_timestamp_value(
        self,
        value: str | None,
        resolved_timezone: str | None,
    ) -> np.datetime64 | None:
        if value in (None, ""):
            return None

        try:
            return parse_datetime(value)
        except ValueError as exc:
            if "Timezone required in datetime string" not in str(exc):
                raise

        parsed_value = datetime.fromisoformat(value)
        if parsed_value.tzinfo is not None:
            parsed_value = parsed_value.astimezone(timezone.utc).replace(tzinfo=None)

        return np.datetime64(parsed_value, "ns")

    def _resolve_timezone_name(
        self,
        explicit_timezone: str | None,
        location: str | None,
    ) -> str | None:
        if explicit_timezone:
            return explicit_timezone
        if not location:
            return None
        return self.LOCATION_TIMEZONES.get(location.strip().casefold())

    def _normalize_channel_samples(
        self,
        timestamps: list[np.datetime64],
        values: list[float],
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
