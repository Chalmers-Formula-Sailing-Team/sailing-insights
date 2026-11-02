# tests/test_garmin_adapter.py

import json
from pathlib import Path

import numpy as np
import pytest
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.extraction.garminAdapter import GarminAdapter

# Adjust this import to your real location once CanonicalSession exists
from src.models.canonicalSession import CanonicalSession
from src.models.job import Job

FIXTURES_DIR = Path(__file__).parent / "fixtures"

SAMPLE_TCX = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
  xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
  xmlns:ns5="http://www.garmin.com/xmlschemas/ActivityGoals/v1"
  xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2"
  xmlns:ns2="http://www.garmin.com/xmlschemas/UserProfile/v2"
  xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:ns4="http://www.garmin.com/xmlschemas/ProfileExtension/v1">
  <Activities>
    <Activity Sport="Other">
      <Id>2025-09-06T08:30:23.000Z</Id>
      <Lap StartTime="2025-09-06T08:30:23.000Z">
        <TotalTimeSeconds>7550.666</TotalTimeSeconds>
        <DistanceMeters>28560.82</DistanceMeters>
        <MaximumSpeed>9.45199966430664</MaximumSpeed>
        <Calories>775</Calories>
        <AverageHeartRateBpm>
          <Value>116</Value>
        </AverageHeartRateBpm>
        <MaximumHeartRateBpm>
          <Value>159</Value>
        </MaximumHeartRateBpm>
        <Intensity>Active</Intensity>
        <TriggerMethod>Manual</TriggerMethod>
        <Track>
          <Trackpoint>
            <Time>2025-09-06T08:30:23.000Z</Time>
            <Position>
              <LatitudeDegrees>57.66800721175969</LatitudeDegrees>
              <LongitudeDegrees>11.84245990589261</LongitudeDegrees>
            </Position>
            <AltitudeMeters>-2.799999952316284</AltitudeMeters>
            <DistanceMeters>0.0</DistanceMeters>
            <HeartRateBpm>
              <Value>120</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX />
            </Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2025-09-06T08:30:24.000Z</Time>
            <Position>
              <LatitudeDegrees>57.66804736107588</LatitudeDegrees>
              <LongitudeDegrees>11.842476418241858</LongitudeDegrees>
            </Position>
            <AltitudeMeters>-2.5999999046325684</AltitudeMeters>
            <DistanceMeters>4.579999923706055</DistanceMeters>
            <HeartRateBpm>
              <Value>120</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX>
                <ns3:Speed>6.008999824523926</ns3:Speed>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""

SAMPLE_TCX_WITH_OFFSET_TIMESTAMPS = SAMPLE_TCX.replace(
    "2025-09-06T08:30:23.000Z", "2025-09-06T08:30:23.000+02:00"
).replace("2025-09-06T08:30:24.000Z", "2025-09-06T08:30:24.000+02:00")

SAMPLE_TCX_WITH_UNSORTED_TRACKPOINTS = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
  xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
  xmlns:ns5="http://www.garmin.com/xmlschemas/ActivityGoals/v1"
  xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2"
  xmlns:ns2="http://www.garmin.com/xmlschemas/UserProfile/v2"
  xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:ns4="http://www.garmin.com/xmlschemas/ProfileExtension/v1">
  <Activities>
    <Activity Sport="Other">
      <Id>2025-09-06T08:30:23.000Z</Id>
      <Lap StartTime="2025-09-06T08:30:23.000Z">
        <Track>
          <Trackpoint>
            <Time>2025-09-06T08:30:25.000Z</Time>
            <Position>
              <LatitudeDegrees>57.3</LatitudeDegrees>
              <LongitudeDegrees>11.3</LongitudeDegrees>
            </Position>
            <HeartRateBpm>
              <Value>103</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX>
                <ns3:Speed>6.3</ns3:Speed>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2025-09-06T08:30:23.000Z</Time>
            <Position>
              <LatitudeDegrees>57.1</LatitudeDegrees>
              <LongitudeDegrees>11.1</LongitudeDegrees>
            </Position>
            <HeartRateBpm>
              <Value>101</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX>
                <ns3:Speed>6.1</ns3:Speed>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2025-09-06T08:30:24.000Z</Time>
            <Position>
              <LatitudeDegrees>57.2</LatitudeDegrees>
              <LongitudeDegrees>11.2</LongitudeDegrees>
            </Position>
            <HeartRateBpm>
              <Value>102</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX>
                <ns3:Speed>6.2</ns3:Speed>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""

