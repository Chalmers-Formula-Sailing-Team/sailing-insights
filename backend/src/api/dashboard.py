from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from .constants import (
    MANUAL_WAVE_HEIGHT_METRIC_NAME,
    MANUAL_WIND_DIRECTION_METRIC_NAME,
    MANUAL_WIND_GUST_METRIC_NAME,
    MANUAL_WIND_SPEED_METRIC_NAME,
    MAX_TRACK_POINTS_PER_SESSION,
)
from .database import _coerce_float
from .models import (
    DashboardBoatOverview,
    DashboardOverviewResponse,
    DashboardSessionOverview,
    DashboardTrackPoint,
)


def _fetch_boat_rows(connection: Connection[Any]) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                b.id::text AS id,
                b.name,
                b.sailnumber,
                bc.name AS class_name
            FROM boat AS b
            LEFT JOIN boat_class AS bc
                ON bc.id = b.class_id
            ORDER BY b.name ASC
            """
        )
        return list(cursor.fetchall())


def _fetch_session_rows(connection: Connection[Any]) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            WITH metric_values AS (
                SELECT
                    session_id,
                    MAX(value) FILTER (WHERE name = 'session_distance_nm') AS distance_nm,
                    MAX(value) FILTER (WHERE name = 'session_duration_min') AS duration_min,
                    MAX(value) FILTER (WHERE name = 'max_boat_speed') AS max_speed_kts,
                    MAX(value) FILTER (WHERE name = 'foiling_time_min') AS foiling_time_min,
                    MAX(value) FILTER (WHERE name = 'foiling_percentage') AS foiling_percentage,
                    MAX(value) FILTER (WHERE name = 'tack_count') AS tack_count,
                    MAX(value) FILTER (WHERE name = 'gybe_count') AS gybe_count,
                    MAX(value) FILTER (WHERE name = 'foiling_tack_count') AS foiling_tack_count,
                    MAX(value) FILTER (WHERE name = 'foiling_gybe_count') AS foiling_gybe_count,
                    MAX(value) FILTER (WHERE name = 'foiling_tack_percentage') AS foiling_tack_percentage,
                    MAX(value) FILTER (WHERE name = 'foiling_gybe_percentage') AS foiling_gybe_percentage,
                    MAX(value) FILTER (WHERE name = 'avg_wind_speed_kn') AS derived_wind_speed_kts,
                    MAX(value) FILTER (WHERE name = 'avg_wind_gust_kn') AS wind_gust_kts,
                    MAX(value) FILTER (WHERE name = 'avg_wind_dir') AS derived_wind_direction_deg,
                    MAX(value) FILTER (WHERE name = %s) AS manual_wind_speed_kts,
                    MAX(value) FILTER (WHERE name = %s) AS manual_wind_gust_kts,
                    MAX(value) FILTER (WHERE name = %s) AS manual_wind_direction_deg,
                    MAX(value) FILTER (WHERE name = %s) AS manual_wave_height_m
                FROM session_metric
                GROUP BY session_id
            )
            SELECT
                s.id::text AS id,
                s.name,
                s.start_at,
                s.end_at,
                s.boat_id::text AS boat_id,
                b.name AS boat_name,
                s.location,
                s.notes,
                COALESCE(
                    metric_values.duration_min / 60.0,
                    CASE
                        WHEN s.start_at IS NOT NULL AND s.end_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (s.end_at - s.start_at)) / 3600.0
                        ELSE 0.0
                    END
                ) AS duration_hours,
                COALESCE(metric_values.distance_nm, 0.0) AS distance_nm,
                metric_values.max_speed_kts AS max_speed_kts,
                metric_values.foiling_time_min AS foiling_time_min,
                metric_values.foiling_percentage AS foiling_percentage,
                metric_values.tack_count AS tack_count,
                metric_values.gybe_count AS gybe_count,
                metric_values.foiling_tack_count AS foiling_tack_count,
                metric_values.foiling_gybe_count AS foiling_gybe_count,
                metric_values.foiling_tack_percentage AS foiling_tack_percentage,
                metric_values.foiling_gybe_percentage AS foiling_gybe_percentage,
                metric_values.manual_wind_speed_kts AS manual_wind_speed_kts,
                metric_values.manual_wind_gust_kts AS manual_wind_gust_kts,
                metric_values.manual_wind_direction_deg AS manual_wind_direction_deg,
                metric_values.manual_wave_height_m AS manual_wave_height_m,
                metric_values.derived_wind_speed_kts AS external_wind_speed_kts,
                metric_values.wind_gust_kts AS external_wind_gust_kts,
                metric_values.derived_wind_direction_deg AS external_wind_direction_deg,
                COALESCE(
                    metric_values.derived_wind_speed_kts,
                    metric_values.manual_wind_speed_kts
                ) AS wind_speed_kts,
                COALESCE(
                    metric_values.wind_gust_kts,
                    metric_values.manual_wind_gust_kts
                ) AS wind_gust_kts,
                COALESCE(
                    metric_values.derived_wind_direction_deg,
                    metric_values.manual_wind_direction_deg
                ) AS wind_direction_deg,
                metric_values.manual_wave_height_m AS wave_height_m
            FROM session AS s
            LEFT JOIN boat AS b
                ON b.id = s.boat_id
            LEFT JOIN metric_values
                ON metric_values.session_id = s.id
            ORDER BY COALESCE(s.start_at, s.end_at) DESC NULLS LAST, s.name ASC
            """,
            (
                MANUAL_WIND_SPEED_METRIC_NAME,
                MANUAL_WIND_GUST_METRIC_NAME,
                MANUAL_WIND_DIRECTION_METRIC_NAME,
                MANUAL_WAVE_HEIGHT_METRIC_NAME,
            ),
        )
        rows = list(cursor.fetchall())

    for row in rows:
        if row.get("wind_speed_kts") is None:
            row["wind_speed_kts"] = row.get("external_wind_speed_kts")
            if row["wind_speed_kts"] is None:
                row["wind_speed_kts"] = row.get("manual_wind_speed_kts")

        if row.get("wind_gust_kts") is None:
            row["wind_gust_kts"] = row.get("external_wind_gust_kts")
            if row["wind_gust_kts"] is None:
                row["wind_gust_kts"] = row.get("manual_wind_gust_kts")

        if row.get("wind_direction_deg") is None:
            row["wind_direction_deg"] = row.get("external_wind_direction_deg")
            if row["wind_direction_deg"] is None:
                row["wind_direction_deg"] = row.get("manual_wind_direction_deg")

        if row.get("wave_height_m") is None:
            row["wave_height_m"] = row.get("manual_wave_height_m")

    return rows


