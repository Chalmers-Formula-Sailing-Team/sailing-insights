from __future__ import annotations

import csv
from dataclasses import dataclass

import numpy as np

from src.constants.ChannelNames import ChannelNames
from src.extraction.csvSourceAdapter import CsvSourceAdapter
from src.extraction.metaAdapter import MetaAdapter
from src.extraction.utils import build_session_id, parse_datetime
from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.models.job import Job


@dataclass(slots=True)
class _ChannelSpec:
    output_name: str
    unit: str | None


class ERHAdapter(CsvSourceAdapter):
    TIME_STRING_HEADER = "time_str"
    TIME_RELATIVE_HEADER = "time_rel_s"
    ESP_US_HEADER = "esp_us"
    HEIGHT_HEADER = "height_m"
    WAND_HEADER = "wand_raw"
    SERVO_HEADER = "servo_deg"
    CONTROL_TIMESTAMP_HEADER = "control_timestamp_ms"
    QUAT_I_HEADER = "quat_i"
    QUAT_J_HEADER = "quat_j"
    QUAT_K_HEADER = "quat_k"
    QUAT_REAL_HEADER = "quat_real"
    LINEAR_AX_HEADER = "lin_ax"
    LINEAR_AY_HEADER = "lin_ay"
    LINEAR_AZ_HEADER = "lin_az"
    EARTH_AX_HEADER = "earth_ax"
    EARTH_AY_HEADER = "earth_ay"
    EARTH_AZ_HEADER = "earth_az"
    EARTH_Z_ACC_HEADER = "earth_z_acc"
    IMU_TIMESTAMP_HEADER = "imu_timestamp_ms"
    SPEED_HEADER = "speed_knots"
    LATITUDE_HEADER = "latitude_deg"
    LONGITUDE_HEADER = "longitude_deg"
    COURSE_HEADER = "course_deg"
    MAX_REASONABLE_ABSOLUTE_COORDINATE = 100.0

    SOURCE_NAME = "ehr_csv"
    TARGET_SAMPLE_PERIOD = np.timedelta64(1, "s")

    @property
    def required_headers(self) -> set[str]:
        return {
            self.ESP_US_HEADER,
            self.HEIGHT_HEADER,
            self.WAND_HEADER,
            self.SERVO_HEADER,
        }

    @property
    def _channel_specs(self) -> dict[str, _ChannelSpec]:
        return {
            self.TIME_RELATIVE_HEADER: _ChannelSpec(self.TIME_RELATIVE_HEADER, "s"),
            self.ESP_US_HEADER: _ChannelSpec(self.ESP_US_HEADER, "us"),
            self.HEIGHT_HEADER: _ChannelSpec(self.HEIGHT_HEADER, "m"),
            self.WAND_HEADER: _ChannelSpec(self.WAND_HEADER, None),
            self.SERVO_HEADER: _ChannelSpec(self.SERVO_HEADER, "deg"),
            self.CONTROL_TIMESTAMP_HEADER: _ChannelSpec(
                self.CONTROL_TIMESTAMP_HEADER, "ms"
            ),
            self.QUAT_I_HEADER: _ChannelSpec(self.QUAT_I_HEADER, None),
            self.QUAT_J_HEADER: _ChannelSpec(self.QUAT_J_HEADER, None),
            self.QUAT_K_HEADER: _ChannelSpec(self.QUAT_K_HEADER, None),
            self.QUAT_REAL_HEADER: _ChannelSpec(self.QUAT_REAL_HEADER, None),
            self.LINEAR_AX_HEADER: _ChannelSpec(self.LINEAR_AX_HEADER, "m/s^2"),
            self.LINEAR_AY_HEADER: _ChannelSpec(self.LINEAR_AY_HEADER, "m/s^2"),
            self.LINEAR_AZ_HEADER: _ChannelSpec(self.LINEAR_AZ_HEADER, "m/s^2"),
            self.EARTH_AX_HEADER: _ChannelSpec(self.EARTH_AX_HEADER, "m/s^2"),
            self.EARTH_AY_HEADER: _ChannelSpec(self.EARTH_AY_HEADER, "m/s^2"),
            self.EARTH_AZ_HEADER: _ChannelSpec(self.EARTH_AZ_HEADER, "m/s^2"),
            self.EARTH_Z_ACC_HEADER: _ChannelSpec(self.EARTH_Z_ACC_HEADER, "m/s^2"),
            self.IMU_TIMESTAMP_HEADER: _ChannelSpec(self.IMU_TIMESTAMP_HEADER, "ms"),
            self.SPEED_HEADER: _ChannelSpec(ChannelNames.SOG.value, "kn"),
            self.COURSE_HEADER: _ChannelSpec(ChannelNames.COG.value, "deg"),
        }

    def parse_job(self, job: Job) -> CanonicalSession:
        meta_adapter = MetaAdapter(job.meta_path)
        ride_height_offset_cm = meta_adapter.get_ride_height_offset_cm()
        rows = self._load_rows(job, meta_adapter)
        downsampled_rows = self._downsample_rows(rows)

        channels = self._build_channels(downsampled_rows)

        lat_channel = channels[ChannelNames.LATITUDE.value]
        metadata = SessionMetadata(
            session_id=build_session_id(job),
            session_name=meta_adapter.get_session_name(),
            source_type="ehr",
            boat_id=meta_adapter.get_boat_name(),
            start_at=meta_adapter.get_start_ts()
            or (lat_channel.timestamps[0] if lat_channel.timestamps.size > 0 else None),
            end_at=meta_adapter.get_end_ts()
            or (
                lat_channel.timestamps[-1] if lat_channel.timestamps.size > 0 else None
            ),
            timezone=meta_adapter.get_timezone(),
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

        return CanonicalSession(
            metadata=metadata,
            channels=channels,
            metrics={},
            races=meta_adapter.get_races(),
        )

    def _load_rows(
        self, job: Job, meta_adapter: MetaAdapter
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []

        with open(job.session_path, "r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file, delimiter=";")
            self._validate_required_fields(reader.fieldnames or [])

            for row in reader:
                timestamp = self._parse_row_timestamp(row, meta_adapter)
                latitude = self._sanitize_coordinate(
                    self._parse_float(row.get(self.LATITUDE_HEADER))
                )
                longitude = self._sanitize_coordinate(
                    self._parse_float(row.get(self.LONGITUDE_HEADER))
                )

                if timestamp is None:
                    continue

                parsed_row: dict[str, object] = {
                    "timestamp": timestamp,
                    ChannelNames.LATITUDE.value: latitude,
                    ChannelNames.LONGITUDE.value: longitude,
                }

                for input_name, spec in self._channel_specs.items():
                    value = self._parse_float(row.get(input_name))
                    if value is not None:
                        parsed_row[spec.output_name] = value

                rows.append(parsed_row)

        return rows

    def _build_channels(self, rows: list[dict[str, object]]) -> dict[str, Channel]:
        channel_samples: dict[str, list[tuple[np.datetime64, float]]] = {
            ChannelNames.LATITUDE.value: [],
            ChannelNames.LONGITUDE.value: [],
        }
        channel_units: dict[str, str | None] = {
            ChannelNames.LATITUDE.value: "deg",
            ChannelNames.LONGITUDE.value: "deg",
        }

        for spec in self._channel_specs.values():
            channel_samples.setdefault(spec.output_name, [])
            channel_units.setdefault(spec.output_name, spec.unit)

        for row in rows:
            timestamp = row["timestamp"]
            for channel_name, value in row.items():
                if channel_name == "timestamp":
                    continue
                channel_samples.setdefault(channel_name, []).append((timestamp, value))

        channels: dict[str, Channel] = {}
        for channel_name, samples in channel_samples.items():
            if not samples:
                continue

            timestamps = np.array(
                [timestamp for timestamp, _ in samples], dtype="datetime64[ms]"
            )
            values = np.array([value for _, value in samples], dtype=float)

            channels[channel_name] = Channel(
                name=channel_name,
                timestamps=timestamps,
                values=values,
                unit=channel_units[channel_name],
                source=self.SOURCE_NAME,
            )

        return channels

    def _downsample_rows(
        self, rows: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        if not rows:
            return rows

        sorted_rows = sorted(
            rows,
            key=lambda row: row["timestamp"].astype("datetime64[ns]").astype(np.int64),
        )

        downsampled_rows: list[dict[str, object]] = []
        current_bucket: np.datetime64 | None = None
        last_row_in_bucket: dict[str, object] | None = None

        for row in sorted_rows:
            timestamp = row["timestamp"].astype("datetime64[s]")
            if current_bucket is None or timestamp != current_bucket:
                if last_row_in_bucket is not None:
                    downsampled_rows.append(last_row_in_bucket)
                current_bucket = timestamp
            last_row_in_bucket = row

        if last_row_in_bucket is not None:
            downsampled_rows.append(last_row_in_bucket)

        return downsampled_rows

    def _validate_required_fields(self, fieldnames: list[str]) -> None:
        normalized = {field.strip() for field in fieldnames if field and field.strip()}
        missing_required = sorted(self.required_headers - normalized)
        if missing_required:
            raise ValueError(
                "EHR CSV is missing required headers: " + ", ".join(missing_required)
            )
        if self.LATITUDE_HEADER not in normalized:
            raise ValueError(f"EHR CSV requires '{self.LATITUDE_HEADER}'.")
        if self.LONGITUDE_HEADER not in normalized:
            raise ValueError(f"EHR CSV requires '{self.LONGITUDE_HEADER}'.")
        if (
            self.TIME_STRING_HEADER not in normalized
            and self.ESP_US_HEADER not in normalized
        ):
            raise ValueError(
                "EHR CSV requires either 'time_str' or 'esp_us' to build timestamps."
            )

    def _parse_row_timestamp(
        self,
        row: dict[str, str | None],
        meta_adapter: MetaAdapter,
    ) -> np.datetime64 | None:
        timestamp_value = row.get(self.TIME_STRING_HEADER)
        if timestamp_value not in (None, ""):
            return self._parse_time_string(timestamp_value, meta_adapter)

        esp_us = self._parse_float(row.get(self.ESP_US_HEADER))
        if esp_us is None:
            return None

        base_timestamp = meta_adapter.get_start_ts()
        if base_timestamp is None:
            base_timestamp = np.datetime64("1970-01-01T00:00:00.000", "ns")
        else:
            base_timestamp = base_timestamp.astype("datetime64[ns]")

        return base_timestamp + np.timedelta64(int(esp_us), "us")

    def _parse_time_string(
        self, value: str, meta_adapter: MetaAdapter
    ) -> np.datetime64 | None:
        hhmmss_timestamp = self._parse_hhmmss_utc_time(value)
        if hhmmss_timestamp is not None:
            return hhmmss_timestamp

        try:
            return parse_datetime(value)
        except ValueError as exc:
            if "Timezone required in datetime string" not in str(exc):
                raise

        base_timestamp = meta_adapter.get_start_ts()
        if base_timestamp is None:
            raise ValueError(
                "EHR CSV contains timezone-naive 'time_str' values. "
                "Provide timezone-aware timestamps or set 'start_ts' in metadata."
            )

        time_rel_seconds = base_timestamp.astype("datetime64[ns]")
        naive_value = np.datetime64(value.replace(" ", "T"), "ns")
        time_of_day_offset = naive_value - naive_value.astype("datetime64[D]")
        return base_timestamp.astype("datetime64[D]") + time_of_day_offset

    def _parse_hhmmss_utc_time(self, value: str) -> np.datetime64 | None:
        normalized = value.strip()
        if len(normalized) != 6 or not normalized.isdigit():
            return None

        hours = int(normalized[0:2])
        minutes = int(normalized[2:4])
        seconds = int(normalized[4:6])

        if hours > 23 or minutes > 59 or seconds > 59:
            raise ValueError(f"Invalid HHMMSS UTC time string: {value}")
        # unfortunately, the electronics time do not fetch the real UTC timestamp with date
        # so we hardcode it
        return parse_datetime(f"2000-01-01T{hours:02d}:{minutes:02d}:{seconds:02d}Z")

    def _parse_float(self, value: str | None) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    def _sanitize_coordinate(self, value: float | None) -> float:
        if value is None:
            return float("nan")

        if value == 0.0 or abs(value) > self.MAX_REASONABLE_ABSOLUTE_COORDINATE:
            return float("nan")

        return value