SAMPLE_TCX_WITH_DUPLICATE_TIMESTAMPS = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
  xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
  xmlns:ns5="http://www.garmin.com/xmlschemas/ActivityGoals/v1"
  xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2"
  xmlns:ns2="http://www.garmin.com/xmlschemas/UserProfile/v2"
  xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:ns4="http://www.garmin.com/xmlschemas/ProfileExtension/v1">
  <Activities>
    <Activity Sport="Other">
      <Id>2025-09-06T08:30:23.000Z</Id>
      <Lap StartTime="2025-09-06T08:30:23.000Z">
        <Track>
          <Trackpoint>
            <Time>2025-09-06T08:30:23.000Z</Time>
            <Position>
              <LatitudeDegrees>57.1</LatitudeDegrees>
              <LongitudeDegrees>11.1</LongitudeDegrees>
            </Position>
            <HeartRateBpm>
              <Value>101</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX>
                <ns3:Speed>6.1</ns3:Speed>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2025-09-06T08:30:23.000Z</Time>
            <Position>
              <LatitudeDegrees>57.15</LatitudeDegrees>
              <LongitudeDegrees>11.15</LongitudeDegrees>
            </Position>
            <HeartRateBpm>
              <Value>102</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX>
                <ns3:Speed>6.15</ns3:Speed>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2025-09-06T08:30:24.000Z</Time>
            <Position>
              <LatitudeDegrees>57.2</LatitudeDegrees>
              <LongitudeDegrees>11.2</LongitudeDegrees>
            </Position>
            <HeartRateBpm>
              <Value>103</Value>
            </HeartRateBpm>
            <Extensions>
              <ns3:TPX>
                <ns3:Speed>6.2</ns3:Speed>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""


@pytest.fixture
def adapter() -> GarminAdapter:
    return GarminAdapter()


@pytest.fixture
def tcx_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "session.tcx"
    file_path.write_text(SAMPLE_TCX, encoding="utf-8")
    return file_path


@pytest.fixture
def tcx_file_with_offset_timestamps(tmp_path: Path) -> Path:
    file_path = tmp_path / "session_offset.tcx"
    file_path.write_text(SAMPLE_TCX_WITH_OFFSET_TIMESTAMPS, encoding="utf-8")
    return file_path


@pytest.fixture
def tcx_file_with_unsorted_trackpoints(tmp_path: Path) -> Path:
    file_path = tmp_path / "session_unsorted.tcx"
    file_path.write_text(SAMPLE_TCX_WITH_UNSORTED_TRACKPOINTS, encoding="utf-8")
    return file_path


@pytest.fixture
def tcx_file_with_duplicate_timestamps(tmp_path: Path) -> Path:
    file_path = tmp_path / "session_duplicate_timestamps.tcx"
    file_path.write_text(SAMPLE_TCX_WITH_DUPLICATE_TIMESTAMPS, encoding="utf-8")
    return file_path


