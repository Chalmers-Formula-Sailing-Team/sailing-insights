import numpy as np
import pytest

from src.analyzer.sessionAnalyzer import SessionAnalyzer
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.models.canonicalSession import (CanonicalSession, Channel,
                                         SessionMetadata)


@pytest.fixture
def session() -> CanonicalSession:
    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-123"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=np.array([1.0, 2.0, 3.0]),
                values=np.array([4.3, 7.2, 6.8]),
                unit="kn",
                source="gps",
            ),
        },
    )


def test_analyze_adds_max_speed_metric_and_provenance(session: CanonicalSession) -> None:
    analyzer = SessionAnalyzer()

    result = analyzer.analyze(session)

    max_speed_metric = result.get_metric(MetricNames.MAX_BOAT_SPEED.value)
    assert max_speed_metric.value == 7.2
    assert max_speed_metric.unit == "kn"
    assert max_speed_metric.source == "SessionAnalyzer"
    assert max_speed_metric.metadata == {"channel": ChannelNames.SOG.value}

    distance_metric = result.get_metric(MetricNames.SESSION_DISTANCE.value)
    assert distance_metric.value == 0.0
    assert distance_metric.unit == "nm"
    assert distance_metric.source == "SessionAnalyzer"
    assert distance_metric.metadata == {
        "channels": [
            ChannelNames.LATITUDE.value,
            ChannelNames.LONGITUDE.value,
        ]
    }

    duration_metric = result.get_metric(MetricNames.SESSION_DURATION.value)
    assert duration_metric.value == 0.0
    assert duration_metric.unit == "min"
    assert duration_metric.source == "SessionAnalyzer"
    assert duration_metric.metadata == {
        "channel": ChannelNames.LATITUDE.value,
        "method": "max_timestamp_minus_min_timestamp",
    }

    assert len(result.provenance) == 3
    records = {record.produced_name: record for record in result.provenance}

    max_speed_record = records[MetricNames.MAX_BOAT_SPEED.value]
    assert max_speed_record.producer == "SessionAnalyzer"
    assert max_speed_record.produced_type == "metric"
    assert max_speed_record.inputs == [ChannelNames.SOG.value]
    assert max_speed_record.config == {
        "method": "max",
        "channel": ChannelNames.SOG.value,
    }
    assert max_speed_record.changes == [
        {
            "field": "value",
            "operation": "aggregate_max",
            "description": "Computed max session boat speed from speed samples",
        }
    ]

    distance_record = records[MetricNames.SESSION_DISTANCE.value]
    assert distance_record.producer == "SessionAnalyzer"
    assert distance_record.produced_type == "metric"
    assert distance_record.inputs == [
        ChannelNames.LATITUDE.value,
        ChannelNames.LONGITUDE.value,
    ]
    assert distance_record.config == {
        "method": "haversine_sum",
        "channels": [
            ChannelNames.LATITUDE.value,
            ChannelNames.LONGITUDE.value,
        ],
        "unit": "nm",
    }
    assert distance_record.changes == [
        {
            "field": "value",
            "operation": "aggregate_distance",
            "description": "Computed total session distance from lat/lon track",
        }
    ]

    duration_record = records[MetricNames.SESSION_DURATION.value]
    assert duration_record.producer == "SessionAnalyzer"
    assert duration_record.produced_type == "metric"
    assert duration_record.inputs == [ChannelNames.LATITUDE.value]
    assert duration_record.config == {
        "method": "max_minus_min_timestamp",
        "channel": ChannelNames.LATITUDE.value,
        "unit": "min",
    }
    assert duration_record.changes == [
        {
            "field": "value",
            "operation": "aggregate_duration",
            "description": "Computed session duration from lat timestamps",
        }
    ]


def test_analyze_calculates_session_distance_in_nautical_miles() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-distance"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([1.0, 2.0, 3.0]),
                values=np.array([0.0, 0.0, 0.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([1.0, 2.0, 3.0]),
                values=np.array([0.0, 0.5, 1.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=np.array([1.0, 2.0, 3.0]),
                values=np.array([4.3, 7.2, 6.8]),
                unit="kn",
                source="gps",
            ),
        },
    )
    analyzer = SessionAnalyzer()

    result = analyzer.analyze(session)

    distance_metric = result.get_metric(MetricNames.SESSION_DISTANCE.value)
    assert distance_metric.unit == "nm"
    assert distance_metric.value == pytest.approx(60.0405, abs=0.01)


def test_analyze_calculates_session_duration_in_minutes() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-duration"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([57.0, 57.0, 57.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([11.0, 11.0, 11.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([4.3, 7.2, 6.8]),
                unit="kn",
                source="gps",
            ),
        },
    )
    analyzer = SessionAnalyzer()

    result = analyzer.analyze(session)

    duration_metric = result.get_metric(MetricNames.SESSION_DURATION.value)
    assert duration_metric.unit == "min"
    assert duration_metric.value == pytest.approx(2.0)


def test_analyze_requires_boat_speed_channel() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-missing-boat-speed"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )
    analyzer = SessionAnalyzer()

    with pytest.raises(
        KeyError, match=rf"Missing required channels: \['{ChannelNames.SOG.value}'\]"
    ):
        analyzer.analyze(session)


def test_analyze_rejects_empty_boat_speed_samples(session: CanonicalSession) -> None:
    session.get_channel(ChannelNames.SOG.value).timestamps = np.array([], dtype=float)
    session.get_channel(ChannelNames.SOG.value).values = np.array([], dtype=float)
    analyzer = SessionAnalyzer()

    with pytest.raises(
        ValueError,
        match=rf"SessionAnalyzer requires '{ChannelNames.SOG.value}' to contain samples",
    ):
        analyzer.analyze(session)


def test_print_summary_outputs_session_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-summary"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([0.0, 0.0, 0.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([0.0, 0.5, 1.0]),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=np.array([0.0, 60.0, 120.0]),
                values=np.array([4.3, 7.2, 6.8]),
                unit="kn",
                source="gps",
            ),
        },
    )
    analyzer = SessionAnalyzer()

    result = analyzer.analyze(session)
    analyzer.print_summary()

    max_speed_metric = result.get_metric(MetricNames.MAX_BOAT_SPEED.value)
    distance_metric = result.get_metric(MetricNames.SESSION_DISTANCE.value)
    duration_metric = result.get_metric(MetricNames.SESSION_DURATION.value)
    assert capsys.readouterr().out == (
        f"{max_speed_metric.name}: {max_speed_metric.value} {max_speed_metric.unit}\n"
        f"{distance_metric.name}: {distance_metric.value} {distance_metric.unit}\n"
        f"{duration_metric.name}: {duration_metric.value} {duration_metric.unit}\n"
    )
