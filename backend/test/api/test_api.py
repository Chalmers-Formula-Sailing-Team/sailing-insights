import asyncio
import json
from datetime import datetime, timezone
from tempfile import SpooledTemporaryFile

import numpy as np
import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from src.api import api as api_module
from src.api import session_data as session_data_module
from src.api.exporters import SessionExportBundle

from src import api


def make_upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(filename=filename, file=file)


@pytest.fixture
def api_test_context(tmp_path, monkeypatch):  # noqa: ANN001
    called_jobs = []

    def fake_process_job(self, job) -> None:  # noqa: ANN001
        called_jobs.append(job)

    monkeypatch.setattr(api, "JOB_PAYLOAD_ROOT", tmp_path)
    monkeypatch.setattr(api_module, "JOB_PAYLOAD_ROOT", tmp_path)
    monkeypatch.setattr(api_module.JobProcessor, "process_job", fake_process_job)
    api._jobs.clear()

    return called_jobs, tmp_path


def test_create_session_job_uploads_files_and_triggers_pipeline(
    api_test_context,
) -> None:
    called_jobs, tmp_path = api_test_context
    background_tasks = BackgroundTasks()
    response = asyncio.run(
        api.create_session_job(
            background_tasks=background_tasks,
            tcx_file=make_upload_file("session.tcx", b"<tcx/>"),
            metadata_json=make_upload_file(
                "metadata.json", b'{"sessionName": "Training"}'
            ),
        )
    )

    assert response.status == "queued"
    assert response.job_id

    for task in background_tasks.tasks:
        task.func(*task.args, **task.kwargs)

    assert len(called_jobs) == 1

    called_job = called_jobs[0]
    assert called_job.session_path.endswith("session.tcx")
    assert called_job.meta_path.endswith("metadata.json")
    assert (tmp_path / response.job_id / "session.tcx").exists()
    stored_metadata = json.loads(
        (tmp_path / response.job_id / "metadata.json").read_text(encoding="utf-8")
    )
    assert stored_metadata == {"sessionName": "Training"}


def test_create_session_job_accepts_fit_uploads_and_preserves_suffix(
    api_test_context,
) -> None:
    called_jobs, tmp_path = api_test_context
    background_tasks = BackgroundTasks()
    response = asyncio.run(
        api.create_session_job(
            background_tasks=background_tasks,
            tcx_file=make_upload_file("session.fit", b"FITDATA"),
            metadata_json=make_upload_file(
                "metadata.json", b'{"sessionName": "Training"}'
            ),
        )
    )

    for task in background_tasks.tasks:
        task.func(*task.args, **task.kwargs)

    assert len(called_jobs) == 1

    called_job = called_jobs[0]
    assert called_job.session_path.endswith("session.fit")
    assert called_job.meta_path.endswith("metadata.json")
    assert (tmp_path / response.job_id / "session.fit").exists()


def test_create_session_job_accepts_csv_uploads_and_preserves_suffix(
    api_test_context,
) -> None:
    called_jobs, tmp_path = api_test_context
    background_tasks = BackgroundTasks()
    response = asyncio.run(
        api.create_session_job(
            background_tasks=background_tasks,
            tcx_file=make_upload_file("session.csv", b"time,latitude,longitude\n"),
            metadata_json=make_upload_file(
                "metadata.json", b'{"sessionName": "Training"}'
            ),
        )
    )

    for task in background_tasks.tasks:
        task.func(*task.args, **task.kwargs)

    assert len(called_jobs) == 1

    called_job = called_jobs[0]
    assert called_job.session_path.endswith("session.csv")
    assert called_job.meta_path.endswith("metadata.json")
    assert (tmp_path / response.job_id / "session.csv").exists()


class _DummyConnection:
    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN204, ANN001
        return False


class _RecordingCursor:
    def __init__(self, row: dict | None = None, rows: list[dict] | None = None) -> None:
        self.row = row
        self.rows = rows or []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN204, ANN001
        return False

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> dict | None:
        return self.row

    def fetchall(self) -> list[dict]:
        return self.rows


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self, row_factory=None):  # noqa: ANN001, ARG002
        return self._cursor


class _SequentialCursor:
    def __init__(self, rows_by_fetch: list[list[dict]]) -> None:
        self.rows_by_fetch = rows_by_fetch
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN204, ANN001
        return False

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executed.append((query, params))

    def fetchall(self) -> list[dict]:
        return self.rows_by_fetch.pop(0)


class _SequentialConnection:
    def __init__(self, cursor: _SequentialCursor) -> None:
        self._cursor = cursor

    def cursor(self, row_factory=None):  # noqa: ANN001, ARG002
        return self._cursor


