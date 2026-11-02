from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from .models import SessionRace


def _fetch_session_races(
    connection: Connection[Any], session_id: str
) -> list[SessionRace]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                id::text AS id,
                session_id::text AS session_id,
                name,
                start_time,
                finish_time
            FROM race
            WHERE session_id::text = %s
            ORDER BY start_time ASC, finish_time ASC, id ASC
            """,
            (session_id,),
        )
        rows = list(cursor.fetchall())

    return [
        SessionRace(
            id=str(row["id"]),
            session_id=str(row["session_id"]),
            name=row["name"],
            start_time=row["start_time"],
            finish_time=row["finish_time"],
        )
        for row in rows
    ]


def _fetch_session_race(
    connection: Connection[Any], session_id: str, race_id: str
) -> SessionRace | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                id::text AS id,
                session_id::text AS session_id,
                name,
                start_time,
                finish_time
            FROM race
            WHERE session_id::text = %s
              AND id::text = %s
            """,
            (session_id, race_id),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return SessionRace(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        name=row["name"],
        start_time=row["start_time"],
        finish_time=row["finish_time"],
    )


def _create_session_race(
    connection: Connection[Any],
    session_id: str,
    name: str,
    start_time: datetime,
    finish_time: datetime,
) -> SessionRace | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            WITH target_session AS (
                SELECT id
                FROM session
                WHERE id::text = %s
            )
            INSERT INTO race (session_id, name, start_time, finish_time)
            SELECT
                target_session.id,
                %s,
                %s,
                %s
            FROM target_session
            RETURNING
                id::text AS id,
                session_id::text AS session_id,
                name,
                start_time,
                finish_time
            """,
            (session_id, name, start_time, finish_time),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return SessionRace(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        name=row["name"],
        start_time=row["start_time"],
        finish_time=row["finish_time"],
    )


def _update_session_race(
    connection: Connection[Any],
    session_id: str,
    race_id: str,
    name: str,
    start_time: datetime,
    finish_time: datetime,
) -> SessionRace | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            UPDATE race
            SET name = %s,
                start_time = %s,
                finish_time = %s
            WHERE session_id::text = %s
              AND id::text = %s
            RETURNING
                id::text AS id,
                session_id::text AS session_id,
                name,
                start_time,
                finish_time
            """,
            (name, start_time, finish_time, session_id, race_id),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return SessionRace(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        name=row["name"],
        start_time=row["start_time"],
        finish_time=row["finish_time"],
    )


def _delete_session_race(
    connection: Connection[Any], session_id: str, race_id: str
) -> bool:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            DELETE FROM race
            WHERE session_id::text = %s
              AND id::text = %s
            RETURNING id::text AS id
            """,
            (session_id, race_id),
        )
        row = cursor.fetchone()

    return row is not None