def _sample_track_points(
    points: list[DashboardTrackPoint],
    limit: int = MAX_TRACK_POINTS_PER_SESSION,
) -> list[DashboardTrackPoint]:
    if len(points) <= limit or limit < 2:
        return points

    step = (len(points) - 1) / (limit - 1)
    return [points[round(index * step)] for index in range(limit)]


def _fetch_track_points_by_session_id(
    connection: Connection[Any], session_ids: list[str]
) -> dict[str, list[DashboardTrackPoint]]:
    normalized_session_ids = [session_id for session_id in session_ids if session_id]
    if not normalized_session_ids:
        return {}

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                lat.session_id::text AS session_id,
                lat_data.timestamp AS timestamp,
                lat_data.value AS latitude,
                lon_data.value AS longitude
            FROM session_channel AS lat
            JOIN session_channel AS lon
                ON lon.session_id = lat.session_id
               AND lon.name = 'lon'
            JOIN channel_data_real AS lat_data
                ON lat_data.channel_id = lat.id
            JOIN channel_data_real AS lon_data
                ON lon_data.channel_id = lon.id
               AND lon_data.timestamp = lat_data.timestamp
            WHERE lat.name = 'lat'
              AND lat.session_id::text = ANY(%s)
            ORDER BY lat.session_id ASC, lat_data.timestamp ASC
            """,
            (normalized_session_ids,),
        )
        rows = list(cursor.fetchall())

    track_points_by_session_id: dict[str, list[DashboardTrackPoint]] = {}
    for row in rows:
        session_id = str(row["session_id"])
        latitude = row["latitude"]
        longitude = row["longitude"]
        if latitude is None or longitude is None:
            continue

        points = track_points_by_session_id.setdefault(session_id, [])
        points.append(
            DashboardTrackPoint(
                latitude=float(latitude),
                longitude=float(longitude),
                timestamp=row["timestamp"],
            )
        )

    return {
        session_id: _sample_track_points(points)
        for session_id, points in track_points_by_session_id.items()
    }


def _build_dashboard_overview_response(
    boat_rows: list[dict[str, Any]],
    session_rows: list[dict[str, Any]],
    track_points_by_session_id: dict[str, list[DashboardTrackPoint]] | None = None,
) -> DashboardOverviewResponse:
    track_points_by_session_id = track_points_by_session_id or {}
    boats_by_id: dict[str, dict[str, Any]] = {}
    for boat_row in boat_rows:
        boats_by_id[boat_row["id"]] = {
            "id": boat_row["id"],
            "name": boat_row["name"],
            "class_name": boat_row["class_name"],
            "sailnumber": boat_row.get("sailnumber"),
            "session_count": 0,
            "total_hours": 0.0,
            "total_distance_nm": 0.0,
            "max_speed_kts": None,
        }

    session_overviews: list[DashboardSessionOverview] = []
    for session_row in session_rows:
        session_id = str(session_row["id"])
        boat_id_value = session_row["boat_id"]
        boat_id = str(boat_id_value) if boat_id_value is not None else None
        duration_hours = _coerce_float(session_row["duration_hours"])
        distance_nm = _coerce_float(session_row["distance_nm"])
        max_speed_kts = (
            _coerce_float(session_row["max_speed_kts"], default=0.0)
            if session_row["max_speed_kts"] is not None
            else None
        )
        foiling_time_min = (
            _coerce_float(session_row["foiling_time_min"], default=0.0)
            if session_row["foiling_time_min"] is not None
            else None
        )
        foiling_percentage = (
            _coerce_float(session_row["foiling_percentage"], default=0.0)
            if session_row["foiling_percentage"] is not None
            else None
        )

        session_overviews.append(
            DashboardSessionOverview(
                id=session_id,
                boat_id=boat_id,
                boat_name=session_row["boat_name"],
                name=session_row["name"] or "Unnamed session",
                location=session_row.get("location"),
                start_at=session_row["start_at"],
                end_at=session_row["end_at"],
                duration_hours=duration_hours,
                distance_nm=distance_nm,
                max_speed_kts=max_speed_kts,
                foiling_time_min=foiling_time_min,
                foiling_percentage=foiling_percentage,
                tack_count=(
                    _coerce_float(session_row["tack_count"], default=0.0)
                    if session_row["tack_count"] is not None
                    else None
                ),
                gybe_count=(
                    _coerce_float(session_row["gybe_count"], default=0.0)
                    if session_row["gybe_count"] is not None
                    else None
                ),
                foiling_tack_count=(
                    _coerce_float(session_row["foiling_tack_count"], default=0.0)
                    if session_row["foiling_tack_count"] is not None
                    else None
                ),
                foiling_gybe_count=(
                    _coerce_float(session_row["foiling_gybe_count"], default=0.0)
                    if session_row["foiling_gybe_count"] is not None
                    else None
                ),
                foiling_tack_percentage=(
                    _coerce_float(session_row["foiling_tack_percentage"], default=0.0)
                    if session_row["foiling_tack_percentage"] is not None
                    else None
                ),
                foiling_gybe_percentage=(
                    _coerce_float(session_row["foiling_gybe_percentage"], default=0.0)
                    if session_row["foiling_gybe_percentage"] is not None
                    else None
                ),
                manual_wind_speed_kts=(
                    _coerce_float(session_row["manual_wind_speed_kts"], default=0.0)
                    if session_row["manual_wind_speed_kts"] is not None
                    else None
                ),
                manual_wind_gust_kts=(
                    _coerce_float(session_row["manual_wind_gust_kts"], default=0.0)
                    if session_row["manual_wind_gust_kts"] is not None
                    else None
                ),
                manual_wind_direction_deg=(
                    _coerce_float(session_row["manual_wind_direction_deg"], default=0.0)
                    if session_row["manual_wind_direction_deg"] is not None
                    else None
                ),
                manual_wave_height_m=(
                    _coerce_float(session_row["manual_wave_height_m"], default=0.0)
                    if session_row["manual_wave_height_m"] is not None
                    else None
                ),
                external_wind_speed_kts=(
                    _coerce_float(session_row["external_wind_speed_kts"], default=0.0)
                    if session_row["external_wind_speed_kts"] is not None
                    else None
                ),
                external_wind_gust_kts=(
                    _coerce_float(session_row["external_wind_gust_kts"], default=0.0)
                    if session_row["external_wind_gust_kts"] is not None
                    else None
                ),
                external_wind_direction_deg=(
                    _coerce_float(
                        session_row["external_wind_direction_deg"], default=0.0
                    )
                    if session_row["external_wind_direction_deg"] is not None
                    else None
                ),
                wind_speed_kts=(
                    _coerce_float(session_row["wind_speed_kts"], default=0.0)
                    if session_row["wind_speed_kts"] is not None
                    else None
                ),
                wind_gust_kts=(
                    _coerce_float(session_row["wind_gust_kts"], default=0.0)
                    if session_row["wind_gust_kts"] is not None
                    else None
                ),
                wind_direction_deg=(
                    _coerce_float(session_row["wind_direction_deg"], default=0.0)
                    if session_row["wind_direction_deg"] is not None
                    else None
                ),
                wave_height_m=(
                    _coerce_float(session_row["wave_height_m"], default=0.0)
                    if session_row["wave_height_m"] is not None
                    else None
                ),
                notes=session_row["notes"],
                track_points=track_points_by_session_id.get(session_id, []),
            )
        )

        if boat_id is None:
            continue

        if boat_id not in boats_by_id:
            boats_by_id[boat_id] = {
                "id": boat_id,
                "name": session_row["boat_name"] or "Unknown boat",
                "class_name": None,
                "sailnumber": None,
                "session_count": 0,
                "total_hours": 0.0,
                "total_distance_nm": 0.0,
                "max_speed_kts": None,
            }

        boat = boats_by_id[boat_id]
        boat["session_count"] += 1
        boat["total_hours"] += duration_hours
        boat["total_distance_nm"] += distance_nm

        if max_speed_kts is None:
            continue

        if boat["max_speed_kts"] is None or max_speed_kts > boat["max_speed_kts"]:
            boat["max_speed_kts"] = max_speed_kts

    boat_overviews = [
        DashboardBoatOverview(
            id=boat["id"],
            name=boat["name"],
            class_name=boat["class_name"],
            sailnumber=boat["sailnumber"],
            session_count=boat["session_count"],
            total_hours=boat["total_hours"],
            total_distance_nm=boat["total_distance_nm"],
            max_speed_kts=boat["max_speed_kts"],
        )
        for boat in sorted(boats_by_id.values(), key=lambda item: item["name"])
    ]

    total_hours = sum(boat.total_hours for boat in boat_overviews)
    total_distance_nm = sum(boat.total_distance_nm for boat in boat_overviews)

    return DashboardOverviewResponse(
        boat_count=len(boat_overviews),
        session_count=len(session_overviews),
        total_hours=total_hours,
        total_distance_nm=total_distance_nm,
        boats=boat_overviews,
        sessions=session_overviews,
    )