def test_get_dashboard_overview_aggregates_boat_and_session_numbers(
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_boat_rows",
        lambda _connection: [
            {"id": "boat-1", "name": "SIPS", "class_name": "Waszp"},
            {"id": "boat-2", "name": "Herr Nielson", "class_name": "Yngling"},
        ],
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_rows",
        lambda _connection: [
            {
                "id": "session-1",
                "boat_id": "boat-1",
                "boat_name": "SIPS",
                "name": "Training morning",
                "location": "Langedrag",
                "start_at": None,
                "end_at": None,
                "notes": "Line drills and speed focus.",
                "duration_hours": 1.5,
                "distance_nm": 12.0,
                "max_speed_kts": 18.2,
                "foiling_time_min": 45.0,
                "foiling_percentage": 50.0,
                "tack_count": 6.0,
                "gybe_count": 3.0,
                "foiling_tack_count": 4.0,
                "foiling_gybe_count": 1.0,
                "foiling_tack_percentage": 66.7,
                "foiling_gybe_percentage": 33.3,
                "manual_wind_speed_kts": 12.0,
                "manual_wind_gust_kts": 17.0,
                "manual_wind_direction_deg": 210.0,
                "manual_wave_height_m": 0.7,
                "external_wind_speed_kts": 14.0,
                "external_wind_gust_kts": 18.0,
                "external_wind_direction_deg": 220.0,
                "wind_speed_kts": 14.0,
                "wind_gust_kts": 18.0,
                "wind_direction_deg": 220.0,
                "wave_height_m": 0.7,
            },
            {
                "id": "session-2",
                "boat_id": "boat-1",
                "boat_name": "SIPS",
                "name": "Training afternoon",
                "location": "Garda",
                "start_at": None,
                "end_at": None,
                "notes": None,
                "duration_hours": 2.25,
                "distance_nm": 19.4,
                "max_speed_kts": 20.1,
                "foiling_time_min": 81.0,
                "foiling_percentage": 60.0,
                "tack_count": 4.0,
                "gybe_count": 2.0,
                "foiling_tack_count": 2.0,
                "foiling_gybe_count": 1.0,
                "foiling_tack_percentage": 50.0,
                "foiling_gybe_percentage": 50.0,
                "manual_wind_speed_kts": None,
                "manual_wind_gust_kts": None,
                "manual_wind_direction_deg": None,
                "manual_wave_height_m": 0.9,
                "external_wind_speed_kts": 17.0,
                "external_wind_gust_kts": 22.0,
                "external_wind_direction_deg": 230.0,
                "wind_speed_kts": 17.0,
                "wind_gust_kts": 22.0,
                "wind_direction_deg": 230.0,
                "wave_height_m": 0.9,
            },
            {
                "id": "session-3",
                "boat_id": "boat-2",
                "boat_name": "Herr Nielson",
                "name": "Crew block",
                "location": None,
                "start_at": None,
                "end_at": None,
                "notes": None,
                "duration_hours": 1.0,
                "distance_nm": 8.1,
                "max_speed_kts": 12.5,
                "foiling_time_min": 12.0,
                "foiling_percentage": 20.0,
                "tack_count": 1.0,
                "gybe_count": 1.0,
                "foiling_tack_count": 0.0,
                "foiling_gybe_count": 0.0,
                "foiling_tack_percentage": 0.0,
                "foiling_gybe_percentage": 0.0,
                "manual_wind_speed_kts": 11.0,
                "manual_wind_gust_kts": 14.0,
                "manual_wind_direction_deg": 170.0,
                "manual_wave_height_m": 0.4,
                "external_wind_speed_kts": 12.0,
                "external_wind_gust_kts": 15.0,
                "external_wind_direction_deg": 180.0,
                "wind_speed_kts": 12.0,
                "wind_gust_kts": 15.0,
                "wind_direction_deg": 180.0,
                "wave_height_m": 0.4,
            },
        ],
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_track_points_by_session_id",
        lambda _connection, _session_ids: {
            "session-1": [
                api.DashboardTrackPoint(latitude=57.6761, longitude=11.8248),
                api.DashboardTrackPoint(latitude=57.6773, longitude=11.8262),
            ],
            "session-2": [
                api.DashboardTrackPoint(latitude=57.6801, longitude=11.8284),
            ],
        },
    )

    response = api.get_dashboard_overview()

    assert response.boat_count == 2
    assert response.session_count == 3
    assert response.total_hours == pytest.approx(4.75)
    assert response.total_distance_nm == pytest.approx(39.5)

    boats = {boat.id: boat for boat in response.boats}
    assert boats["boat-1"].session_count == 2
    assert boats["boat-1"].total_hours == pytest.approx(3.75)
    assert boats["boat-1"].total_distance_nm == pytest.approx(31.4)
    assert boats["boat-1"].max_speed_kts == pytest.approx(20.1)
    assert boats["boat-2"].session_count == 1
    sessions = {session.id: session for session in response.sessions}
    assert sessions["session-1"].foiling_time_min == pytest.approx(45.0)
    assert sessions["session-1"].foiling_percentage == pytest.approx(50.0)
    assert sessions["session-1"].tack_count == pytest.approx(6.0)
    assert sessions["session-1"].gybe_count == pytest.approx(3.0)
    assert sessions["session-1"].foiling_tack_count == pytest.approx(4.0)
    assert sessions["session-1"].foiling_gybe_count == pytest.approx(1.0)
    assert sessions["session-1"].foiling_tack_percentage == pytest.approx(66.7)
    assert sessions["session-1"].foiling_gybe_percentage == pytest.approx(33.3)
    assert sessions["session-1"].wave_height_m == pytest.approx(0.7)
    assert sessions["session-1"].manual_wind_speed_kts == pytest.approx(12.0)
    assert sessions["session-1"].manual_wind_gust_kts == pytest.approx(17.0)
    assert sessions["session-1"].external_wind_gust_kts == pytest.approx(18.0)
    assert sessions["session-1"].location == "Langedrag"
    assert sessions["session-1"].notes == "Line drills and speed focus."
    assert len(sessions["session-1"].track_points) == 2
    assert sessions["session-2"].track_points[0].latitude == pytest.approx(57.6801)
    assert sessions["session-3"].track_points == []


