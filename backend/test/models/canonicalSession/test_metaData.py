import pytest
from src.models.canonicalSession import SessionMetadata


def test_session_metadata_valid_minimal():
    metadata = SessionMetadata(session_id="session_001")

    assert metadata.session_id == "session_001"
    assert metadata.source_type is None
    assert metadata.athlete_id is None
    assert metadata.boat_id is None
    assert metadata.start_at is None
    assert metadata.end_at is None
    assert metadata.timezone is None
    assert metadata.location is None
    assert metadata.notes is None
    assert metadata.labels == {}
    assert metadata.extras == {}


def test_session_metadata_valid_with_all_fields():
    labels = {"venue": "palma", "mode": "training"}
    extras = {"coach": "alice", "device_fw": "1.2.3"}

    metadata = SessionMetadata(
        session_id="session_002",
        source_type="garmin",
        athlete_id="ath_123",
        boat_id="boat_456",
        start_at=1710000000.0,
        end_at=1710003600.0,
        timezone="Europe/Stockholm",
        location="Langedrag",
        notes="Short debrief note",
        labels=labels,
        extras=extras,
    )

    assert metadata.session_id == "session_002"
    assert metadata.source_type == "garmin"
    assert metadata.athlete_id == "ath_123"
    assert metadata.boat_id == "boat_456"
    assert metadata.start_at == 1710000000.0
    assert metadata.end_at == 1710003600.0
    assert metadata.timezone == "Europe/Stockholm"
    assert metadata.location == "Langedrag"
    assert metadata.notes == "Short debrief note"
    assert metadata.labels == labels
    assert metadata.extras == extras


def test_session_metadata_accepts_empty_strings():
    metadata = SessionMetadata(
        session_id="",
        source_type="",
        athlete_id="",
        boat_id="",
        timezone="",
        location="",
        notes="",
    )

    assert metadata.session_id == ""
    assert metadata.source_type == ""
    assert metadata.athlete_id == ""
    assert metadata.boat_id == ""
    assert metadata.timezone == ""
    assert metadata.location == ""
    assert metadata.notes == ""


def test_session_metadata_accepts_zero_values():
    metadata = SessionMetadata(
        session_id="session_003",
        start_at=0.0,
        end_at=0.0,
    )

    assert metadata.start_at == 0.0
    assert metadata.end_at == 0.0


def test_session_metadata_labels_uses_independent_default_dict():
    metadata1 = SessionMetadata(session_id="session_001")
    metadata2 = SessionMetadata(session_id="session_002")

    metadata1.labels["venue"] = "cascais"

    assert metadata1.labels == {"venue": "cascais"}
    assert metadata2.labels == {}


def test_session_metadata_extras_uses_independent_default_dict():
    metadata1 = SessionMetadata(session_id="session_001")
    metadata2 = SessionMetadata(session_id="session_002")

    metadata1.extras["import_batch"] = 7

    assert metadata1.extras == {"import_batch": 7}
    assert metadata2.extras == {}


def test_session_metadata_labels_and_extras_are_independent_on_same_instance():
    metadata = SessionMetadata(session_id="session_004")

    metadata.labels["campaign"] = "spring"
    metadata.extras["campaign"] = {"id": 1}

    assert metadata.labels == {"campaign": "spring"}
    assert metadata.extras == {"campaign": {"id": 1}}


def test_session_metadata_allows_start_before_end():
    metadata = SessionMetadata(
        session_id="session_005",
        start_at=100.0,
        end_at=200.0,
    )

    assert metadata.start_at == 100.0
    assert metadata.end_at == 200.0


def test_session_metadata_raises_if_end_before_start():
    with pytest.raises(
        ValueError,
    ):
        SessionMetadata(
            session_id="session_007",
            start_at=200.0,
            end_at=100.0,
        )
