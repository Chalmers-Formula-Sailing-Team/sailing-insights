from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Literal

import numpy as np
from psycopg import Connection
from psycopg.rows import dict_row

from src.analyzer.maneuverAnalyzer import ManeuverAnalyzer
from src.analyzer.windAngleAnlayzer import TWAAnalyzer
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Event,
    Metric,
    ProvenanceRecord,
    SessionMetadata,
)
from src.persistence.sessionPersistence import SessionPersistence

from .constants import (
    MANUAL_WAVE_HEIGHT_METRIC_NAME,
    MANUAL_WIND_DIRECTION_METRIC_NAME,
    MANUAL_WIND_SPEED_METRIC_NAME,
)
from .database import _coerce_float
from .models import (
    SessionDataChannel,
    SessionDataEvent,
    SessionDataMetric,
    SessionDataProvenanceRecord,
    SessionDataResponse,
    SessionDataSession,
    SessionDataValue,
    SessionRace,
)


def _fetch_session_data_session(
    connection: Connection[Any], session_id: str
) -> SessionDataSession | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                s.id::text AS id,
                s.name,
                s.start_at,
                s.end_at,
                s.boat_id::text AS boat_id,
                b.name AS boat_name,
                s.source,
                s.notes,
                COALESCE(
                    MAX(m.value) FILTER (WHERE m.name = 'avg_wind_speed_kn'),
                    MAX(m.value) FILTER (WHERE m.name = %s)
                ) AS wind_speed_kts,
                MAX(m.value) FILTER (WHERE m.name = 'avg_wind_gust_kn') AS wind_gust_kts,
                COALESCE(
                    MAX(m.value) FILTER (WHERE m.name = 'avg_wind_dir'),
                    MAX(m.value) FILTER (WHERE m.name = %s)
                ) AS wind_direction_deg,
                MAX(m.value) FILTER (WHERE m.name = %s) AS wave_height_m
            FROM session AS s
            LEFT JOIN boat AS b
                ON b.id = s.boat_id
            LEFT JOIN session_metric AS m
                ON m.session_id = s.id
            WHERE s.id::text = %s
            GROUP BY s.id, s.name, s.start_at, s.end_at, s.boat_id, b.name, s.source, s.notes
            """,
            (
                MANUAL_WIND_SPEED_METRIC_NAME,
                MANUAL_WIND_DIRECTION_METRIC_NAME,
                MANUAL_WAVE_HEIGHT_METRIC_NAME,
                session_id,
            ),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return SessionDataSession(
        id=str(row["id"]),
        name=row["name"] or "Unnamed session",
        start_at=row["start_at"],
        end_at=row["end_at"],
        boat_id=str(row["boat_id"]) if row["boat_id"] is not None else None,
        boat_name=row["boat_name"],
        source=row["source"],
        notes=row["notes"],
        wind_speed_kts=(
            _coerce_float(row["wind_speed_kts"], default=0.0)
            if row["wind_speed_kts"] is not None
            else None
        ),
        wind_gust_kts=(
            _coerce_float(row["wind_gust_kts"], default=0.0)
            if row["wind_gust_kts"] is not None
            else None
        ),
        wind_direction_deg=(
            _coerce_float(row["wind_direction_deg"], default=0.0)
            if row["wind_direction_deg"] is not None
            else None
        ),
        wave_height_m=(
            _coerce_float(row["wave_height_m"], default=0.0)
            if row["wave_height_m"] is not None
            else None
        ),
    )


def _fetch_session_data_channels(
    connection: Connection[Any],
    session_id: str,
    *,
    start_time: datetime | None = None,
    finish_time: datetime | None = None,
) -> list[SessionDataChannel]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                id::text AS id,
                name,
                unit,
                source,
                is_derived
            FROM session_channel
            WHERE session_id::text = %s
            ORDER BY name ASC, id ASC
            """,
            (session_id,),
        )
        channel_rows = list(cursor.fetchall())

    channels_by_id: dict[str, SessionDataChannel] = {
        str(row["id"]): SessionDataChannel(
            id=str(row["id"]),
            name=row["name"],
            unit=row["unit"],
            source=row["source"],
            is_derived=bool(row["is_derived"]),
            data_type="real",
            values=[],
        )
        for row in channel_rows
    }
    if not channels_by_id:
        return []

    channel_ids = list(channels_by_id)
    value_queries: tuple[tuple[str, Literal["real", "boolean", "string"]], ...] = (
        ("channel_data_real", "real"),
        ("channel_data_boolean", "boolean"),
        ("channel_data_string", "string"),
    )

    with connection.cursor(row_factory=dict_row) as cursor:
        for table_name, data_type in value_queries:
            timestamp_filter = ""
            params: tuple[object, ...] = (channel_ids,)
            if start_time is not None and finish_time is not None:
                timestamp_filter = """
                  AND timestamp >= %s
                  AND timestamp <= %s
                """
                params = (channel_ids, start_time, finish_time)

            cursor.execute(
                f"""
                SELECT
                    channel_id::text AS channel_id,
                    timestamp,
                    value
                FROM {table_name}
                WHERE channel_id::text = ANY(%s)
                {timestamp_filter}
                ORDER BY channel_id ASC, timestamp ASC
                """,
                params,
            )
            for value_row in cursor.fetchall():
                channel = channels_by_id.get(str(value_row["channel_id"]))
                if channel is None:
                    continue

                channel.data_type = data_type
                channel.values.append(
                    SessionDataValue(
                        timestamp=value_row["timestamp"],
                        value=value_row["value"],
                    )
                )

    return list(channels_by_id.values())


