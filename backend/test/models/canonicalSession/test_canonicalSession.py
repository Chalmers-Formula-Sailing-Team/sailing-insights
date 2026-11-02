from dataclasses import dataclass, field

import numpy as np
import pytest
from src.models.canonicalSession import (
    Artifact,
    CanonicalSession,
    Channel,
    Event,
    Metric,
    ProvenanceRecord,
    SessionMetadata,
)

# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture
def metadata() -> SessionMetadata:
    return SessionMetadata(
        session_id="session-123",
        source_type="garmin",
    )


@pytest.fixture
def lat_channel() -> Channel:
    return Channel(
        name="lat",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )


@pytest.fixture
def long_channel() -> Channel:
    return Channel(
        name="lon",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )


@pytest.fixture
def session(
    metadata: SessionMetadata,
    lat_channel: Channel,
    long_channel: Channel,
) -> CanonicalSession:
    return CanonicalSession(
        metadata=metadata,
        channels={"lat": lat_channel, "lon": long_channel},
    )


@pytest.fixture
def speed_channel() -> Channel:
    return Channel(
        name="speed",
        timestamps=np.array([10.0, 20.0, 30.0]),
        values=np.array([4.1, 4.5, 4.3]),
        unit="kn",
        source="gps",
    )


@pytest.fixture
def heel_channel() -> Channel:
    return Channel(
        name="heel",
        timestamps=np.array([5.0, 15.0, 25.0, 35.0]),
        values=np.array([8.0, 10.0, 6.0, 7.0]),
        unit="deg",
        source="imu",
    )


@pytest.fixture
def empty_channel() -> Channel:
    return Channel(
        name="empty",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="kn",
        source="derived",
    )


@pytest.fixture
def vmg_metric() -> Metric:
    return Metric(
        name="vmg_avg",
        value=5.4,
        unit="kn",
        source="vmg_analyzer",
    )


@pytest.fixture
def chart_artifact() -> Artifact:
    return Artifact(
        name="polar_chart",
        data={"url": "/tmp/polar.png"},
        artifact_type="chart",
        source="polar_analyzer",
    )


@pytest.fixture
def provenance_record() -> ProvenanceRecord:
    return ProvenanceRecord(
        producer="normalizer",
        produced_type="channel",
        produced_name="speed",
        inputs=["raw_gps_speed"],
        config={"method": "identity"},
    )


# -------------------------------------------------------------------
# Channel methods
# -------------------------------------------------------------------


def test_add_channel_stores_channel(
    session: CanonicalSession, speed_channel: Channel
) -> None:
    session.add_channel(speed_channel)

    assert "speed" in session.channels
    assert session.channels["speed"] is speed_channel


def test_canonical_session_requires_lat_and_long_channels(
    metadata: SessionMetadata, lat_channel: Channel
) -> None:
    with pytest.raises(
        ValueError,
        match=r"CanonicalSession requires channels: \['lat', 'lon'\]; missing \['lon'\]",
    ):
        CanonicalSession(metadata=metadata, channels={"lat": lat_channel})


def test_canonical_session_allows_minimal_lat_and_long_only(
    metadata: SessionMetadata, lat_channel: Channel, long_channel: Channel
) -> None:
    session = CanonicalSession(
        metadata=metadata,
        channels={"lat": lat_channel, "lon": long_channel},
    )

    assert set(session.channels) == {"lat", "lon"}


def test_canonical_session_raises_when_lat_and_lon_value_counts_differ(
    metadata: SessionMetadata,
) -> None:
    lat_channel = Channel(
        name="lat",
        timestamps=np.array([1.0, 2.0]),
        values=np.array([57.6680, 57.6681]),
        unit="deg",
        source="gps",
    )
    lon_channel = Channel(
        name="lon",
        timestamps=np.array([1.0]),
        values=np.array([11.8424]),
        unit="deg",
        source="gps",
    )

    with pytest.raises(
        ValueError, match="lat and lon channels must have same amount of values"
    ):
        CanonicalSession(
            metadata=metadata,
            channels={"lat": lat_channel, "lon": lon_channel},
        )


def test_add_channel_raises_on_duplicate_without_overwrite(
    session: CanonicalSession, speed_channel: Channel
) -> None:
    session.add_channel(speed_channel)

    with pytest.raises(ValueError, match="Channel 'speed' already exists"):
        session.add_channel(speed_channel)


def test_add_channel_allows_overwrite(session: CanonicalSession) -> None:
    original = Channel(
        name="speed",
        timestamps=np.array([1.0, 2.0]),
        values=np.array([3.0, 4.0]),
        unit="kn",
        source="gps",
    )
    replacement = Channel(
        name="speed",
        timestamps=np.array([10.0, 20.0]),
        values=np.array([6.0, 7.0]),
        unit="kn",
        source="derived",
        is_derived=True,
    )

    session.add_channel(original)
    session.add_channel(replacement, overwrite=True)

    assert session.get_channel("speed") is replacement


