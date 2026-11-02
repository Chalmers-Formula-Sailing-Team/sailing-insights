from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from src.analyzer.videoAnalyzer import VideoAnalyzer
from src.jobProcessor import JobProcessor
from src.models.job import Job

from .boats import _create_boat, _delete_boat, _update_boat
from .constants import (
    MANUAL_WAVE_HEIGHT_METRIC_NAME,
    MANUAL_WIND_DIRECTION_METRIC_NAME,
    MANUAL_WIND_GUST_METRIC_NAME,
    MANUAL_WIND_SPEED_METRIC_NAME,
    MAX_TRACK_POINTS_PER_SESSION,
    PROJECT_ROOT,
)
from .dashboard import (
    _build_dashboard_overview_response,
    _fetch_boat_rows,
    _fetch_session_rows,
    _fetch_track_points_by_session_id,
    _sample_track_points,
)
from .database import (
    _coerce_float,
    _coerce_int,
    _connect_postgres,
    _read_root_env_defaults,
)
from .exporters import (
    SessionRaceExportBundle,
    _fetch_boat_name,
    _fetch_boat_session_ids,
    _resolve_session_export_bundle,
    build_boat_export_documents,
    build_race_export_documents,
    build_session_export_documents,
    build_session_races_export_documents,
)
from .jobs import (
    JOB_PAYLOAD_ROOT,
    _get_job,
    _jobs,
    _jobs_lock,
    _set_job_state,
    _utc_now,
    _validate_upload_filenames,
)
from .models import (
    BoatResponse,
    BoatWriteRequest,
    DashboardBoatOverview,
    DashboardOverviewResponse,
    DashboardSessionOverview,
    DashboardTrackPoint,
    JobResponse,
    SessionDataChannel,
    SessionDataEvent,
    SessionDataMetric,
    SessionDataProvenanceRecord,
    SessionDataResponse,
    SessionDataSession,
    SessionDataValue,
    SessionManualWindDirectionUpdateRequest,
    SessionManualWindDirectionUpdateResponse,
    SessionNotesUpdateRequest,
    SessionNotesUpdateResponse,
    SessionRace,
    SessionRaceCreateRequest,
    SessionResponse,
    SessionVideoTriggerRequest,
    SessionVideoTriggerResponse,
    SessionWriteRequest,
)
from .races import (
    _create_session_race,
    _delete_session_race,
    _fetch_session_race,
    _fetch_session_races,
    _update_session_race,
)
from .session_data import (
    _build_session_data_response,
    _fetch_session_data_channels,
    _fetch_session_data_events,
    _fetch_session_data_metrics,
    _fetch_session_data_provenance,
    _fetch_session_data_session,
    _normalize_session_notes,
    _recompute_session_twa_channels,
    _update_manual_wind_direction,
    _update_session_notes,
)
from .sessions import _delete_session, _update_session

app = FastAPI(
    title="Sailing Insights API",
    description="Session ingestion endpoint for TCX/FIT + metadata JSON uploads.",
)

logger = logging.getLogger(__name__)
video_analyzer = VideoAnalyzer()

