import json
from pathlib import Path

import numpy as np
from src.constants.ChannelNames import ChannelNames
from src.extraction.erhAdapter import ERHAdapter
from src.models.job import Job

SAMPLE_EHR_CSV = """time_str;time_rel_s;esp_us;height_m;wand_raw;servo_deg;control_timestamp_ms;quat_i;quat_j;quat_k;quat_real;lin_ax;lin_ay;lin_az;earth_ax;earth_ay;earth_az;earth_z_acc;imu_timestamp_ms;speed_knots;latitude_deg;longitude_deg;course_deg
2025-10-18T08:30:23.100Z;0.1;100000;0.41;1120;3.1;1001;0.1;0.2;0.3;0.9;1.1;1.2;1.3;2.1;2.2;2.3;2.4;2001;11.2;57.6680;11.8424;245.0
2025-10-18T08:30:23.900Z;0.9;900000;0.42;1123;3.5;1009;0.2;0.3;0.4;0.8;1.4;1.5;1.6;2.4;2.5;2.6;2.7;2009;11.7;57.6681;11.8425;246.0
2025-10-18T08:30:24.100Z;1.1;1100000;0.43;1126;3.7;1011;0.3;0.4;0.5;0.7;1.7;1.8;1.9;2.7;2.8;2.9;3.0;2011;12.0;57.6682;11.8426;247.0
2025-10-18T08:30:24.900Z;1.9;1900000;0.44;1129;3.8;1019;0.4;0.5;0.6;0.6;2.0;2.1;2.2;3.0;3.1;3.2;3.3;2019;12.4;57.6683;11.8427;248.0
"""

SAMPLE_EHR_CSV_RELATIVE_TIME = """esp_us;height_m;wand_raw;servo_deg;latitude_deg;longitude_deg;speed_knots;course_deg
0;0.42;1123;3.5;57.6680;11.8424;11.7;246.0
1000000;0.44;1129;3.8;57.6683;11.8427;12.4;248.0
"""

SAMPLE_EHR_CSV_HHMMSS_TIME = """time_str;esp_us;height_m;wand_raw;servo_deg;latitude_deg;longitude_deg;speed_knots;course_deg
101446;0;0.42;1123;3.5;57.6680;11.8424;11.7;246.0
101447;1000000;0.44;1129;3.8;57.6683;11.8427;12.4;248.0
"""

SAMPLE_EHR_CSV_INVALID_GPS = """time_str;esp_us;height_m;wand_raw;servo_deg;latitude_deg;longitude_deg;speed_knots;course_deg
2025-10-18T08:30:23.100Z;100000;0.41;1120;3.1;57.6680;11.8424;11.2;245.0
2025-10-18T08:30:23.900Z;900000;0.42;1123;3.5;0;150.0;11.7;246.0
2025-10-18T08:30:24.900Z;1900000;0.44;1129;3.8;57.6683;11.8427;12.4;248.0
"""


def test_ehr_adapter_required_headers_are_broadcast_for_resolution() -> None:
    adapter = ERHAdapter()

    assert adapter.required_headers == {
        "esp_us",
        "height_m",
        "wand_raw",
        "servo_deg",
    }