def test_get_dashboard_overview_returns_503_on_database_error(monkeypatch) -> None:
    def _raise_connection_error():
        raise RuntimeError("connection failed")

    monkeypatch.setattr(api_module, "_connect_postgres", _raise_connection_error)

    with pytest.raises(HTTPException) as exc_info:
        api.get_dashboard_overview()

    assert exc_info.value.status_code == 503


def test_create_boat_returns_created_boat(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())

    def fake_create_boat(_connection, payload):  # noqa: ANN001
        assert payload.name == "SAGA"
        assert payload.class_name == "SuMoth"
        assert payload.sailnumber == "SWE 1"
        return (
            "created",
            api.BoatResponse(
                id="boat-3",
                name=payload.name,
                class_name=payload.class_name,
                sailnumber=payload.sailnumber,
            ),
        )

    monkeypatch.setattr(api_module, "_create_boat", fake_create_boat)

    response = api.create_boat(
        api.BoatWriteRequest(name="SAGA", class_name="SuMoth", sailnumber="SWE 1")
    )

    assert response.id == "boat-3"
    assert response.class_name == "SuMoth"


def test_update_boat_returns_404_for_unknown_boat(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_update_boat",
        lambda _connection, _id, _payload: ("not_found", None),
    )

    with pytest.raises(HTTPException) as exc_info:
        api.update_boat(
            "missing-boat",
            api.BoatWriteRequest(name="SAGA", class_name="SuMoth", sailnumber="SWE 1"),
        )

    assert exc_info.value.status_code == 404


