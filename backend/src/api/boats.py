from __future__ import annotations

from typing import Any, Literal

from psycopg import Connection
from psycopg.rows import dict_row

from .models import BoatResponse, BoatWriteRequest


def _normalize_boat_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _fetch_boat_response(connection: Connection[Any], boat_id: str) -> BoatResponse | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT
                b.id::text AS id,
                b.name,
                bc.name AS class_name,
                b.sailnumber
            FROM boat AS b
            JOIN boat_class AS bc
                ON bc.id = b.class_id
            WHERE b.id::text = %s
            """,
            (boat_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return BoatResponse(
        id=str(row["id"]),
        name=row["name"],
        class_name=row["class_name"],
        sailnumber=row["sailnumber"],
    )


def _boat_name_exists(
    connection: Connection[Any], name: str, excluded_boat_id: str | None = None
) -> bool:
    with connection.cursor(row_factory=dict_row) as cursor:
        if excluded_boat_id is None:
            cursor.execute(
                """
                SELECT 1
                FROM boat
                WHERE lower(name) = lower(%s)
                LIMIT 1
                """,
                (name,),
            )
        else:
            cursor.execute(
                """
                SELECT 1
                FROM boat
                WHERE lower(name) = lower(%s)
                  AND id::text <> %s
                LIMIT 1
                """,
                (name, excluded_boat_id),
            )

        return cursor.fetchone() is not None


def _resolve_boat_class_id(connection: Connection[Any], class_name: str) -> str:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT id::text AS id
            FROM boat_class
            WHERE lower(name) = lower(%s)
            LIMIT 1
            """,
            (class_name,),
        )
        row = cursor.fetchone()
        if row is not None:
            return str(row["id"])

        cursor.execute(
            """
            INSERT INTO boat_class (name)
            VALUES (%s)
            RETURNING id::text AS id
            """,
            (class_name,),
        )
        created_row = cursor.fetchone()

    return str(created_row["id"])


def _create_boat(
    connection: Connection[Any], payload: BoatWriteRequest
) -> tuple[Literal["created", "duplicate"], BoatResponse | None]:
    name = _normalize_boat_text(payload.name, "Boat name")
    class_name = _normalize_boat_text(payload.class_name, "Class name")
    sailnumber = _normalize_boat_text(payload.sailnumber, "Sail number")

    if _boat_name_exists(connection, name):
        return "duplicate", None

    class_id = _resolve_boat_class_id(connection, class_name)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            INSERT INTO boat (name, class_id, sailnumber)
            VALUES (%s, %s, %s)
            RETURNING id::text AS id
            """,
            (name, class_id, sailnumber),
        )
        row = cursor.fetchone()

    return "created", _fetch_boat_response(connection, str(row["id"]))


def _update_boat(
    connection: Connection[Any], boat_id: str, payload: BoatWriteRequest
) -> tuple[Literal["updated", "not_found", "duplicate"], BoatResponse | None]:
    name = _normalize_boat_text(payload.name, "Boat name")
    class_name = _normalize_boat_text(payload.class_name, "Class name")
    sailnumber = _normalize_boat_text(payload.sailnumber, "Sail number")

    existing_boat = _fetch_boat_response(connection, boat_id)
    if existing_boat is None:
        return "not_found", None

    if _boat_name_exists(connection, name, excluded_boat_id=boat_id):
        return "duplicate", None

    class_id = _resolve_boat_class_id(connection, class_name)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE boat
            SET name = %s,
                class_id = %s,
                sailnumber = %s
            WHERE id::text = %s
            """,
            (name, class_id, sailnumber, boat_id),
        )

    return "updated", _fetch_boat_response(connection, boat_id)


def _delete_boat(
    connection: Connection[Any], boat_id: str
) -> Literal["deleted", "not_found"]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT id::text AS id
            FROM boat
            WHERE id::text = %s
            """,
            (boat_id,),
        )
        if cursor.fetchone() is None:
            return "not_found"

        cursor.execute(
            """
            DELETE FROM session
            WHERE boat_id::text = %s
            """,
            (boat_id,),
        )

        cursor.execute(
            """
            DELETE FROM boat
            WHERE id::text = %s
            """,
            (boat_id,),
        )

    return "deleted"
