import json
from pathlib import Path

import numpy as np
import pytest
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.extraction.csvAdapter import CsvAdapter
from src.extraction.erhAdapter import ERHAdapter
from src.extraction.sailmonAdapter import SailmonAdapter
from src.models.job import Job

SAMPLE_SAILMON_CSV = """time,servertime,latitude,longitude,HDT - Heading True,SOG - Speed over Ground,COG - Course over Ground,TWA - True Wind Angle,TWD - True Wind Direction,Heel,Trim Fore / Aft,VMG - Velocity Made Good,Time to Gun,GPS Satellites,GPS HAcc,Battery Charge,Battery 1 Voltage,Battery 1 Current,Battery 1 Temperature
2025-10-18T08:30:23.000Z,2025-10-18T08:30:23.000Z,57.66800721175969,11.84245990589261,245.0,12.4,247.0,32.0,210.0,4.1,0.2,11.7,120,14,0.8,87,12.3,1.4,28.0
2025-10-18T08:30:24.000Z,2025-10-18T08:30:24.000Z,57.66804736107588,11.842476418241858,246.0,12.6,248.0,31.5,211.0,4.0,0.1,11.9,119,14,0.8,87,12.3,1.4,28.1
"""

SAMPLE_EHR_CSV = """time_str;esp_us;height_m;wand_raw;servo_deg;latitude_deg;longitude_deg;speed_knots;course_deg
2025-10-18T08:30:23.000Z;0;0.42;1123;3.5;57.66800721175969;11.84245990589261;11.7;246.0
2025-10-18T08:30:24.000Z;1000000;0.44;1129;3.8;57.66804736107588;11.842476418241858;12.4;248.0
"""


@pytest.fixture
def sailmon_csv_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "session.csv"
    file_path.write_text(SAMPLE_SAILMON_CSV, encoding="utf-8")
    return file_path


@pytest.fixture
def ehr_csv_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "session.csv"
    file_path.write_text(SAMPLE_EHR_CSV, encoding="utf-8")
    return file_path


@pytest.fixture
def meta_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "meta.json"
    file_path.write_text(
        json.dumps(
            {
                "sessionName": "Sailmon Session",
                "boat": "Bird",
                "windSpeed": 16.2,
                "exportedAt": "2025-10-18T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return file_path


def test_csv_adapter_can_handle_csv_extension() -> None:
    adapter = CsvAdapter()

    assert adapter.can_handle(Job(session_path="session.csv", meta_path="meta.json"))
    assert not adapter.can_handle(
        Job(session_path="session.fit", meta_path="meta.json")
    )


def test_csv_adapter_routes_sailmon_csv_to_sailmon_adapter(
    sailmon_csv_file: Path, meta_file: Path
) -> None:
    adapter = CsvAdapter()

    session = adapter.parse_job(
        Job(session_path=str(sailmon_csv_file), meta_path=str(meta_file))
    )

    assert session.metadata.source_type == "sailmon"
    assert session.metadata.session_name == "Sailmon Session"
    assert session.metadata.boat_id == "Bird"
    assert (
        session.channels[ChannelNames.LATITUDE.value].source
        == SailmonAdapter.SAILMON_SOURCE
    )
    assert (
        session.channels[ChannelNames.LONGITUDE.value].source
        == SailmonAdapter.SAILMON_SOURCE
    )
    assert session.channels[ChannelNames.SOG.value].unit == "m/s"
    assert np.array_equal(
        session.channels[ChannelNames.LATITUDE.value].timestamps,
        np.array(
            ["2025-10-18T08:30:23.000", "2025-10-18T08:30:24.000"],
            dtype="datetime64[ms]",
        ),
    )
    assert np.allclose(
        session.channels[ChannelNames.LATITUDE.value].values,
        np.array([57.66800721175969, 57.66804736107588], dtype=float),
    )
    assert np.allclose(
        session.channels[ChannelNames.LONGITUDE.value].values,
        np.array([11.84245990589261, 11.842476418241858], dtype=float),
    )
    assert np.allclose(
        session.channels[ChannelNames.SOG.value].values,
        np.array([12.4, 12.6], dtype=float),
    )
    assert session.metrics[MetricNames.MANUAL_WIND_SPEED.value].value == 16.2


def test_csv_adapter_routes_ehr_csv_to_ehr_adapter(
    ehr_csv_file: Path, meta_file: Path
) -> None:
    adapter = CsvAdapter()

    session = adapter.parse_job(
        Job(session_path=str(ehr_csv_file), meta_path=str(meta_file))
    )

    assert session.metadata.source_type == "ehr"
    assert (
        session.channels[ChannelNames.LATITUDE.value].source == ERHAdapter.SOURCE_NAME
    )
    assert session.channels["height_m"].unit == "m"
    assert np.allclose(
        session.channels["servo_deg"].values,
        np.array([3.5, 3.8], dtype=float),
    )


def test_csv_adapter_raises_when_no_csv_subadapter_matches(
    tmp_path: Path, meta_file: Path
) -> None:
    csv_file = tmp_path / "unknown.csv"
    csv_file.write_text(
        "timestamp,lat,lon,speed\n2025-10-18T08:30:23.000Z,57.6,11.8,12.4\n",
        encoding="utf-8",
    )
    adapter = CsvAdapter()

    with pytest.raises(ValueError, match="No CSV adapter found"):
        adapter.parse_job(Job(session_path=str(csv_file), meta_path=str(meta_file)))