@pytest.fixture
def meta_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "session.json"
    file_path.write_text(
        (FIXTURES_DIR / "activity_20297966806.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return file_path


@pytest.fixture
def activity_metadata() -> dict:
    return json.loads(
        (FIXTURES_DIR / "activity_20297966806.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def tcx_job(tcx_file: Path, meta_file: Path) -> Job:
    return Job(session_path=str(tcx_file), meta_path=str(meta_file))


@pytest.fixture
def tcx_job_with_offset_timestamps(
    tcx_file_with_offset_timestamps: Path, meta_file: Path
) -> Job:
    return Job(
        session_path=str(tcx_file_with_offset_timestamps),
        meta_path=str(meta_file),
    )


@pytest.fixture
def tcx_job_with_unsorted_trackpoints(
    tcx_file_with_unsorted_trackpoints: Path, meta_file: Path
) -> Job:
    return Job(
        session_path=str(tcx_file_with_unsorted_trackpoints),
        meta_path=str(meta_file),
    )


@pytest.fixture
def tcx_job_with_duplicate_timestamps(
    tcx_file_with_duplicate_timestamps: Path, meta_file: Path
) -> Job:
    return Job(
        session_path=str(tcx_file_with_duplicate_timestamps),
        meta_path=str(meta_file),
    )


class TestGarminAdapterCanHandle:
    def test_can_handle_returns_true_for_tcx_file(
        self, adapter: GarminAdapter, tcx_job: Job
    ):
        assert adapter.can_handle(tcx_job) is True

    def test_can_handle_returns_false_for_non_tcx_file(
        self, adapter: GarminAdapter, tmp_path: Path
    ):
        session_file = tmp_path / "session.gpx"
        session_file.write_text("<gpx></gpx>", encoding="utf-8")

        meta_file = tmp_path / "session.json"
        meta_file.write_text("{}", encoding="utf-8")

        job = Job(session_path=str(session_file), meta_path=str(meta_file))

        assert adapter.can_handle(job) is False

    def test_can_handle_uppercase_suffix(self, adapter: GarminAdapter, tmp_path: Path):
        session_file = tmp_path / "session.TCX"
        session_file.write_text(SAMPLE_TCX, encoding="utf-8")

        meta_file = tmp_path / "session.json"
        meta_file.write_text("{}", encoding="utf-8")

        job = Job(session_path=str(session_file), meta_path=str(meta_file))

        # Current implementation checks suffix exactly against [".tcx"]
        assert adapter.can_handle(job) is True


class TestGarminAdapterParseJobExpectedContract:
    def test_parse_job_returns_canonical_session(
        self, adapter: GarminAdapter, tcx_job: Job
    ):
        session = adapter.parse_job(tcx_job)

        assert isinstance(session, CanonicalSession)

        assert session is not None

    def test_parse_job_extracts_two_trackpoints(
        self, adapter: GarminAdapter, tcx_job: Job
    ):
        session = adapter.parse_job(tcx_job)

        assert ChannelNames.LATITUDE.value in session.channels
        assert ChannelNames.LONGITUDE.value in session.channels
        assert len(session.channels[ChannelNames.LATITUDE.value].values) == 2
        assert len(session.channels[ChannelNames.LONGITUDE.value].values) == 2

    def test_parse_job_extracts_lat_long_heart_rate(
        self, adapter: GarminAdapter, tcx_job: Job
    ):
        session = adapter.parse_job(tcx_job)

        # Example expected values from the sample TCX:
        latitudes = session.channels[ChannelNames.LATITUDE.value].values
        longitudes = session.channels[ChannelNames.LONGITUDE.value].values
        heart_rate = session.channels[ChannelNames.HEART_RATE.value].values

        assert latitudes.tolist() == [57.66800721175969, 57.66804736107588]
        assert longitudes.tolist() == [11.84245990589261, 11.842476418241858]
        assert heart_rate.tolist() == [120, 120]

    def test_parse_job_extracts_timestamps(self, adapter: GarminAdapter, tcx_job: Job):
        session = adapter.parse_job(tcx_job)

        # Example depending on your chosen internal representation:
        timestamps = session.channels[ChannelNames.LATITUDE.value].timestamps
        assert len(timestamps) == 2
        assert timestamps[0] < timestamps[1]
        assert timestamps.tolist() == [
            np.datetime64("2025-09-06T08:30:23.000Z"),
            np.datetime64("2025-09-06T08:30:24.000Z"),
        ]

    def test_parse_job_handles_optional_speed_extension(
        self, adapter: GarminAdapter, tcx_job: Job
    ):
        session = adapter.parse_job(tcx_job)

        # The first point has no speed value, the second does.
        speeds = session.channels[ChannelNames.SOG.value].values
        assert len(speeds) == 1
        assert speeds[0] == pytest.approx(6.008999824523926)
        assert session.channels[ChannelNames.SOG.value].timestamps[0] == np.datetime64(
            "2025-09-06T08:30:24.000"
        )

    def test_parse_job_emits_utc_timestamps_for_every_channel(
        self,
        adapter: GarminAdapter,
        tcx_job_with_offset_timestamps: Job,
    ) -> None:
        session = adapter.parse_job(tcx_job_with_offset_timestamps)

        expected_timestamps = {
            ChannelNames.LATITUDE.value: np.array(
                [
                    np.datetime64("2025-09-06T06:30:23.000"),
                    np.datetime64("2025-09-06T06:30:24.000"),
                ],
                dtype="datetime64[ms]",
            ),
            ChannelNames.LONGITUDE.value: np.array(
                [
                    np.datetime64("2025-09-06T06:30:23.000"),
                    np.datetime64("2025-09-06T06:30:24.000"),
                ],
                dtype="datetime64[ms]",
            ),
            ChannelNames.HEART_RATE.value: np.array(
                [
                    np.datetime64("2025-09-06T06:30:23.000"),
                    np.datetime64("2025-09-06T06:30:24.000"),
                ],
                dtype="datetime64[ms]",
            ),
            ChannelNames.SOG.value: np.array(
                [np.datetime64("2025-09-06T06:30:24.000")],
                dtype="datetime64[ms]",
            ),
        }

        for channel_name, expected in expected_timestamps.items():
            timestamps = session.channels[channel_name].timestamps
            assert timestamps.dtype == np.dtype("datetime64[ms]")
            np.testing.assert_array_equal(timestamps, expected)

    def test_parse_job_sorts_channel_samples_by_timestamp(
        self,
        adapter: GarminAdapter,
        tcx_job_with_unsorted_trackpoints: Job,
    ) -> None:
        session = adapter.parse_job(tcx_job_with_unsorted_trackpoints)

        np.testing.assert_array_equal(
            session.channels[ChannelNames.LATITUDE.value].timestamps,
            np.array(
                [
                    np.datetime64("2025-09-06T08:30:23.000"),
                    np.datetime64("2025-09-06T08:30:24.000"),
                    np.datetime64("2025-09-06T08:30:25.000"),
                ],
                dtype="datetime64[ms]",
            ),
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.LATITUDE.value].values,
            np.array([57.1, 57.2, 57.3]),
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.LONGITUDE.value].values,
            np.array([11.1, 11.2, 11.3]),
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.HEART_RATE.value].values,
            np.array([101, 102, 103]),
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.SOG.value].values,
            np.array([6.1, 6.2, 6.3]),
        )

    def test_parse_job_deduplicates_repeated_timestamps(
        self,
        adapter: GarminAdapter,
        tcx_job_with_duplicate_timestamps: Job,
    ) -> None:
        session = adapter.parse_job(tcx_job_with_duplicate_timestamps)

        expected_timestamps = np.array(
            [
                np.datetime64("2025-09-06T08:30:23.000"),
                np.datetime64("2025-09-06T08:30:24.000"),
            ],
            dtype="datetime64[ms]",
        )

        np.testing.assert_array_equal(
            session.channels[ChannelNames.LATITUDE.value].timestamps,
            expected_timestamps,
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.LATITUDE.value].values,
            np.array([57.15, 57.2]),
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.LONGITUDE.value].values,
            np.array([11.15, 11.2]),
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.HEART_RATE.value].values,
            np.array([102, 103]),
        )
        np.testing.assert_array_equal(
            session.channels[ChannelNames.SOG.value].values,
            np.array([6.15, 6.2]),
        )

    def test_parse_job_preserves_top_level_activity_metadata_fields(
        self,
        adapter: GarminAdapter,
        tcx_job: Job,
    ):
        session = adapter.parse_job(tcx_job)
        meta = session.metadata
        assert meta.session_name == "demo session"
        assert meta.boat_id == "Demo Boat"
        assert meta.notes == "Synthetic fixture data for parser tests."
        assert meta.start_at == np.datetime64("2025-09-06T10:30:00")
        assert meta.end_at == np.datetime64("2025-09-06T12:36:00")
        assert session.metrics[MetricNames.MANUAL_WIND_SPEED.value].value == pytest.approx(12.0)
        assert session.metrics[MetricNames.MANUAL_WIND_SPEED.value].unit == "kn"
        assert (
            session.metrics[MetricNames.MANUAL_WIND_SPEED.value].source
            == MetricNames.MANUAL_WIND_SOURCE.value
        )
        assert session.metrics[MetricNames.MANUAL_WIND_GUST.value].value == pytest.approx(17.0)
        assert session.metrics[MetricNames.MANUAL_WIND_GUST.value].unit == "kn"
        assert (
            session.metrics[MetricNames.MANUAL_WIND_GUST.value].source
            == MetricNames.MANUAL_WIND_SOURCE.value
        )
        assert (
            session.metrics[MetricNames.MANUAL_WIND_DIRECTION.value].value
            == pytest.approx(123.0)
        )
        assert session.metrics[MetricNames.MANUAL_WIND_DIRECTION.value].unit == "deg"
        assert (
            session.metrics[MetricNames.MANUAL_WIND_DIRECTION.value].source
            == MetricNames.MANUAL_WIND_SOURCE.value
        )
        assert session.metrics[MetricNames.MANUAL_WAVE_HEIGHT.value].value == pytest.approx(0.8)
        assert session.metrics[MetricNames.MANUAL_WAVE_HEIGHT.value].unit == "m"
        assert (
            session.metrics[MetricNames.MANUAL_WAVE_HEIGHT.value].source
            == MetricNames.MANUAL_WIND_SOURCE.value
        )

    def test_parse_job_preserves_race_details_from_activity_metadata(
        self,
        adapter: GarminAdapter,
        tcx_job: Job,
    ):
        session = adapter.parse_job(tcx_job)

        assert len(session.races) == 1
        race = session.races[0]
        assert race.id == "188e5779-006e-4fb3-b9d1-754e193e4d34"
        assert race.name == "Race 1"
        assert race.start_at == np.datetime64("2025-09-06T08:34:20.000Z")
        assert race.finish_at == np.datetime64("2025-09-06T08:52:43.000Z")
