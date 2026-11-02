import json
from pathlib import Path

import numpy as np
from src.constants.ChannelNames import ChannelNames

from src.extraction.sailmonAdapter import SailmonAdapter
from src.models.job import Job

SAMPLE_SAILMON_CSV_WITH_DUPLICATE_TIMESTAMPS = """time,servertime,latitude,longitude,HDT - Heading True,SOG - Speed over Ground,COG - Course over Ground,TWA - True Wind Angle,TWD - True Wind Direction,Heel,Trim Fore / Aft,VMG - Velocity Made Good,Time to Gun,GPS Satellites,GPS HAcc,Battery Charge,Battery 1 Voltage,Battery 1 Current,Battery 1 Temperature
2025-10-18T08:30:24.000Z,2025-10-18T08:30:24.000Z,57.2,11.2,246.0,12.6,248.0,31.5,211.0,4.0,0.1,11.9,119,14,0.8,87,12.3,1.4,28.1
2025-10-18T08:30:23.000Z,2025-10-18T08:30:23.000Z,57.1,11.1,245.0,12.4,247.0,32.0,210.0,4.1,0.2,11.7,120,14,0.8,87,12.3,1.4,28.0
2025-10-18T08:30:23.000Z,2025-10-18T08:30:23.000Z,57.15,11.15,245.5,12.5,247.5,31.8,210.5,4.05,0.15,11.8,119,14,0.8,87,12.3,1.4,28.0
"""

SAMPLE_SAILMON_CSV_WITH_NAIVE_TIMESTAMPS = """time,servertime,latitude,longitude,HDT - Heading True,SOG - Speed over Ground,COG - Course over Ground,TWA - True Wind Angle,TWD - True Wind Direction,Heel,Trim Fore / Aft,VMG - Velocity Made Good,Time to Gun,GPS Satellites,GPS HAcc,Battery Charge,Battery 1 Voltage,Battery 1 Current,Battery 1 Temperature
2025-10-18 08:30:24.000,2025-10-18 08:30:24.000,57.2,11.2,246.0,12.6,248.0,31.5,211.0,4.0,0.1,11.9,119,14,0.8,87,12.3,1.4,28.1
2025-10-18 08:30:23.000,2025-10-18 08:30:23.000,57.1,11.1,245.0,12.4,247.0,32.0,210.0,4.1,0.2,11.7,120,14,0.8,87,12.3,1.4,28.0
"""


def test_sailmon_adapter_required_headers_are_broadcast_for_resolution() -> None:
    adapter = SailmonAdapter()

    assert adapter.required_headers == {
        "time",
        "servertime",
        "latitude",
        "longitude",
        "HDT - Heading True",
        "SOG - Speed over Ground",
        "COG - Course over Ground",
        "Heel",
        "Trim Fore / Aft",
        "GPS Satellites",
        "GPS HAcc",
        "Battery Charge",
        "Battery 1 Voltage",
        "Battery 1 Current",
        "Battery 1 Temperature",
    }


def test_sailmon_adapter_sorts_and_deduplicates_samples(tmp_path: Path) -> None:
    csv_file = tmp_path / "session.csv"
    csv_file.write_text(SAMPLE_SAILMON_CSV_WITH_DUPLICATE_TIMESTAMPS, encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(json.dumps({"sessionName": "Sailmon"}), encoding="utf-8")

    adapter = SailmonAdapter()

    session = adapter.parse_job(Job(session_path=str(csv_file), meta_path=str(meta_file)))

    assert np.array_equal(
        session.channels[ChannelNames.LATITUDE.value].timestamps,
        np.array(
            ["2025-10-18T08:30:23.000", "2025-10-18T08:30:24.000"],
            dtype="datetime64[ms]",
        ),
    )
    assert np.allclose(
        session.channels[ChannelNames.LATITUDE.value].values, np.array([57.15, 57.2])
    )
    assert np.allclose(
        session.channels[ChannelNames.LONGITUDE.value].values, np.array([11.15, 11.2])
    )
    assert np.allclose(
        session.channels[ChannelNames.HEADING.value].values, np.array([245.5, 246.0])
    )
    assert np.allclose(
        session.channels[ChannelNames.SOG.value].values, np.array([12.5, 12.6])
    )
    assert np.allclose(
        session.channels[ChannelNames.COG.value].values, np.array([247.5, 248.0])
    )
    assert np.allclose(
        session.channels[ChannelNames.TWA.value].values, np.array([31.8, 31.5])
    )
    assert np.allclose(
        session.channels[ChannelNames.TWD.value].values, np.array([210.5, 211.0])
    )
    assert np.allclose(
        session.channels[ChannelNames.HEEL.value].values, np.array([4.05, 4.0])
    )
    assert np.allclose(
        session.channels[ChannelNames.PITCH.value].values, np.array([0.15, 0.1])
    )
    assert np.allclose(
        session.channels[ChannelNames.VMG.value].values, np.array([11.8, 11.9])
    )
    assert np.allclose(
        session.channels[ChannelNames.TIME_TO_GUN.value].values,
        np.array([119.0, 119.0]),
    )
    assert session.metadata.start_at == np.datetime64("2025-10-18T08:30:23.000")
    assert session.metadata.end_at == np.datetime64("2025-10-18T08:30:24.000")


def test_sailmon_adapter_infers_timezone_from_location_for_naive_timestamps(
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "session.csv"
    csv_file.write_text(SAMPLE_SAILMON_CSV_WITH_NAIVE_TIMESTAMPS, encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps({"sessionName": "Sailmon", "location": "Langedrag"}),
        encoding="utf-8",
    )

    adapter = SailmonAdapter()

    session = adapter.parse_job(Job(session_path=str(csv_file), meta_path=str(meta_file)))

    assert np.array_equal(
        session.channels[ChannelNames.LATITUDE.value].timestamps,
        np.array(
            ["2025-10-18T08:30:23.000", "2025-10-18T08:30:24.000"],
            dtype="datetime64[ms]",
        ),
    )
    assert session.metadata.timezone == "Europe/Stockholm"