cors_origins_raw = os.getenv(
    "API_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
cors_origins = [
    origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_text_download_response(
    document_name: str, content: str, media_type: str
) -> Response:
    response = Response(content=content, media_type=media_type)
    response.headers["Content-Disposition"] = f'attachment; filename="{document_name}"'
    return response


def _resolve_requested_channel_name(channel_name: str | None) -> str:
    if channel_name is None:
        return "sog"

    normalized = channel_name.strip()
    if not normalized:
        return "sog"
    return normalized.lower()


def _resolve_requested_channel_names(payload: SessionVideoTriggerRequest) -> list[str]:
    if payload.channel_names:
        normalized_names = [
            channel_name.strip().lower()
            for channel_name in payload.channel_names
            if isinstance(channel_name, str) and channel_name.strip()
        ]
        if normalized_names:
            return list(dict.fromkeys(normalized_names))

    return [_resolve_requested_channel_name(payload.sog_channel)]


def _resolve_requested_overlay_layout(
    payload: SessionVideoTriggerRequest,
) -> dict[str, list[str]]:
    normalized_layout: dict[str, list[str]] = {}

    for position in ("top", "bottom", "left", "right"):
        raw_names = payload.overlay_layout.get(position, [])
        if not isinstance(raw_names, list):
            continue
        normalized_names = [
            channel_name.strip().lower()
            for channel_name in raw_names
            if isinstance(channel_name, str) and channel_name.strip()
        ]
        if normalized_names:
            normalized_layout[position] = list(dict.fromkeys(normalized_names))[:3]

    if normalized_layout:
        return normalized_layout

    return {
        payload.overlay_position: _resolve_requested_channel_names(payload)[:3],
    }


def _is_virtual_video_channel(channel_name: str) -> bool:
    return channel_name in {"time_utc", "utc_time"}


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )
    return job


@app.get("/dashboard/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview() -> DashboardOverviewResponse:
    try:
        with _connect_postgres() as connection:
            boat_rows = _fetch_boat_rows(connection)
            session_rows = _fetch_session_rows(connection)
            track_points_by_session_id = _fetch_track_points_by_session_id(
                connection,
                [str(session_row["id"]) for session_row in session_rows],
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load dashboard overview from database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load dashboard overview from database.",
        ) from exc

    return _build_dashboard_overview_response(
        boat_rows, session_rows, track_points_by_session_id
    )


@app.get("/sessions/{session_id}/data", response_model=SessionDataResponse)
def get_session_data(session_id: str) -> SessionDataResponse:
    try:
        with _connect_postgres() as connection:
            session = _fetch_session_data_session(connection, session_id)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )

            channels = _fetch_session_data_channels(connection, session_id)
            metrics = _fetch_session_data_metrics(connection, session_id)
            events = _fetch_session_data_events(connection, session_id)
            provenance = _fetch_session_data_provenance(connection, session_id)
            races = _fetch_session_races(connection, session_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load session data from database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load session data from database.",
        ) from exc

    return _build_session_data_response(
        session=session,
        channels=channels,
        metrics=metrics,
        events=events,
        provenance=provenance,
        races=races,
    )


@app.get(
    "/sessions/{session_id}/races/{race_id}/data",
    response_model=SessionDataResponse,
)
def get_session_race_data(session_id: str, race_id: str) -> SessionDataResponse:
    try:
        with _connect_postgres() as connection:
            session = _fetch_session_data_session(connection, session_id)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )

            race = _fetch_session_race(connection, session_id, race_id)
            if race is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Race not found.",
                )

            channels = _fetch_session_data_channels(
                connection,
                session_id,
                start_time=race.start_time,
                finish_time=race.finish_time,
            )
            events = _fetch_session_data_events(
                connection,
                session_id,
                start_time=race.start_time,
                finish_time=race.finish_time,
            )
            provenance = _fetch_session_data_provenance(connection, session_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load race data from database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load race data from database.",
        ) from exc

    return _build_session_data_response(
        session=session,
        channels=channels,
        metrics=[],
        events=events,
        provenance=provenance,
        races=[race],
    )


@app.get("/sessions/{session_id}/export.csv")
def export_session_csv(session_id: str) -> Response:
    try:
        with _connect_postgres() as connection:
            bundle = _resolve_session_export_bundle(connection, session_id)
            if bundle is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export session CSV.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export session CSV.",
        ) from exc

    csv_document, _ = build_session_export_documents(bundle)
    return _build_text_download_response(
        csv_document.filename, csv_document.content, "text/csv"
    )


@app.get("/sessions/{session_id}/export.txt")
def export_session_txt(session_id: str) -> PlainTextResponse:
    try:
        with _connect_postgres() as connection:
            bundle = _resolve_session_export_bundle(connection, session_id)
            if bundle is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export session notes.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export session notes.",
        ) from exc

    _, txt_document = build_session_export_documents(bundle)
    return PlainTextResponse(
        txt_document.content,
        headers={
            "Content-Disposition": f'attachment; filename="{txt_document.filename}"'
        },
    )


@app.get("/sessions/{session_id}/races/{race_id}/export.csv")
def export_session_race_csv(session_id: str, race_id: str) -> Response:
    try:
        with _connect_postgres() as connection:
            race = _fetch_session_race(connection, session_id, race_id)
            if race is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Race not found.",
                )

            bundle = _resolve_session_export_bundle(
                connection,
                session_id,
                start_time=race.start_time,
                finish_time=race.finish_time,
            )
            if bundle is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export race CSV.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export race CSV.",
        ) from exc

    csv_document, _ = build_race_export_documents(
        bundle,
        race_name=race.name,
        race_id=race.id,
    )
    return _build_text_download_response(
        csv_document.filename, csv_document.content, "text/csv"
    )