def test_get_channel_returns_channel(
    session: CanonicalSession, speed_channel: Channel
) -> None:
    session.add_channel(speed_channel)

    result = session.get_channel("speed")

    assert result is speed_channel


def test_get_channel_raises_key_error_with_clear_message(
    session: CanonicalSession,
) -> None:
    with pytest.raises(KeyError, match="Channel 'speed' not found"):
        session.get_channel("speed")


@pytest.mark.parametrize(
    ("channel_name", "expected"),
    [
        ("speed", True),
        ("heel", False),
    ],
)
def test_has_channel(
    session: CanonicalSession,
    speed_channel: Channel,
    channel_name: str,
    expected: bool,
) -> None:
    session.add_channel(speed_channel)

    assert session.has_channel(channel_name) is expected


def test_require_channels_passes_when_all_exist(
    session: CanonicalSession, speed_channel: Channel, heel_channel: Channel
) -> None:
    session.add_channel(speed_channel)
    session.add_channel(heel_channel)

    session.require_channels(["speed", "heel"])


def test_require_channels_raises_with_missing_names(
    session: CanonicalSession, speed_channel: Channel
) -> None:
    session.add_channel(speed_channel)

    with pytest.raises(KeyError, match=r"Missing required channels: \['heel', 'awa'\]"):
        session.require_channels(["speed", "heel", "awa"])


def test_require_channels_passes_for_empty_requirement_list(
    session: CanonicalSession,
) -> None:
    session.require_channels([])


# -------------------------------------------------------------------
# Event methods
# -------------------------------------------------------------------


def test_add_event_appends_event(session: CanonicalSession) -> None:
    event = Event(
        event_type="tack",
        start_time=100.0,
        end_time=110.0,
        source="maneuver_analyzer",
    )

    session.add_event(event)

    assert session.events == [event]


def test_get_events_returns_all_when_no_filters(session: CanonicalSession) -> None:
    e1 = Event(event_type="tack", start_time=10.0, end_time=15.0, source="analyzer")
    e2 = Event(event_type="gybe", start_time=20.0, end_time=25.0, source="analyzer")
    session.add_event(e1)
    session.add_event(e2)

    result = session.get_events()

    assert result == [e1, e2]


def test_get_events_filters_by_event_type(session: CanonicalSession) -> None:
    e1 = Event(event_type="tack", start_time=10.0, end_time=15.0, source="analyzer")
    e2 = Event(event_type="gybe", start_time=20.0, end_time=25.0, source="analyzer")
    e3 = Event(event_type="tack", start_time=30.0, end_time=35.0, source="analyzer")
    session.events.extend([e1, e2, e3])

    result = session.get_events(event_type="tack")

    assert result == [e1, e3]


def test_get_events_filters_by_start_time_inclusive(session: CanonicalSession) -> None:
    e1 = Event(event_type="tack", start_time=10.0, end_time=12.0, source="analyzer")
    e2 = Event(event_type="tack", start_time=20.0, end_time=22.0, source="analyzer")
    e3 = Event(event_type="tack", start_time=30.0, end_time=32.0, source="analyzer")
    session.events.extend([e1, e2, e3])

    result = session.get_events(start_time=20.0)

    assert result == [e2, e3]


def test_get_events_filters_by_end_time_inclusive(session: CanonicalSession) -> None:
    e1 = Event(event_type="tack", start_time=10.0, end_time=12.0, source="analyzer")
    e2 = Event(event_type="tack", start_time=20.0, end_time=25.0, source="analyzer")
    e3 = Event(event_type="tack", start_time=30.0, end_time=40.0, source="analyzer")
    session.events.extend([e1, e2, e3])

    result = session.get_events(end_time=25.0)

    assert result == [e1, e2]


def test_get_events_uses_start_time_when_event_end_time_is_none(
    session: CanonicalSession,
) -> None:
    instant_event = Event(
        event_type="mark_rounding",
        start_time=50.0,
        end_time=None,
        source="race_analyzer",
    )
    late_event = Event(
        event_type="mark_rounding",
        start_time=60.0,
        end_time=None,
        source="race_analyzer",
    )
    session.events.extend([instant_event, late_event])

    result = session.get_events(end_time=55.0)

    assert result == [instant_event]


def test_get_events_combines_all_filters(session: CanonicalSession) -> None:
    e1 = Event(event_type="tack", start_time=10.0, end_time=15.0, source="analyzer")
    e2 = Event(event_type="gybe", start_time=20.0, end_time=25.0, source="analyzer")
    e3 = Event(event_type="tack", start_time=30.0, end_time=35.0, source="analyzer")
    e4 = Event(event_type="tack", start_time=40.0, end_time=50.0, source="analyzer")
    session.events.extend([e1, e2, e3, e4])

    result = session.get_events(event_type="tack", start_time=25.0, end_time=40.0)

    assert result == [e3]