def _fetch_session_data_metrics(
    connection: Connection[Any], session_id: str
) -> list[SessionDataMetric]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                id::text AS id,
                name,
                value,
                unit,
                source
            FROM session_metric
            WHERE session_id::text = %s
            ORDER BY name ASC, id ASC
            """,
            (session_id,),
        )
        rows = list(cursor.fetchall())

    return [
        SessionDataMetric(
            id=str(row["id"]),
            name=row["name"],
            value=(
                _coerce_float(row["value"], default=0.0)
                if row["value"] is not None
                else None
            ),
            unit=row["unit"],
            source=row["source"],
        )
        for row in rows
    ]


def _fetch_session_data_events(
    connection: Connection[Any],
    session_id: str,
    *,
    start_time: datetime | None = None,
    finish_time: datetime | None = None,
) -> list[SessionDataEvent]:
    with connection.cursor(row_factory=dict_row) as cursor:
        time_filter = ""
        params: tuple[object, ...] = (session_id,)
        if start_time is not None and finish_time is not None:
            time_filter = """
              AND (
                    (start_time IS NOT NULL AND start_time >= %s AND start_time <= %s)
                 OR (end_time IS NOT NULL AND end_time >= %s AND end_time <= %s)
                 OR (
                        start_time IS NOT NULL
                    AND end_time IS NOT NULL
                    AND start_time <= %s
                    AND end_time >= %s
                 )
              )
            """
            params = (
                session_id,
                start_time,
                finish_time,
                start_time,
                finish_time,
                finish_time,
                start_time,
            )

        cursor.execute(
            """
            SELECT
                id::text AS id,
                event_type,
                start_time,
                end_time,
                source,
                confidence,
                foiling,
                latitude,
                longitude
            FROM session_event
            WHERE session_id::text = %s
            """
            + time_filter
            + """
            ORDER BY start_time ASC NULLS LAST, event_type ASC, id ASC
            """,
            params,
        )
        rows = list(cursor.fetchall())

    return [
        SessionDataEvent(
            id=str(row["id"]),
            event_type=row["event_type"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            source=row["source"],
            confidence=(
                _coerce_float(row["confidence"], default=0.0)
                if row["confidence"] is not None
                else None
            ),
            foiling=bool(row["foiling"]),
            latitude=(
                _coerce_float(row["latitude"], default=0.0)
                if row["latitude"] is not None
                else None
            ),
            longitude=(
                _coerce_float(row["longitude"], default=0.0)
                if row["longitude"] is not None
                else None
            ),
        )
        for row in rows
    ]


def _fetch_session_data_provenance(
    connection: Connection[Any], session_id: str
) -> list[SessionDataProvenanceRecord]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                id::text AS id,
                producer,
                produced_type,
                produced_name,
                action
            FROM provenance_record
            WHERE session_id::text = %s
            ORDER BY produced_type ASC, produced_name ASC, id ASC
            """,
            (session_id,),
        )
        rows = list(cursor.fetchall())

    return [
        SessionDataProvenanceRecord(
            id=str(row["id"]),
            producer=row["producer"],
            produced_type=row["produced_type"],
            produced_name=row["produced_name"],
            action=row["action"],
        )
        for row in rows
    ]