def test_delete_boat_returns_no_content_when_deleted(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(api_module, "_delete_boat", lambda _connection, _id: "deleted")

    response = api.delete_boat("boat-with-sessions")

    assert response.status_code == 204


def test_delete_boat_deletes_sessions_before_boat() -> None:
    cursor = _RecordingCursor(row={"id": "boat-1"})
    connection = _RecordingConnection(cursor)

    result = api_module._delete_boat(connection, "boat-1")

    assert result == "deleted"
    assert len(cursor.executed) == 3
    assert "SELECT id::text AS id" in cursor.executed[0][0]
    assert "DELETE FROM session" in cursor.executed[1][0]
    assert cursor.executed[1][1] == ("boat-1",)
    assert "DELETE FROM boat" in cursor.executed[2][0]


def test_update_session_returns_updated_session(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())

    def fake_update_session(_connection, session_id, payload):  # noqa: ANN001
        assert session_id == "session-1"
        assert payload.name == "Training"
        assert payload.location == "Langedrag"
        assert payload.notes == "Updated note"
        return (
            "updated",
            api.SessionResponse(
                id=session_id,
                name=payload.name,
                location=payload.location,
                notes=payload.notes,
            ),
        )

    monkeypatch.setattr(api_module, "_update_session", fake_update_session)

    response = api.update_session(
        "session-1",
        api.SessionWriteRequest(
            name="Training",
            location="Langedrag",
            notes="Updated note",
        ),
    )

    assert response.id == "session-1"
    assert response.location == "Langedrag"


def test_delete_session_returns_no_content_when_deleted(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module, "_delete_session", lambda _connection, _id: "deleted"
    )

    response = api.delete_session("session-1")

    assert response.status_code == 204


def test_delete_session_deletes_session_row() -> None:
    cursor = _RecordingCursor(row={"id": "session-1"})
    connection = _RecordingConnection(cursor)

    result = api_module._delete_session(connection, "session-1")

    assert result == "deleted"
    assert len(cursor.executed) == 1
    assert "DELETE FROM session" in cursor.executed[0][0]
    assert cursor.executed[0][1] == ("session-1",)


def test_update_session_race_returns_updated_race(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())

    start_time = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    finish_time = datetime(2026, 6, 1, 10, 15, tzinfo=timezone.utc)

    def fake_update_session_race(  # noqa: ANN001
        _connection, session_id, race_id, name, start_at, finish_at
    ):
        assert session_id == "session-1"
        assert race_id == "race-1"
        assert name == "Race 1"
        assert start_at == start_time
        assert finish_at == finish_time
        return api.SessionRace(
            id=race_id,
            session_id=session_id,
            name=name,
            start_time=start_at,
            finish_time=finish_at,
        )

    monkeypatch.setattr(api_module, "_update_session_race", fake_update_session_race)

    response = api.update_session_race(
        "session-1",
        "race-1",
        api.SessionRaceCreateRequest(
            name="Race 1",
            start_time=start_time,
            finish_time=finish_time,
        ),
    )

    assert response.id == "race-1"
    assert response.name == "Race 1"


def test_delete_session_race_returns_no_content_when_deleted(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module, "_delete_session_race", lambda _connection, _sid, _rid: True
    )

    response = api.delete_session_race("session-1", "race-1")

    assert response.status_code == 204


def test_delete_session_race_deletes_matching_row() -> None:
    cursor = _RecordingCursor(row={"id": "race-1"})
    connection = _RecordingConnection(cursor)

    result = api_module._delete_session_race(connection, "session-1", "race-1")

    assert result is True
    assert len(cursor.executed) == 1
    assert "DELETE FROM race" in cursor.executed[0][0]
    assert cursor.executed[0][1] == ("session-1", "race-1")


def test_fetch_session_rows_falls_back_to_manual_wind_metrics() -> None:
    cursor = _RecordingCursor(
        rows=[
            {
                "id": "session-1",
                "name": "Training morning",
                "start_at": None,
                "end_at": None,
                "boat_id": "boat-1",
                "boat_name": "SIPS",
                "location": "Langedrag",
                "notes": "Sea breeze filled in late.",
                "duration_hours": 1.5,
                "distance_nm": 12.0,
                "max_speed_kts": 18.2,
                "foiling_time_min": 45.0,
                "foiling_percentage": 50.0,
                "tack_count": 3.0,
                "gybe_count": 1.0,
                "foiling_tack_count": 2.0,
                "foiling_gybe_count": 1.0,
                "foiling_tack_percentage": 66.7,
                "foiling_gybe_percentage": 100.0,
                "manual_wind_speed_kts": 14.0,
                "manual_wind_gust_kts": 19.0,
                "manual_wind_direction_deg": 220.0,
                "manual_wave_height_m": 0.8,
                "external_wind_speed_kts": None,
                "external_wind_gust_kts": None,
                "external_wind_direction_deg": None,
                "wind_speed_kts": 14.0,
                "wind_gust_kts": None,
                "wind_direction_deg": 220.0,
                "wave_height_m": 0.8,
            }
        ]
    )
    connection = _RecordingConnection(cursor)

    rows = api._fetch_session_rows(connection)

    assert rows[0]["wind_speed_kts"] == pytest.approx(14.0)
    assert rows[0]["wind_gust_kts"] == pytest.approx(19.0)
    assert rows[0]["manual_wind_speed_kts"] == pytest.approx(14.0)
    assert rows[0]["manual_wind_gust_kts"] == pytest.approx(19.0)
    assert rows[0]["external_wind_speed_kts"] is None
    assert rows[0]["wind_direction_deg"] == pytest.approx(220.0)
    assert rows[0]["wave_height_m"] == pytest.approx(0.8)
    query, params = cursor.executed[0]
    assert "manual_wind_speed_kts" in query
    assert "manual_wind_gust_kts" in query
    assert "manual_wind_direction_deg" in query
    assert "manual_wave_height_m" in query
    assert "s.location" in query
    assert "tack_count" in query
    assert "gybe_count" in query
    assert "foiling_tack_count" in query
    assert "foiling_gybe_count" in query
    assert "foiling_tack_percentage" in query
    assert "foiling_gybe_percentage" in query
    assert params == (
        "manual_wind_speed_kn",
        "manual_wind_gust_kn",
        "manual_wind_direction_deg",
        "manual_wave_height_m",
    )


def test_fetch_session_data_session_falls_back_to_manual_wind_metrics() -> None:
    timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    cursor = _RecordingCursor(
        row={
            "id": "session-1",
            "name": "Training morning",
            "start_at": timestamp,
            "end_at": timestamp,
            "boat_id": "boat-1",
            "boat_name": "SIPS",
            "source": "garmin",
            "notes": "Crew timing got better each start.",
            "wind_speed_kts": 14.0,
            "wind_gust_kts": None,
            "wind_direction_deg": 220.0,
            "wave_height_m": 0.9,
        }
    )
    connection = _RecordingConnection(cursor)

    session = api._fetch_session_data_session(connection, "session-1")

    assert session is not None
    assert session.wind_speed_kts == pytest.approx(14.0)
    assert session.wind_direction_deg == pytest.approx(220.0)
    assert session.wave_height_m == pytest.approx(0.9)
    assert session.notes == "Crew timing got better each start."
    query, params = cursor.executed[0]
    assert "COALESCE" in query
    assert "AS wave_height_m" in query
    assert params == (
        "manual_wind_speed_kn",
        "manual_wind_direction_deg",
        "manual_wave_height_m",
        "session-1",
    )


def test_get_session_data_returns_all_persisted_session_payload(monkeypatch) -> None:
    timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    session = api.SessionDataSession(
        id="session-1",
        name="Training morning",
        start_at=timestamp,
        end_at=timestamp,
        boat_id="boat-1",
        boat_name="SIPS",
        source="garmin",
        notes="Short note",
        wind_speed_kts=14.0,
        wind_gust_kts=18.0,
        wind_direction_deg=220.0,
        wave_height_m=0.6,
    )
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_session",
        lambda _connection, session_id: session if session_id == "session-1" else None,
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_channels",
        lambda _connection, _session_id: [
            api.SessionDataChannel(
                id="channel-1",
                name="boat_speed",
                unit="kt",
                source="GarminAdapter",
                is_derived=True,
                data_type="real",
                values=[
                    api.SessionDataValue(timestamp=timestamp, value=12.4),
                ],
            )
        ],
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_metrics",
        lambda _connection, _session_id: [
            api.SessionDataMetric(
                id="metric-1",
                name="max_boat_speed",
                value=18.2,
                unit="kt",
                source="SessionAnalyzer",
            )
        ],
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_events",
        lambda _connection, _session_id: [
            api.SessionDataEvent(
                id="event-1",
                event_type="tack",
                start_time=timestamp,
                end_time=timestamp,
                source="manual",
                confidence=0.9,
                foiling=True,
            )
        ],
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_provenance",
        lambda _connection, _session_id: [
            api.SessionDataProvenanceRecord(
                id="provenance-1",
                producer="SessionAnalyzer",
                produced_type="metric",
                produced_name="max_boat_speed",
                action="analyze",
            )
        ],
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_races",
        lambda _connection, _session_id: [
            api.SessionRace(
                id="race-1",
                session_id="session-1",
                name="Race 1",
                start_time=timestamp,
                finish_time=timestamp,
            )
        ],
    )

    response = api.get_session_data("session-1")

    assert response.session.id == "session-1"
    assert response.channels[0].name == "boat_speed"
    assert response.channels[0].values[0].value == pytest.approx(12.4)
    assert response.metrics[0].name == "max_boat_speed"
    assert response.events[0].event_type == "tack"
    assert response.events[0].foiling is True
    assert response.provenance[0].produced_name == "max_boat_speed"
    assert response.races[0].name == "Race 1"


