from datetime import datetime, timedelta, timezone
import uuid

import numpy as np

import src.persistence.sessionPersistence as session_persistence_module
from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.persistence.sessionPersistence import SessionPersistence


class _RecordingCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.executed_many: list[tuple[str, list[tuple[object, ...]]]] = []

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN204, ANN001
        return False

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executed.append((query, params))

    def executemany(self, query: str, params_seq) -> None:  # noqa: ANN001
        self.executed_many.append((query, list(params_seq)))


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _RecordingCursor:
        return self._cursor


def test_resolve_channel_data_target_routes_numeric_values_to_real_table() -> None:
    persistence = SessionPersistence()

    table_name, converter = persistence._resolve_channel_data_target(
        np.array([1, 2, 3], dtype=np.int64)
    )

    assert table_name == SessionPersistence.CHANNEL_DATA_TABLE_REAL
    assert converter(3) == 3.0


def test_resolve_channel_data_target_routes_boolean_values_to_boolean_table() -> None:
    persistence = SessionPersistence()

    table_name, converter = persistence._resolve_channel_data_target(
        np.array([True, False], dtype=np.bool_)
    )

    assert table_name == SessionPersistence.CHANNEL_DATA_TABLE_BOOLEAN
    assert converter("true") is True
    assert converter("0") is False


def test_resolve_channel_data_target_routes_string_values_to_string_table() -> None:
    persistence = SessionPersistence()

    table_name, converter = persistence._resolve_channel_data_target(
        np.array(["a", "b", "c"], dtype=str)
    )

    assert table_name == SessionPersistence.CHANNEL_DATA_TABLE_STRING
    assert converter(42) == "42"


def test_coerce_timestamp_array_converts_datetime64_and_nat() -> None:
    persistence = SessionPersistence()
    timestamps = np.array(
        ["2025-01-01T00:00:00.123", "NaT", "2025-01-01T00:00:01.456"],
        dtype="datetime64[ms]",
    )

    converted = persistence._coerce_timestamp_array(timestamps)

    assert converted == [
        datetime(2025, 1, 1, 0, 0, 0, 123000, tzinfo=timezone.utc),
        None,
        datetime(2025, 1, 1, 0, 0, 1, 456000, tzinfo=timezone.utc),
    ]


def test_coerce_timestamp_array_converts_numeric_epoch_seconds() -> None:
    persistence = SessionPersistence()
    timestamps = np.array([0.0, 61.5, np.nan], dtype=np.float64)

    converted = persistence._coerce_timestamp_array(timestamps)

    assert converted == [
        datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        datetime(1970, 1, 1, 0, 1, 1, 500000, tzinfo=timezone.utc),
        None,
    ]


def test_coerce_timestamp_array_normalizes_timezone_aware_datetimes_to_utc() -> None:
    persistence = SessionPersistence()
    timestamps = np.array(
        [
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=2))),
        ],
        dtype=object,
    )

    converted = persistence._coerce_timestamp_array(timestamps)

    assert converted == [
        datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
    ]


def test_coerce_session_id_generates_deterministic_uuid_for_non_uuid_inputs() -> None:
    persistence = SessionPersistence()

    generated = persistence._coerce_session_id("session-123")

    assert generated == uuid.uuid5(uuid.NAMESPACE_URL, "session-123")


def test_coerce_session_id_preserves_valid_uuid() -> None:
    persistence = SessionPersistence()
    expected = uuid.uuid4()

    generated = persistence._coerce_session_id(str(expected))

    assert generated == expected


def test_connect_from_env_reads_postgres_credentials_from_root_dotenv_when_missing(
    monkeypatch, tmp_path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POSTGRES_HOST=10.0.0.10",
                "POSTGRES_PORT=6543",
                "POSTGRES_DB=demo_db",
                "POSTGRES_USER=demo_user",
                "POSTGRES_PASSWORD=demo_pw",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(SessionPersistence, "ROOT_ENV_PATH", env_path)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    captured_kwargs: dict[str, str] = {}

    def fake_connect(**kwargs):  # noqa: ANN003
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr(session_persistence_module.psycopg, "connect", fake_connect)

    persistence = SessionPersistence()
    _ = persistence._connect_from_env()

    assert captured_kwargs == {
        "host": "10.0.0.10",
        "port": "6543",
        "dbname": "demo_db",
        "user": "demo_user",
        "password": "demo_pw",
        "options": "-c timezone=UTC",
    }


def test_upsert_session_row_does_not_write_manual_wind_columns() -> None:
    persistence = SessionPersistence()
    cursor = _RecordingCursor()
    connection = _RecordingConnection(cursor)
    session_id = uuid.uuid4()

    session = CanonicalSession(
        metadata=SessionMetadata(
            session_id=str(session_id),
            session_name="Morning session",
            source_type="garmin",
            athlete_id="athlete-1",
            boat_id="boat-1",
            start_at=np.datetime64("2025-01-01T10:00:00"),
            end_at=np.datetime64("2025-01-01T11:00:00"),
            location="Langedrag",
            notes="Crew felt locked in after the first two drills.",
        ),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array(["2025-01-01T10:00:00"], dtype="datetime64[ms]"),
                values=np.array([57.7], dtype=float),
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array(["2025-01-01T10:00:00"], dtype="datetime64[ms]"),
                values=np.array([11.9], dtype=float),
            ),
        },
    )

    persistence._upsert_session_row(connection, session, session_id, uuid.uuid4())

    assert len(cursor.executed) == 1
    query, params = cursor.executed[0]
    assert "wind_amt_manual" not in query
    assert "wind_dir_manual" not in query
    assert "location" in query
    assert "notes" in query
    assert len(params) == 9
    assert params[-2] == "Langedrag"


def test_insert_events_persists_foiling_flag() -> None:
    from src.models.canonicalSession import Event

    persistence = SessionPersistence()
    cursor = _RecordingCursor()
    connection = _RecordingConnection(cursor)
    session_id = uuid.uuid4()
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-with-event"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([0.0], dtype=float),
                values=np.array([57.7], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([0.0], dtype=float),
                values=np.array([11.9], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
        events=[
            Event(
                event_type="tack",
                start_time=0.0,
                source="ManeuverAnalyzer",
                foiling=True,
            )
        ],
    )

    persistence._insert_events(connection, session, session_id)

    assert len(cursor.executed_many) == 1
    query, rows = cursor.executed_many[0]
    assert "foiling" in query
    assert len(rows) == 1
    assert rows[0][7] is True