@app.get("/sessions/{session_id}/races/{race_id}/export.txt")
def export_session_race_txt(session_id: str, race_id: str) -> PlainTextResponse:
    try:
        with _connect_postgres() as connection:
            race = _fetch_session_race(connection, session_id, race_id)
            if race is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Race not found.",
                )

            bundle = _resolve_session_export_bundle(
                connection,
                session_id,
                start_time=race.start_time,
                finish_time=race.finish_time,
            )
            if bundle is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export race notes.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export race notes.",
        ) from exc

    _, txt_document = build_race_export_documents(
        bundle,
        race_name=race.name,
        race_id=race.id,
    )
    return PlainTextResponse(
        txt_document.content,
        headers={
            "Content-Disposition": f'attachment; filename="{txt_document.filename}"'
        },
    )


@app.get("/sessions/{session_id}/races/export.csv")
def export_session_races_csv(session_id: str) -> Response:
    try:
        with _connect_postgres() as connection:
            session = _fetch_session_data_session(connection, session_id)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )

            races = _fetch_session_races(connection, session_id)
            if not races:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No races found for session.",
                )

            race_bundles = []
            for race in races:
                bundle = _resolve_session_export_bundle(
                    connection,
                    session_id,
                    start_time=race.start_time,
                    finish_time=race.finish_time,
                )
                if bundle is not None:
                    race_bundles.append(
                        SessionRaceExportBundle(race=race, bundle=bundle)
                    )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export session races CSV.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export session races CSV.",
        ) from exc

    csv_document, _ = build_session_races_export_documents(
        session.name,
        session.id,
        race_bundles,
    )
    return _build_text_download_response(
        csv_document.filename, csv_document.content, "text/csv"
    )


@app.get("/sessions/{session_id}/races/export.txt")
def export_session_races_txt(session_id: str) -> PlainTextResponse:
    try:
        with _connect_postgres() as connection:
            session = _fetch_session_data_session(connection, session_id)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )

            races = _fetch_session_races(connection, session_id)
            if not races:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No races found for session.",
                )

            race_bundles = []
            for race in races:
                bundle = _resolve_session_export_bundle(
                    connection,
                    session_id,
                    start_time=race.start_time,
                    finish_time=race.finish_time,
                )
                if bundle is not None:
                    race_bundles.append(
                        SessionRaceExportBundle(race=race, bundle=bundle)
                    )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export session races notes.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export session races notes.",
        ) from exc

    _, txt_document = build_session_races_export_documents(
        session.name,
        session.id,
        race_bundles,
    )
    return PlainTextResponse(
        txt_document.content,
        headers={
            "Content-Disposition": f'attachment; filename="{txt_document.filename}"'
        },
    )


@app.get("/boats/{boat_id}/export.csv")
def export_boat_csv(boat_id: str) -> Response:
    try:
        with _connect_postgres() as connection:
            boat_name = _fetch_boat_name(connection, boat_id)
            session_ids = _fetch_boat_session_ids(connection, boat_id)
            if boat_name is None and not session_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Boat not found.",
                )

            bundles = []
            for session_id in session_ids:
                bundle = _resolve_session_export_bundle(connection, session_id)
                if bundle is not None:
                    bundles.append(bundle)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export boat CSV.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export boat CSV.",
        ) from exc

    csv_document, _ = build_boat_export_documents(boat_name, boat_id, bundles)
    return _build_text_download_response(
        csv_document.filename, csv_document.content, "text/csv"
    )


@app.get("/boats/{boat_id}/export.txt")
def export_boat_txt(boat_id: str) -> PlainTextResponse:
    try:
        with _connect_postgres() as connection:
            boat_name = _fetch_boat_name(connection, boat_id)
            session_ids = _fetch_boat_session_ids(connection, boat_id)
            if boat_name is None and not session_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Boat not found.",
                )

            bundles = []
            for session_id in session_ids:
                bundle = _resolve_session_export_bundle(connection, session_id)
                if bundle is not None:
                    bundles.append(bundle)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to export boat notes.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not export boat notes.",
        ) from exc

    _, txt_document = build_boat_export_documents(boat_name, boat_id, bundles)
    return PlainTextResponse(
        txt_document.content,
        headers={
            "Content-Disposition": f'attachment; filename="{txt_document.filename}"'
        },
    )


@app.post("/boats", response_model=BoatResponse, status_code=status.HTTP_201_CREATED)
def create_boat(payload: BoatWriteRequest) -> BoatResponse:
    try:
        with _connect_postgres() as connection:
            result, boat = _create_boat(connection, payload)
            if result == "duplicate":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A boat with this name already exists.",
                )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to create boat.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create boat.",
        ) from exc

    return boat