def test_get_session_data_returns_404_for_unknown_session(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module, "_fetch_session_data_session", lambda _connection, _session_id: None
    )

    with pytest.raises(HTTPException) as exc_info:
        api.get_session_data("missing-session")

    assert exc_info.value.status_code == 404


def test_get_session_data_returns_503_on_database_error(monkeypatch) -> None:
    def _raise_connection_error():
        raise RuntimeError("connection failed")

    monkeypatch.setattr(api_module, "_connect_postgres", _raise_connection_error)

    with pytest.raises(HTTPException) as exc_info:
        api.get_session_data("session-1")

    assert exc_info.value.status_code == 503


def test_export_session_csv_returns_download_response(monkeypatch) -> None:
    timestamp = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    bundle = SessionExportBundle(
        session=api.SessionDataSession(
            id="session-1",
            name="Morning Session",
            start_at=timestamp,
            end_at=timestamp,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            notes=None,
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
        ),
        channels=[],
        events=[],
    )
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_resolve_session_export_bundle",
        lambda _connection, session_id: bundle if session_id == "session-1" else None,
    )

    response = api.export_session_csv("session-1")

    assert response.media_type == "text/csv"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="sips_20260601_morning-session.csv"'
    )
    assert response.body.decode("utf-8").startswith("timestamp,event_tack,event_gybe")


def test_export_session_races_csv_returns_download_response(monkeypatch) -> None:
    timestamp = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    bundle = SessionExportBundle(
        session=api.SessionDataSession(
            id="session-1",
            name="Morning Session",
            start_at=timestamp,
            end_at=timestamp,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            notes=None,
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
        ),
        channels=[],
        events=[],
    )
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_session",
        lambda _connection, session_id: (
            bundle.session if session_id == "session-1" else None
        ),
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_races",
        lambda _connection, session_id: (
            [
                api.SessionRace(
                    id="race-1",
                    session_id=session_id,
                    name="Race 1",
                    start_time=timestamp,
                    finish_time=timestamp,
                )
            ]
            if session_id == "session-1"
            else []
        ),
    )
    monkeypatch.setattr(
        api_module,
        "_resolve_session_export_bundle",
        lambda _connection, session_id, start_time=None, finish_time=None: (
            bundle
            if session_id == "session-1"
            and start_time == timestamp
            and finish_time == timestamp
            else None
        ),
    )

    response = api.export_session_races_csv("session-1")

    assert response.media_type == "text/csv"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="sips_20260601_races.csv"'
    )
    assert response.body.decode("utf-8").startswith(
        "race_id,race_name,timestamp,event_tack,event_gybe"
    )


def test_export_boat_txt_returns_download_response(monkeypatch) -> None:
    timestamp = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    bundle = SessionExportBundle(
        session=api.SessionDataSession(
            id="session-1",
            name="Morning Session",
            start_at=timestamp,
            end_at=timestamp,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            notes=None,
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
        ),
        channels=[],
        events=[],
    )
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module, "_fetch_boat_name", lambda _connection, boat_id: "SIPS"
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_boat_session_ids",
        lambda _connection, boat_id: ["session-1"],
    )
    monkeypatch.setattr(
        api_module,
        "_resolve_session_export_bundle",
        lambda _connection, session_id: bundle if session_id == "session-1" else None,
    )

    response = api.export_boat_txt("boat-1")

    expected_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="sips_exp_{expected_date}.txt"'
    )
    assert "Export scope: boat" in response.body.decode("utf-8")


