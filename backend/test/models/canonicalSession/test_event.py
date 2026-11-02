import pytest
from src.models.canonicalSession import Event


def test_event_valid_point_in_time():
    event = Event(event_type="tack", start_time=12.5, source="maneuverAnalyzer")

    assert event.event_type == "tack"
    assert event.start_time == 12.5
    assert event.end_time is None
    assert event.source == "maneuverAnalyzer"
    assert event.confidence is None
    assert event.metadata == {}


def test_event_valid_interval():
    event = Event(
        event_type="sensor_dropout",
        start_time=100.0,
        end_time=105.5,
        source="detector_a",
        confidence=0.92,
    )

    assert event.event_type == "sensor_dropout"
    assert event.start_time == 100.0
    assert event.end_time == 105.5
    assert event.source == "detector_a"
    assert event.confidence == 0.92
    assert event.foiling is False
    assert event.metadata == {}


def test_event_allows_end_time_equal_to_start_time():
    event = Event(
        event_type="mark_rounding",
        start_time=50.0,
        end_time=50.0,
        source="markRoundingAnalyzer",
    )

    assert event.start_time == 50.0
    assert event.end_time == 50.0


def test_event_raises_no_source_provided():
    with pytest.raises(
        ValueError,
        match=r"Event 'gybe' must have a source",
    ):
        Event(
            source=None,
            event_type="gybe",
            start_time=20.0,
        )


def test_event_raises_when_end_time_before_start_time():
    with pytest.raises(
        ValueError,
        match=r"Event 'gybe' end_time cannot be before start_time",
    ):
        Event(event_type="gybe", start_time=20.0, end_time=19.9, source="gyber3000")


def test_event_accepts_metadata():
    metadata = {"leg": 2, "watch": "port"}

    event = Event(
        event_type="start_crossing",
        start_time=5.0,
        metadata=metadata,
        source="crossMaster",
    )

    assert event.metadata == metadata


def test_event_accepts_foiling_flag() -> None:
    event = Event(
        event_type="gybe",
        start_time=8.0,
        source="maneuverAnalyzer",
        foiling=True,
    )

    assert event.foiling is True


def test_event_metadata_uses_independent_default_dict():
    event1 = Event(event_type="tack", start_time=1.0, source="atacker")
    event2 = Event(event_type="gybe", start_time=2.0, source="gyboo")

    event1.metadata["note"] = "first"

    assert event1.metadata == {"note": "first"}
    assert event2.metadata == {}