def _build_session_data_response(
    session: SessionDataSession,
    channels: list[SessionDataChannel],
    metrics: list[SessionDataMetric],
    events: list[SessionDataEvent],
    provenance: list[SessionDataProvenanceRecord],
    races: list[SessionRace],
) -> SessionDataResponse:
    return SessionDataResponse(
        session=session,
        channels=channels,
        metrics=metrics,
        events=events,
        provenance=provenance,
        races=races,
    )


def _normalize_session_notes(notes: str | None) -> str | None:
    if notes is None:
        return None

    normalized_notes = notes.replace("\r\n", "\n")
    return normalized_notes if normalized_notes.strip() else None


def _update_session_notes(
    connection: Connection[Any], session_id: str, notes: str | None
) -> tuple[bool, str | None]:
    normalized_notes = _normalize_session_notes(notes)

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            UPDATE session
            SET notes = %s
            WHERE id::text = %s
            RETURNING id::text AS session_id, notes
            """,
            (normalized_notes, session_id),
        )
        row = cursor.fetchone()

    if row is None:
        return False, None

    return True, row["notes"]


def _normalize_manual_wind_direction(
    direction_deg: float | None,
) -> float | None:
    if direction_deg is None:
        return None

    normalized_direction = float(direction_deg)
    if not isfinite(normalized_direction):
        return None

    return float(normalized_direction % 360.0)


def _update_manual_wind_direction(
    connection: Connection[Any], session_id: str, direction_deg: float | None
) -> tuple[bool, float | None]:
    normalized_direction = _normalize_manual_wind_direction(direction_deg)
    metric_source = "map_wind_picker"

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT id::text AS session_id
            FROM session
            WHERE id::text = %s
            """,
            (session_id,),
        )
        session_row = cursor.fetchone()
        if session_row is None:
            return False, None

        if normalized_direction is None:
            cursor.execute(
                """
                DELETE FROM session_metric
                WHERE session_id::text = %s
                  AND name = %s
                """,
                (session_id, MANUAL_WIND_DIRECTION_METRIC_NAME),
            )
            return True, None

        cursor.execute(
            """
            UPDATE session_metric
            SET value = %s, unit = %s, source = %s
            WHERE session_id::text = %s
              AND name = %s
            RETURNING value
            """,
            (
                normalized_direction,
                "deg",
                metric_source,
                session_id,
                MANUAL_WIND_DIRECTION_METRIC_NAME,
            ),
        )
        updated_row = cursor.fetchone()
        if updated_row is not None:
            return True, _coerce_float(updated_row["value"], default=0.0)

        cursor.execute(
            """
            INSERT INTO session_metric (
                session_id,
                name,
                value,
                unit,
                source
            )
            VALUES (%s::uuid, %s, %s, %s, %s)
            RETURNING value
            """,
            (
                session_id,
                MANUAL_WIND_DIRECTION_METRIC_NAME,
                normalized_direction,
                "deg",
                metric_source,
            ),
        )
        inserted_row = cursor.fetchone()

    return True, _coerce_float(inserted_row["value"], default=0.0)


def _recompute_session_twa_channels(
    connection: Connection[Any], session_id: str
) -> bool:
    session = _build_canonical_session_from_database(connection, session_id)
    if session is None:
        return False

    _remove_analyzer_outputs(session, producer_name="TWAAnalyzer")
    _remove_analyzer_outputs(session, producer_name="ManeuverAnalyzer")

    twa_analyzer = TWAAnalyzer()
    analyzed_session = twa_analyzer.analyze(session)
    maneuver_analyzer = ManeuverAnalyzer()
    analyzed_session = maneuver_analyzer.analyze(analyzed_session)
    _persist_session_with_existing_connection(connection, analyzed_session)
    print(f"twa: recomputed for session {session_id}")
    twa_analyzer.print_summary()
    maneuver_analyzer.print_summary()
    return True


