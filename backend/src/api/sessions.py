from __future__ import annotations

from typing import Any, Literal

from psycopg import Connection
from psycopg.rows import dict_row

from .models import SessionResponse, SessionWriteRequest
from .session_data import _normalize_session_notes


def _normalize_session_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _fetch_session_response(
    connection: Connection[Any], session_id: str
) -> SessionResponse | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT id::text AS id, name, location, notes
            FROM session
            WHERE id::text = %s
            """,
            (session_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return SessionResponse(
        id=str(row["id"]),
        name=row["name"] or "Unnamed session",
        location=row["location"],
        notes=row["notes"],
    )


def _update_session(
    connection: Connection[Any], session_id: str, payload: SessionWriteRequest
) -> tuple[Literal["updated", "not_found"], SessionResponse | None]:
    name = _normalize_session_text(payload.name, "Session name")
    location = _normalize_session_text(payload.location, "Location")
    notes = _normalize_session_notes(payload.notes)

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            UPDATE session
            SET name = %s,
                location = %s,
                notes = %s
            WHERE id::text = %s
            RETURNING id::text AS id, name, location, notes
            """,
            (name, location, notes, session_id),
        )
        row = cursor.fetchone()

    if row is None:
        return "not_found", None

    return (
        "updated",
        SessionResponse(
            id=str(row["id"]),
            name=row["name"],
            location=row["location"],
            notes=row["notes"],
        ),
    )


def _delete_session(
    connection: Connection[Any], session_id: str
) -> Literal["deleted", "not_found"]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            DELETE FROM session
            WHERE id::text = %s
            RETURNING id::text AS id
            """,
            (session_id,),
        )
        row = cursor.fetchone()

    return "deleted" if row is not None else "not_found"