@app.patch("/boats/{boat_id}", response_model=BoatResponse)
def update_boat(boat_id: str, payload: BoatWriteRequest) -> BoatResponse:
    try:
        with _connect_postgres() as connection:
            result, boat = _update_boat(connection, boat_id, payload)
            if result == "not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Boat not found.",
                )
            if result == "duplicate":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A boat with this name already exists.",
                )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to update boat.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update boat.",
        ) from exc

    return boat


@app.delete("/boats/{boat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_boat(boat_id: str) -> Response:
    try:
        with _connect_postgres() as connection:
            result = _delete_boat(connection, boat_id)
            if result == "not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Boat not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to delete boat.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not delete boat.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/sessions/{session_id}/notes", response_model=SessionNotesUpdateResponse)
def update_session_notes(
    session_id: str, payload: SessionNotesUpdateRequest
) -> SessionNotesUpdateResponse:
    try:
        with _connect_postgres() as connection:
            session_exists, updated_notes = _update_session_notes(
                connection, session_id, payload.notes
            )
            if not session_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to update session notes in database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update session notes in database.",
        ) from exc

    return SessionNotesUpdateResponse(session_id=session_id, notes=updated_notes)


@app.patch("/sessions/{session_id}", response_model=SessionResponse)
def update_session(session_id: str, payload: SessionWriteRequest) -> SessionResponse:
    try:
        with _connect_postgres() as connection:
            result, session = _update_session(connection, session_id, payload)
            if result == "not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to update session.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update session.",
        ) from exc

    return session


@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str) -> Response:
    try:
        with _connect_postgres() as connection:
            result = _delete_session(connection, session_id)
            if result == "not_found":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to delete session.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not delete session.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch(
    "/sessions/{session_id}/manual-wind-direction",
    response_model=SessionManualWindDirectionUpdateResponse,
)
def update_session_manual_wind_direction(
    session_id: str, payload: SessionManualWindDirectionUpdateRequest
) -> SessionManualWindDirectionUpdateResponse:
    try:
        with _connect_postgres() as connection:
            session_exists, updated_direction = _update_manual_wind_direction(
                connection,
                session_id,
                payload.manual_wind_direction_deg,
            )
            if not session_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
            _recompute_session_twa_channels(connection, session_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to update manual wind direction in database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update manual wind direction in database.",
        ) from exc

    return SessionManualWindDirectionUpdateResponse(
        session_id=session_id,
        manual_wind_direction_deg=updated_direction,
    )


def _run_video_render_job(
    job_id: str,
    *,
    session_id: str,
    file_path: str,
    output_folder: str | None,
    overlay_layout: dict[str, list[dict[str, object]]],
) -> None:
    _set_job_state(
        job_id,
        status_value="running",
        progress_percent=0.0,
        message="Preparing video render...",
    )

    try:
        render_result = video_analyzer.render_sog_overlay(
            file_path=file_path,
            overlay_layout=overlay_layout,
            output_dir=output_folder.strip()
            if output_folder and output_folder.strip()
            else Path.home() / "Downloads",
            progress_callback=lambda progress_percent, message: _set_job_state(
                job_id,
                status_value="running",
                progress_percent=progress_percent,
                message=message,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to render session video.")
        _set_job_state(
            job_id,
            status_value="failed",
            progress_percent=100.0,
            error=str(exc),
            message="Video render failed.",
        )
        return

    _set_job_state(
        job_id,
        status_value="completed",
        progress_percent=100.0,
        message="Video render completed.",
        output_file_path=str(render_result["output_file_path"]),
    )


@app.post(
    "/sessions/{session_id}/video",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_session_video(
    session_id: str,
    payload: SessionVideoTriggerRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    normalized_file_path = payload.file_path.strip()
    normalized_output_folder = (
        payload.output_folder.strip() if isinstance(payload.output_folder, str) else ""
    )
    requested_overlay_layout = _resolve_requested_overlay_layout(payload)
    if not normalized_file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video file path is required.",
        )

    try:
        with _connect_postgres() as connection:
            session = _fetch_session_data_session(connection, session_id)
            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
            channels = _fetch_session_data_channels(connection, session_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to trigger session video.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not trigger session video.",
        ) from exc

    channels_by_name = {channel.name.lower(): channel for channel in channels}
    overlay_layout: dict[str, list[dict[str, object]]] = {}
    for position, requested_channel_names in requested_overlay_layout.items():
        overlay_channels: list[dict[str, object]] = []
        for requested_channel_name in requested_channel_names:
            if _is_virtual_video_channel(requested_channel_name):
                overlay_channels.append(
                    {
                        "name": "time_utc",
                        "unit": None,
                        "data_type": "virtual_utc_time",
                        "samples": [],
                    }
                )
                continue

            requested_channel = channels_by_name.get(requested_channel_name)
            if requested_channel is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Channel '{requested_channel_name}' not found for session.",
                )

            if not requested_channel.values:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Channel '{requested_channel.name}' does not contain any values.",
                )

            overlay_channels.append(
                {
                    "name": requested_channel.name,
                    "unit": requested_channel.unit,
                    "data_type": requested_channel.data_type,
                    "samples": [
                        (sample.timestamp, sample.value)
                        for sample in requested_channel.values
                    ],
                }
            )

        if overlay_channels:
            overlay_layout[position] = overlay_channels

    if not overlay_layout:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one channel for the video overlay.",
        )

    job_id = uuid4().hex
    now = _utc_now()
    job_response = JobResponse(
        job_id=job_id,
        status="queued",
        created_at=now,
        updated_at=now,
        progress_percent=0.0,
        message="Queued video render.",
    )
    with _jobs_lock:
        _jobs[job_id] = job_response

    background_tasks.add_task(
        _run_video_render_job,
        job_id,
        session_id=session_id,
        file_path=normalized_file_path,
        output_folder=normalized_output_folder or None,
        overlay_layout=overlay_layout,
    )

    logger.info(
        "Video render queued for session %s with file path %s",
        session_id,
        normalized_file_path,
    )
    return job_response