def _build_canonical_session_from_database(
    connection: Connection[Any], session_id: str
) -> CanonicalSession | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                id::text AS id,
                name,
                start_at,
                end_at,
                boat_id::text AS boat_id,
                athlete_id::text AS athlete_id,
                source,
                notes
            FROM session
            WHERE id::text = %s
            """,
            (session_id,),
        )
        session_row = cursor.fetchone()

    if session_row is None:
        return None

    channels = {
        channel.name: _to_canonical_channel(channel)
        for channel in _fetch_session_data_channels(connection, session_id)
    }
    metrics = {
        metric.name: Metric(
            name=metric.name,
            value=metric.value,
            unit=metric.unit,
            source=metric.source,
        )
        for metric in _fetch_session_data_metrics(connection, session_id)
    }
    events = [
        Event(
            event_type=event.event_type,
            start_time=event.start_time,
            end_time=event.end_time,
            source=event.source,
            confidence=event.confidence,
            foiling=event.foiling,
            latitude=event.latitude,
            longitude=event.longitude,
        )
        for event in _fetch_session_data_events(connection, session_id)
    ]
    provenance = [
        ProvenanceRecord(
            producer=record.producer,
            produced_type=record.produced_type,
            produced_name=record.produced_name,
            action=record.action,
        )
        for record in _fetch_session_data_provenance(connection, session_id)
    ]

    return CanonicalSession(
        metadata=SessionMetadata(
            session_id=str(session_row["id"]),
            session_name=session_row["name"] or "",
            source_type=session_row["source"],
            athlete_id=session_row["athlete_id"],
            boat_id=session_row["boat_id"],
            start_at=session_row["start_at"],
            end_at=session_row["end_at"],
            notes=session_row["notes"],
        ),
        channels=channels,
        metrics=metrics,
        events=events,
        provenance=provenance,
    )


def _to_canonical_channel(channel: SessionDataChannel) -> Channel:
    raw_timestamps = [value.timestamp for value in channel.values]
    if raw_timestamps and all(timestamp is not None for timestamp in raw_timestamps):
        try:
            timestamps = np.asarray(raw_timestamps, dtype="datetime64[ns]")
        except (TypeError, ValueError):
            timestamps = np.asarray(raw_timestamps, dtype=object)
    else:
        timestamps = np.asarray(raw_timestamps, dtype=object)

    if channel.data_type == "boolean":
        values = np.asarray([bool(value.value) for value in channel.values], dtype=bool)
    elif channel.data_type == "string":
        values = np.asarray(
            [str(value.value) for value in channel.values], dtype=object
        )
    else:
        values = np.asarray(
            [
                _coerce_float(value.value, default=np.nan)
                if value.value is not None
                else np.nan
                for value in channel.values
            ],
            dtype=float,
        )

    return Channel(
        name=channel.name,
        timestamps=timestamps,
        values=values,
        unit=channel.unit,
        source=channel.source,
        is_derived=channel.is_derived,
    )


def _remove_analyzer_outputs(session: CanonicalSession, *, producer_name: str) -> None:
    produced_metric_names = {
        record.produced_name
        for record in session.provenance
        if record.producer == producer_name and record.produced_type == "metric"
    }
    produced_channel_names = {
        record.produced_name
        for record in session.provenance
        if record.producer == producer_name and record.produced_type == "channel"
    }
    produced_event_types = {
        record.produced_name
        for record in session.provenance
        if record.producer == producer_name and record.produced_type == "event"
    }

    for metric_name in produced_metric_names:
        session.metrics.pop(metric_name, None)
    for channel_name in produced_channel_names:
        session.channels.pop(channel_name, None)
    if produced_event_types:
        session.events = [
            event
            for event in session.events
            if not (
                event.source == producer_name
                and event.event_type in produced_event_types
            )
        ]

    session.provenance = [
        record for record in session.provenance if record.producer != producer_name
    ]


def _persist_session_with_existing_connection(
    connection: Connection[Any], session: CanonicalSession
) -> None:
    persistence = SessionPersistence(connection_factory=lambda: connection)
    session_id = persistence._coerce_session_id(session.metadata.session_id)
    boat_reference = persistence._resolve_boat_id_reference(session.metadata.boat_id)

    with connection.transaction():
        boat_id = persistence._lookup_boat_id(connection, boat_reference)
        persistence._upsert_session_row(connection, session, session_id, boat_id)
        persistence._delete_previous_session_payload(connection, session_id)
        channel_plans = persistence._insert_channels(connection, session, session_id)
        persistence._insert_metrics(connection, session, session_id)
        persistence._insert_events(connection, session, session_id)
        persistence._insert_provenance(connection, session, session_id)
        persistence._copy_channel_values(connection, channel_plans)