def test_normalize_session_notes_preserves_content_and_blank_values() -> None:
    assert api._normalize_session_notes(
        "Rig tune looked better.\r\nMuch steadier exits."
    ) == ("Rig tune looked better.\nMuch steadier exits.")
    assert api._normalize_session_notes("   \n\t ") is None
    assert api._normalize_session_notes(None) is None


def test_update_session_notes_updates_row_and_returns_saved_value() -> None:
    cursor = _RecordingCursor(row={"session_id": "session-1", "notes": "Saved note"})
    connection = _RecordingConnection(cursor)

    session_exists, notes = api._update_session_notes(
        connection,
        "session-1",
        "Saved note",
    )

    assert session_exists is True
    assert notes == "Saved note"
    query, params = cursor.executed[0]
    assert "UPDATE session" in query
    assert params == ("Saved note", "session-1")


def test_update_session_notes_returns_404_for_unknown_session(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_update_session_notes",
        lambda _connection, _id, _notes: (False, None),
    )

    with pytest.raises(HTTPException) as exc_info:
        api.update_session_notes(
            "missing-session",
            api.SessionNotesUpdateRequest(notes="Fresh note"),
        )

    assert exc_info.value.status_code == 404


def test_update_session_notes_returns_updated_payload(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_update_session_notes",
        lambda _connection, session_id, notes: (
            True,
            api._normalize_session_notes(notes),
        ),
    )

    response = api.update_session_notes(
        "session-1",
        api.SessionNotesUpdateRequest(notes="Line choice improved late in the block."),
    )

    assert response.session_id == "session-1"
    assert response.notes == "Line choice improved late in the block."


def test_update_manual_wind_direction_updates_metric_and_returns_saved_value() -> None:
    cursor = _RecordingCursor(row={"session_id": "session-1"}, rows=[])
    connection = _RecordingConnection(cursor)
    cursor.fetchone = lambda: (
        {"session_id": "session-1"} if len(cursor.executed) == 1 else {"value": 225.0}
    )

    session_exists, direction = api._update_manual_wind_direction(
        connection,
        "session-1",
        225.0,
    )

    assert session_exists is True
    assert direction == 225.0
    assert "SELECT id::text AS session_id" in cursor.executed[0][0]
    assert "UPDATE session_metric" in cursor.executed[1][0]


def test_update_manual_wind_direction_endpoint_returns_updated_payload(
    monkeypatch,
) -> None:
    recompute_calls: list[str] = []

    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_update_manual_wind_direction",
        lambda _connection, session_id, direction_deg: (
            True,
            direction_deg % 360.0 if direction_deg is not None else None,
        ),
    )
    monkeypatch.setattr(
        api_module,
        "_recompute_session_twa_channels",
        lambda _connection, session_id: recompute_calls.append(session_id) or True,
    )

    response = api.update_session_manual_wind_direction(
        "session-1",
        api.SessionManualWindDirectionUpdateRequest(manual_wind_direction_deg=405.0),
    )

    assert response.session_id == "session-1"
    assert response.manual_wind_direction_deg == 45.0
    assert recompute_calls == ["session-1"]


def test_to_canonical_channel_converts_database_datetimes_to_datetime64() -> None:
    channel = api.SessionDataChannel(
        id="channel-1",
        name="sog",
        unit="kn",
        source="db",
        is_derived=False,
        data_type="real",
        values=[
            api.SessionDataValue(
                timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                value=12.3,
            ),
            api.SessionDataValue(
                timestamp=datetime(2025, 1, 1, 10, 0, 1, tzinfo=timezone.utc),
                value=12.7,
            ),
        ],
    )

    canonical_channel = session_data_module._to_canonical_channel(channel)

    assert np.issubdtype(canonical_channel.timestamps.dtype, np.datetime64)
    np.testing.assert_array_equal(
        canonical_channel.values,
        np.array([12.3, 12.7], dtype=float),
    )


def test_trigger_session_video_returns_accepted_payload(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_session",
        lambda _connection, session_id: {"id": session_id},
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_channels",
        lambda _connection, _session_id: [
            api.SessionDataChannel(
                id="channel-1",
                name="sog",
                unit="kn",
                source="gps",
                is_derived=False,
                data_type="real",
                values=[
                    api.SessionDataValue(
                        timestamp=datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc),
                        value=12.3,
                    )
                ],
            )
        ],
    )
    background_tasks = BackgroundTasks()

    response = api.trigger_session_video(
        "session-1",
        api.SessionVideoTriggerRequest(
            file_path="  /tmp/video.mp4  ",
            sog_channel="  SOG  ",
        ),
        background_tasks,
    )

    assert response.job_id
    assert response.status == "queued"
    assert response.progress_percent == 0.0
    assert response.message == "Queued video render."
    assert len(background_tasks.tasks) == 1


def test_resolve_requested_overlay_layout_prefers_explicit_layout() -> None:
    payload = api.SessionVideoTriggerRequest(
        file_path="/tmp/video.mp4",
        overlay_position="bottom",
        overlay_layout={
            "top": [" SOG ", "utc_time", "SOG", ""],
            "left": [" twa "],
        },
    )

    layout = api_module._resolve_requested_overlay_layout(payload)

    assert layout == {
        "top": ["sog", "utc_time"],
        "left": ["twa"],
    }