@app.post("/sessions/{session_id}/races", response_model=SessionRace)
def create_session_race(
    session_id: str, payload: SessionRaceCreateRequest
) -> SessionRace:
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Race name is required.",
        )

    if payload.finish_time <= payload.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Race finish time must be later than race start time.",
        )

    try:
        with _connect_postgres() as connection:
            race = _create_session_race(
                connection,
                session_id,
                normalized_name,
                payload.start_time,
                payload.finish_time,
            )
            if race is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to create race in database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create race in database.",
        ) from exc

    return race


def _validate_race_payload(payload: SessionRaceCreateRequest) -> str:
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Race name is required.",
        )

    if payload.finish_time <= payload.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Race finish time must be later than race start time.",
        )

    return normalized_name


@app.patch("/sessions/{session_id}/races/{race_id}", response_model=SessionRace)
def update_session_race(
    session_id: str, race_id: str, payload: SessionRaceCreateRequest
) -> SessionRace:
    normalized_name = _validate_race_payload(payload)

    try:
        with _connect_postgres() as connection:
            race = _update_session_race(
                connection,
                session_id,
                race_id,
                normalized_name,
                payload.start_time,
                payload.finish_time,
            )
            if race is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Race not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to update race in database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update race in database.",
        ) from exc

    return race


@app.delete(
    "/sessions/{session_id}/races/{race_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_session_race(session_id: str, race_id: str) -> Response:
    try:
        with _connect_postgres() as connection:
            race_deleted = _delete_session_race(connection, session_id, race_id)
            if not race_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Race not found.",
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to delete race in database.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not delete race in database.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _run_pipeline(job_id: str, session_path: Path, meta_path: Path) -> None:
    _set_job_state(job_id, status_value="running")
    processor = JobProcessor()

    try:
        processor.process_job(
            Job(session_path=str(session_path), meta_path=str(meta_path))
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed for job_id=%s", job_id)
        _set_job_state(job_id, status_value="failed", error=str(exc))
        return

    _set_job_state(job_id, status_value="completed")


@app.post("/sessions", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_session_job(
    background_tasks: BackgroundTasks,
    tcx_file: UploadFile = File(...),
    metadata_json: UploadFile = File(...),
) -> JobResponse:
    session_extension = _validate_upload_filenames(tcx_file, metadata_json)

    tcx_bytes = await tcx_file.read()
    if not tcx_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`tcx_file` is empty.",
        )

    metadata_bytes = await metadata_json.read()
    if not metadata_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`metadata_json` is empty.",
        )

    try:
        metadata_payload = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"`metadata_json` must contain valid UTF-8 JSON: {exc}",
        ) from exc

    if not isinstance(metadata_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`metadata_json` must be a JSON object.",
        )

    job_id = uuid4().hex
    now = _utc_now()
    job_dir = JOB_PAYLOAD_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    session_path = job_dir / f"session{session_extension}"
    meta_path = job_dir / "metadata.json"
    session_path.write_bytes(tcx_bytes)
    meta_path.write_text(json.dumps(metadata_payload), encoding="utf-8")

    job_response = JobResponse(
        job_id=job_id,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    with _jobs_lock:
        _jobs[job_id] = job_response

    background_tasks.add_task(_run_pipeline, job_id, session_path, meta_path)
    return job_response