def test_ehr_adapter_downsamples_to_one_hz_and_maps_channels(tmp_path: Path) -> None:
    csv_file = tmp_path / "session.csv"
    csv_file.write_text(SAMPLE_EHR_CSV, encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(json.dumps({"sessionName": "EHR"}), encoding="utf-8")

    adapter = ERHAdapter()

    session = adapter.parse_job(
        Job(session_path=str(csv_file), meta_path=str(meta_file))
    )

    assert session.metadata.source_type == "ehr"
    assert np.array_equal(
        session.channels[ChannelNames.LATITUDE.value].timestamps,
        np.array(
            ["2025-10-18T08:30:23.900", "2025-10-18T08:30:24.900"],
            dtype="datetime64[ms]",
        ),
    )
    assert np.allclose(
        session.channels[ChannelNames.LATITUDE.value].values,
        np.array([57.6681, 57.6683], dtype=float),
    )
    assert np.allclose(
        session.channels[ChannelNames.SOG.value].values,
        np.array([11.7, 12.4], dtype=float),
    )
    assert np.allclose(
        session.channels[ChannelNames.COG.value].values,
        np.array([246.0, 248.0], dtype=float),
    )
    assert np.allclose(session.channels["height_m"].values, np.array([0.42, 0.44]))
    assert np.allclose(session.channels["quat_real"].values, np.array([0.8, 0.6]))
    assert np.allclose(session.channels["earth_z_acc"].values, np.array([2.7, 3.3]))
    assert np.allclose(session.channels["time_rel_s"].values, np.array([0.9, 1.9]))


def test_ehr_adapter_uses_meta_start_time_for_relative_timestamps(
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "session.csv"
    csv_file.write_text(SAMPLE_EHR_CSV_RELATIVE_TIME, encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "sessionName": "EHR",
                "start_ts": "2025-10-18T08:30:23.000Z",
            }
        ),
        encoding="utf-8",
    )

    adapter = ERHAdapter()

    session = adapter.parse_job(
        Job(session_path=str(csv_file), meta_path=str(meta_file))
    )

    assert np.array_equal(
        session.channels["height_m"].timestamps,
        np.array(
            ["2025-10-18T08:30:23.000", "2025-10-18T08:30:24.000"],
            dtype="datetime64[ms]",
        ),
    )


def test_ehr_adapter_preserves_ride_height_offset_in_metadata_extras(
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "session.csv"
    csv_file.write_text(SAMPLE_EHR_CSV_RELATIVE_TIME, encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "sessionName": "EHR",
                "start_ts": "2025-10-18T08:30:23.000Z",
                "rideHeightOffsetCm": -24,
            }
        ),
        encoding="utf-8",
    )

    adapter = ERHAdapter()

    session = adapter.parse_job(
        Job(session_path=str(csv_file), meta_path=str(meta_file))
    )

    assert session.metadata.extras["rideHeightOffsetCm"] == -24.0


def test_ehr_adapter_parses_hhmmss_utc_time_strings(tmp_path: Path) -> None:
    csv_file = tmp_path / "session.csv"
    csv_file.write_text(SAMPLE_EHR_CSV_HHMMSS_TIME, encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(json.dumps({"sessionName": "EHR"}), encoding="utf-8")

    adapter = ERHAdapter()

    session = adapter.parse_job(
        Job(session_path=str(csv_file), meta_path=str(meta_file))
    )

    assert np.array_equal(
        session.channels[ChannelNames.LATITUDE.value].timestamps,
        np.array(
            ["2000-01-01T10:14:46.000", "2000-01-01T10:14:47.000"],
            dtype="datetime64[ms]",
        ),
    )


def test_ehr_adapter_converts_invalid_gps_values_to_nan(tmp_path: Path) -> None:
    csv_file = tmp_path / "session.csv"
    csv_file.write_text(SAMPLE_EHR_CSV_INVALID_GPS, encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(json.dumps({"sessionName": "EHR"}), encoding="utf-8")

    adapter = ERHAdapter()

    session = adapter.parse_job(
        Job(session_path=str(csv_file), meta_path=str(meta_file))
    )

    assert np.array_equal(
        session.channels[ChannelNames.LATITUDE.value].timestamps,
        np.array(
            ["2025-10-18T08:30:23.900", "2025-10-18T08:30:24.900"],
            dtype="datetime64[ms]",
        ),
    )
    assert np.isnan(session.channels[ChannelNames.LATITUDE.value].values[0])
    assert np.isnan(session.channels[ChannelNames.LONGITUDE.value].values[0])
    assert session.channels[ChannelNames.LATITUDE.value].values[1] == np.float64(
        57.6683
    )
    assert session.channels[ChannelNames.LONGITUDE.value].values[1] == np.float64(
        11.8427
    )