def test_get_events_returns_empty_list_when_nothing_matches(
    session: CanonicalSession,
) -> None:
    session.add_event(
        Event(event_type="tack", start_time=10.0, end_time=15.0, source="analyzer")
    )

    result = session.get_events(event_type="gybe")

    assert result == []


# -------------------------------------------------------------------
# Metric methods
# -------------------------------------------------------------------


def test_add_metric_stores_metric(
    session: CanonicalSession, vmg_metric: Metric
) -> None:
    session.add_metric(vmg_metric)

    assert session.metrics["vmg_avg"] is vmg_metric


def test_add_metric_raises_on_duplicate_without_overwrite(
    session: CanonicalSession,
) -> None:
    metric = Metric(name="vmg_avg", value=5.0, unit="kn", source="vmg_analyzer")
    session.add_metric(metric)

    with pytest.raises(ValueError, match="Metric 'vmg_avg' already exists"):
        session.add_metric(metric)


def test_add_metric_allows_overwrite(session: CanonicalSession) -> None:
    original = Metric(name="vmg_avg", value=5.0, unit="kn", source="vmg_v1")
    replacement = Metric(name="vmg_avg", value=6.2, unit="kn", source="vmg_v2")

    session.add_metric(original)
    session.add_metric(replacement, overwrite=True)

    assert session.get_metric("vmg_avg") is replacement
    assert session.get_metric("vmg_avg").value == 6.2


def test_get_metric_returns_metric(
    session: CanonicalSession, vmg_metric: Metric
) -> None:
    session.add_metric(vmg_metric)

    assert session.get_metric("vmg_avg") is vmg_metric


def test_get_metric_raises_key_error_with_clear_message(
    session: CanonicalSession,
) -> None:
    with pytest.raises(KeyError, match="Metric 'vmg_avg' not found"):
        session.get_metric("vmg_avg")


@pytest.mark.parametrize(
    ("metric_name", "expected"),
    [
        ("vmg_avg", True),
        ("distance_total", False),
    ],
)
def test_has_metric(
    session: CanonicalSession,
    vmg_metric: Metric,
    metric_name: str,
    expected: bool,
) -> None:
    session.add_metric(vmg_metric)

    assert session.has_metric(metric_name) is expected


# -------------------------------------------------------------------
# Artifact methods
# -------------------------------------------------------------------


def test_add_artifact_stores_artifact(
    session: CanonicalSession, chart_artifact: Artifact
) -> None:
    session.add_artifact(chart_artifact)

    assert session.artifacts["polar_chart"] is chart_artifact


def test_add_artifact_raises_on_duplicate_without_overwrite(
    session: CanonicalSession,
) -> None:
    artifact = Artifact(
        name="polar_chart",
        data={"a": 1},
        artifact_type="chart",
        source="analyzer",
    )
    session.add_artifact(artifact)

    with pytest.raises(ValueError, match="Artifact 'polar_chart' already exists"):
        session.add_artifact(artifact)


def test_add_artifact_allows_overwrite(session: CanonicalSession) -> None:
    original = Artifact(
        name="polar_chart",
        data={"version": 1},
        artifact_type="chart",
        source="polar_v1",
    )
    replacement = Artifact(
        name="polar_chart",
        data={"version": 2},
        artifact_type="chart",
        source="polar_v2",
    )

    session.add_artifact(original)
    session.add_artifact(replacement, overwrite=True)

    assert session.get_artifact("polar_chart") is replacement


def test_get_artifact_returns_artifact(
    session: CanonicalSession, chart_artifact: Artifact
) -> None:
    session.add_artifact(chart_artifact)

    assert session.get_artifact("polar_chart") is chart_artifact


def test_get_artifact_raises_key_error_with_clear_message(
    session: CanonicalSession,
) -> None:
    with pytest.raises(KeyError, match="Artifact 'polar_chart' not found"):
        session.get_artifact("polar_chart")


# -------------------------------------------------------------------
# Provenance methods
# -------------------------------------------------------------------


def test_add_provenance_appends_record(
    session: CanonicalSession, provenance_record: ProvenanceRecord
) -> None:
    session.add_provenance(provenance_record)

    assert session.provenance == [provenance_record]


def test_add_provenance_preserves_order(session: CanonicalSession) -> None:
    r1 = ProvenanceRecord(
        producer="extractor",
        produced_type="channel",
        produced_name="gps_speed",
    )
    r2 = ProvenanceRecord(
        producer="normalizer",
        produced_type="channel",
        produced_name="speed",
    )
    r3 = ProvenanceRecord(
        producer="vmg_analyzer",
        produced_type="metric",
        produced_name="vmg_avg",
    )

    session.add_provenance(r1)
    session.add_provenance(r2)
    session.add_provenance(r3)

    assert session.provenance == [r1, r2, r3]