def test_trigger_session_video_rejects_blank_file_path() -> None:
    with pytest.raises(HTTPException) as exc_info:
        api.trigger_session_video(
            "session-1",
            api.SessionVideoTriggerRequest(file_path="   "),
            BackgroundTasks(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Video file path is required."


def test_trigger_session_video_returns_404_for_unknown_session(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_session",
        lambda _connection, _session_id: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        api.trigger_session_video(
            "missing-session",
            api.SessionVideoTriggerRequest(file_path="/tmp/video.mp4"),
            BackgroundTasks(),
        )

    assert exc_info.value.status_code == 404


def test_trigger_session_video_returns_404_for_unknown_channel(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_session",
        lambda _connection, session_id: {"id": session_id},
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_channels",
        lambda _connection, _session_id: [],
    )

    with pytest.raises(HTTPException) as exc_info:
        api.trigger_session_video(
            "session-1",
            api.SessionVideoTriggerRequest(
                file_path="/tmp/video.mp4",
                sog_channel="sog",
            ),
            BackgroundTasks(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Channel 'sog' not found for session."


def test_trigger_session_video_returns_400_when_video_analysis_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_session",
        lambda _connection, session_id: {"id": session_id},
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_channels",
        lambda _connection, _session_id: [
            api.SessionDataChannel(
                id="channel-1",
                name="sog",
                unit="kn",
                source="gps",
                is_derived=False,
                data_type="real",
                values=[
                    api.SessionDataValue(
                        timestamp=datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc),
                        value=12.3,
                    )
                ],
            )
        ],
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_channels",
        lambda _connection, _session_id: [
            api.SessionDataChannel(
                id="channel-1",
                name="sog",
                unit="kn",
                source="gps",
                is_derived=False,
                data_type="real",
                values=[],
            )
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        api.trigger_session_video(
            "session-1",
            api.SessionVideoTriggerRequest(file_path="/tmp/missing.mov"),
            BackgroundTasks(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Channel 'sog' does not contain any values."


def test_get_job_returns_recorded_job() -> None:
    job = api.JobResponse(
        job_id="job-1",
        status="running",
        created_at=datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 14, 10, 1, tzinfo=timezone.utc),
        progress_percent=42.0,
        message="Rendering video...",
    )
    api._jobs["job-1"] = job

    response = api.get_job("job-1")

    assert response.job_id == "job-1"
    assert response.status == "running"
    assert response.progress_percent == 42.0
    assert response.message == "Rendering video..."


def test_fetch_session_races_returns_persisted_races() -> None:
    timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    cursor = _RecordingCursor(
        rows=[
            {
                "id": "race-1",
                "session_id": "session-1",
                "name": "Race 1",
                "start_time": timestamp,
                "finish_time": timestamp,
            }
        ]
    )
    connection = _RecordingConnection(cursor)

    races = api._fetch_session_races(connection, "session-1")

    assert len(races) == 1
    assert races[0].id == "race-1"
    assert races[0].session_id == "session-1"
    assert races[0].name == "Race 1"
    query, params = cursor.executed[0]
    assert "FROM race" in query
    assert params == ("session-1",)


def test_fetch_session_race_returns_matching_race() -> None:
    timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    cursor = _RecordingCursor(
        row={
            "id": "race-1",
            "session_id": "session-1",
            "name": "Race 1",
            "start_time": timestamp,
            "finish_time": timestamp.replace(hour=13),
        }
    )
    connection = _RecordingConnection(cursor)

    race = api._fetch_session_race(connection, "session-1", "race-1")

    assert race is not None
    assert race.id == "race-1"
    assert race.session_id == "session-1"
    assert race.start_time == timestamp
    assert race.finish_time == timestamp.replace(hour=13)
    query, params = cursor.executed[0]
    assert "FROM race" in query
    assert params == ("session-1", "race-1")


def test_fetch_session_data_channels_filters_values_to_time_window() -> None:
    start_time = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    finish_time = datetime(2026, 5, 6, 13, 0, tzinfo=timezone.utc)
    cursor = _SequentialCursor(
        rows_by_fetch=[
            [
                {
                    "id": "channel-1",
                    "name": "boat_speed",
                    "unit": "kn",
                    "source": "BoatSpeedTransformer",
                    "is_derived": True,
                }
            ],
            [
                {
                    "channel_id": "channel-1",
                    "timestamp": start_time,
                    "value": 12.4,
                }
            ],
            [],
            [],
        ]
    )
    connection = _SequentialConnection(cursor)

    channels = api._fetch_session_data_channels(
        connection,
        "session-1",
        start_time=start_time,
        finish_time=finish_time,
    )

    assert len(channels) == 1
    assert channels[0].values[0].timestamp == start_time
    assert channels[0].values[0].value == 12.4
    for query, params in cursor.executed[1:]:
        assert "timestamp >= %s" in query
        assert "timestamp <= %s" in query
        assert params == (["channel-1"], start_time, finish_time)


def test_fetch_session_data_events_filters_to_overlapping_time_window() -> None:
    start_time = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    finish_time = datetime(2026, 5, 6, 13, 0, tzinfo=timezone.utc)
    cursor = _RecordingCursor(rows=[])
    connection = _RecordingConnection(cursor)

    events = api._fetch_session_data_events(
        connection,
        "session-1",
        start_time=start_time,
        finish_time=finish_time,
    )

    assert events == []
    query, params = cursor.executed[0]
    assert "start_time <= %s" in query
    assert "end_time >= %s" in query
    assert params == (
        "session-1",
        start_time,
        finish_time,
        start_time,
        finish_time,
        finish_time,
        start_time,
    )


def test_create_session_race_inserts_and_returns_created_race() -> None:
    timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    cursor = _RecordingCursor(
        row={
            "id": "race-1",
            "session_id": "session-1",
            "name": "Race 1",
            "start_time": timestamp,
            "finish_time": timestamp,
        }
    )
    connection = _RecordingConnection(cursor)

    race = api._create_session_race(
        connection,
        "session-1",
        "Race 1",
        timestamp,
        timestamp,
    )

    assert race is not None
    assert race.id == "race-1"
    assert race.session_id == "session-1"
    query, params = cursor.executed[0]
    assert "INSERT INTO race" in query
    assert params == ("session-1", "Race 1", timestamp, timestamp)


def test_get_session_race_data_filters_channels_and_events_to_race_window(
    monkeypatch,
) -> None:
    start_time = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    finish_time = datetime(2026, 5, 6, 13, 0, tzinfo=timezone.utc)
    session = api_module.SessionDataSession(
        id="session-1",
        name="Training morning",
        start_at=start_time,
        end_at=finish_time,
        boat_id="boat-1",
        boat_name="SIPS",
        source="garmin",
        notes=None,
        wind_speed_kts=14.0,
        wind_gust_kts=18.0,
        wind_direction_deg=220.0,
        wave_height_m=0.6,
    )
    race = api_module.SessionRace(
        id="race-1",
        session_id="session-1",
        name="Race 1",
        start_time=start_time,
        finish_time=finish_time,
    )
    captured: dict[str, tuple[object, ...] | bool] = {}

    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_fetch_session_data_session",
        lambda _connection, session_id: session if session_id == "session-1" else None,
    )
    monkeypatch.setattr(
        api_module,
        "_fetch_session_race",
        lambda _connection, session_id, race_id: (
            race if session_id == "session-1" and race_id == "race-1" else None
        ),
    )

    def fake_fetch_channels(_connection, session_id, *, start_time, finish_time):
        captured["channels"] = (session_id, start_time, finish_time)
        return []

    def fake_fetch_events(_connection, session_id, *, start_time, finish_time):
        captured["events"] = (session_id, start_time, finish_time)
        return []

    def fake_fetch_metrics(*_args):
        captured["metrics"] = True
        return [
            api_module.SessionDataMetric(
                id="metric-1",
                name="session_distance_nm",
                value=12.0,
                unit="nm",
                source="SessionAnalyzer",
            )
        ]

    monkeypatch.setattr(api_module, "_fetch_session_data_channels", fake_fetch_channels)
    monkeypatch.setattr(api_module, "_fetch_session_data_events", fake_fetch_events)
    monkeypatch.setattr(api_module, "_fetch_session_data_metrics", fake_fetch_metrics)
    monkeypatch.setattr(api_module, "_fetch_session_data_provenance", lambda *_args: [])

    response = api_module.get_session_race_data("session-1", "race-1")

    assert response.session.id == "session-1"
    assert response.metrics == []
    assert response.races == [race]
    assert "metrics" not in captured
    assert captured["channels"] == ("session-1", start_time, finish_time)
    assert captured["events"] == ("session-1", start_time, finish_time)


def test_create_session_race_returns_404_for_unknown_session(monkeypatch) -> None:
    timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(api_module, "_connect_postgres", lambda: _DummyConnection())
    monkeypatch.setattr(
        api_module,
        "_create_session_race",
        lambda _connection, _session_id, _name, _start_time, _finish_time: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        api.create_session_race(
            "missing-session",
            api.SessionRaceCreateRequest(
                name="Race 1",
                start_time=timestamp,
                finish_time=timestamp.replace(hour=13),
            ),
        )

    assert exc_info.value.status_code == 404


def test_create_session_race_rejects_finish_before_start() -> None:
    timestamp = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as exc_info:
        api.create_session_race(
            "session-1",
            api.SessionRaceCreateRequest(
                name="Race 1",
                start_time=timestamp,
                finish_time=timestamp,
            ),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    "metadata_content",
    [
        b"not-json",
        b"[]",
    ],
)
def test_create_session_job_rejects_invalid_metadata_json(
    api_test_context, metadata_content: bytes
) -> None:
    called_jobs, _ = api_test_context
    background_tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            api.create_session_job(
                background_tasks=background_tasks,
                tcx_file=make_upload_file("session.tcx", b"<tcx/>"),
                metadata_json=make_upload_file("metadata.json", metadata_content),
            )
        )

    assert exc_info.value.status_code == 400
    assert len(called_jobs) == 0