# -------------------------------------------------------------------
# start_time property
# -------------------------------------------------------------------


def test_start_time_prefers_metadata_started_at(
    session: CanonicalSession, speed_channel: Channel, heel_channel: Channel
) -> None:
    session.metadata.start_at = 999.0
    session.add_channel(speed_channel)
    session.add_channel(heel_channel)

    assert session.start_time == 999.0


def test_start_time_returns_none_when_no_metadata_and_no_channels(
    metadata: SessionMetadata,
) -> None:
    session = CanonicalSession(
        metadata=metadata,
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    assert session.start_time is None


def test_start_time_derived_from_earliest_non_empty_channel(
    session: CanonicalSession, speed_channel: Channel, heel_channel: Channel
) -> None:
    session.add_channel(speed_channel)  # starts at 10
    session.add_channel(heel_channel)

    assert session.start_time == 5.0


def test_start_time_ignores_empty_channels(
    session: CanonicalSession, speed_channel: Channel, empty_channel: Channel
) -> None:
    session.add_channel(empty_channel)
    session.add_channel(speed_channel)

    assert session.start_time == 10.0


def test_start_time_returns_none_when_all_channels_empty(
    metadata: SessionMetadata,
) -> None:
    session = CanonicalSession(
        metadata=metadata,
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    another_empty = Channel(
        name="empty_speed",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="derived",
    )
    session.add_channel(another_empty)

    assert session.start_time is None


# -------------------------------------------------------------------
# end_time property
# -------------------------------------------------------------------


def test_end_time_prefers_metadata_ended_at(
    session: CanonicalSession, speed_channel: Channel, heel_channel: Channel
) -> None:
    session.metadata.end_at = 1234.0
    session.add_channel(speed_channel)
    session.add_channel(heel_channel)

    assert session.end_time == 1234.0


def test_end_time_returns_none_when_no_metadata_and_no_channels(
    metadata: SessionMetadata,
) -> None:
    session = CanonicalSession(
        metadata=metadata,
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    assert session.end_time is None


def test_end_time_derived_from_latest_non_empty_channel(
    session: CanonicalSession, speed_channel: Channel, heel_channel: Channel
) -> None:
    session.add_channel(speed_channel)  # ends at 30
    session.add_channel(heel_channel)  # ends at 35

    assert session.end_time == 35.0


def test_end_time_ignores_empty_channels(
    session: CanonicalSession, speed_channel: Channel, empty_channel: Channel
) -> None:
    session.add_channel(empty_channel)
    session.add_channel(speed_channel)

    assert session.end_time == 30.0


def test_end_time_returns_none_when_all_channels_empty(
    metadata: SessionMetadata,
) -> None:
    session = CanonicalSession(
        metadata=metadata,
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    another_empty = Channel(
        name="empty_speed",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="derived",
    )
    session.add_channel(another_empty)

    assert session.end_time is None


# -------------------------------------------------------------------
# summary
# -------------------------------------------------------------------


def test_summary_returns_expected_counts_and_identity_fields(
    session: CanonicalSession,
    speed_channel: Channel,
    heel_channel: Channel,
    vmg_metric: Metric,
    chart_artifact: Artifact,
) -> None:
    session.add_channel(speed_channel)
    session.add_channel(heel_channel)
    session.add_event(
        Event(
            event_type="tack",
            start_time=12.0,
            end_time=14.0,
            source="maneuver_analyzer",
        )
    )
    session.add_event(
        Event(
            event_type="gybe",
            start_time=20.0,
            end_time=21.0,
            source="maneuver_analyzer",
        )
    )
    session.add_metric(vmg_metric)
    session.add_artifact(chart_artifact)

    result = session.summary()

    assert result == {
        "session_id": "session-123",
        "source_type": "garmin",
        "channel_count": 4,
        "event_count": 2,
        "metric_count": 1,
        "artifact_count": 1,
        "start_time": 5.0,
        "end_time": 35.0,
    }


def test_summary_uses_metadata_times_when_present(session: CanonicalSession) -> None:
    session.metadata.start_at = 111.0
    session.metadata.end_at = 222.0

    result = session.summary()

    assert result["start_time"] == 111.0
    assert result["end_time"] == 222.0


def test_summary_for_minimal_session_has_required_channels_and_times(
    metadata: SessionMetadata,
) -> None:
    session = CanonicalSession(
        metadata=metadata,
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    result = session.summary()

    assert result == {
        "session_id": "session-123",
        "source_type": "garmin",
        "channel_count": 2,
        "event_count": 0,
        "metric_count": 0,
        "artifact_count": 0,
        "start_time": None,
        "end_time": None,
    }
