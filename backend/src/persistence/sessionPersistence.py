from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import psycopg
from psycopg import Connection

from src.env import read_env_defaults
from src.models.canonicalSession import CanonicalSession, Channel
from src.projectPaths import PROJECT_ROOT

ChannelValueConverter = Callable[[Any], Any]


# TODO refactor into seperate files

@dataclass(frozen=True, slots=True)
class _ChannelInsertPlan:
    channel: Channel
    channel_id: uuid.UUID
    table_name: str
    value_converter: ChannelValueConverter


class SessionPersistence:
    CHANNEL_DATA_TABLE_REAL = "channel_data_real"
    CHANNEL_DATA_TABLE_BOOLEAN = "channel_data_boolean"
    CHANNEL_DATA_TABLE_STRING = "channel_data_string"
    ROOT_ENV_PATH = PROJECT_ROOT / ".env"

    def __init__(
        self,
        connection_factory: Callable[[], Connection[Any]] | None = None,
    ) -> None:
        self._connection_factory = connection_factory or self._connect_from_env

    def persist(self, session: CanonicalSession) -> None:
        session_id = self._coerce_session_id(session.metadata.session_id)
        boat_id = self._resolve_boat_id_reference(session.metadata.boat_id)

        with self._connection_factory() as connection:
            with connection.transaction():
                resolved_boat_id = self._lookup_boat_id(connection, boat_id)
                self._upsert_session_row(connection, session, session_id, resolved_boat_id)
                self._delete_previous_session_payload(connection, session_id)

                channel_plans = self._insert_channels(connection, session, session_id)
                self._insert_metrics(connection, session, session_id)
                self._insert_events(connection, session, session_id)
                self._insert_provenance(connection, session, session_id)
                self._copy_channel_values(connection, channel_plans)

    def _connect_from_env(self) -> Connection[Any]:
        env_defaults = self._read_root_env_defaults()

        db_host = os.getenv("POSTGRES_HOST") or env_defaults.get("POSTGRES_HOST") or "127.0.0.1"
        db_port = os.getenv("POSTGRES_PORT") or env_defaults.get("POSTGRES_PORT") or "5432"
        db_name = os.getenv("POSTGRES_DB") or env_defaults.get("POSTGRES_DB") or "sailing"
        db_user = os.getenv("POSTGRES_USER") or env_defaults.get("POSTGRES_USER")
        db_password = os.getenv("POSTGRES_PASSWORD")
        if db_password is None:
            db_password = env_defaults.get("POSTGRES_PASSWORD")

        if not db_user:
            raise ValueError("Missing database user: set POSTGRES_USER")
        if db_password is None:
            raise ValueError("Missing database password: set POSTGRES_PASSWORD")

        return psycopg.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
            options="-c timezone=UTC",
        )

    def _read_root_env_defaults(self) -> dict[str, str]:
        return read_env_defaults(self.ROOT_ENV_PATH)

    def _upsert_session_row(
        self,
        connection: Connection[Any],
        session: CanonicalSession,
        session_id: uuid.UUID,
        boat_id: uuid.UUID | None,
    ) -> None:
        metadata = session.metadata
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO session (
                    id,
                    name,
                    start_at,
                    end_at,
                    boat_id,
                    athlete_id,
                    source,
                    location,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    start_at = EXCLUDED.start_at,
                    end_at = EXCLUDED.end_at,
                    boat_id = EXCLUDED.boat_id,
                    athlete_id = EXCLUDED.athlete_id,
                    source = EXCLUDED.source,
                    location = EXCLUDED.location,
                    notes = EXCLUDED.notes
                """,
                (
                    session_id,
                    metadata.session_name,
                    self._coerce_timestamp(metadata.start_at),
                    self._coerce_timestamp(metadata.end_at),
                    boat_id,
                    metadata.athlete_id,
                    metadata.source_type,
                    metadata.location,
                    metadata.notes,
                ),
            )

    def _delete_previous_session_payload(
        self,
        connection: Connection[Any],
        session_id: uuid.UUID,
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM channel_data_real
                WHERE channel_id IN (
                    SELECT id FROM session_channel WHERE session_id = %s
                )
                """,
                (session_id,),
            )
            cursor.execute(
                """
                DELETE FROM channel_data_boolean
                WHERE channel_id IN (
                    SELECT id FROM session_channel WHERE session_id = %s
                )
                """,
                (session_id,),
            )
            cursor.execute(
                """
                DELETE FROM channel_data_string
                WHERE channel_id IN (
                    SELECT id FROM session_channel WHERE session_id = %s
                )
                """,
                (session_id,),
            )
            cursor.execute(
                "DELETE FROM session_metric WHERE session_id = %s",
                (session_id,),
            )
            cursor.execute(
                "DELETE FROM session_event WHERE session_id = %s",
                (session_id,),
            )
            cursor.execute(
                "DELETE FROM provenance_record WHERE session_id = %s",
                (session_id,),
            )
            cursor.execute(
                "DELETE FROM session_channel WHERE session_id = %s",
                (session_id,),
            )

    def _insert_channels(
        self,
        connection: Connection[Any],
        session: CanonicalSession,
        session_id: uuid.UUID,
    ) -> list[_ChannelInsertPlan]:
        channel_rows: list[tuple[uuid.UUID, str, uuid.UUID, str | None, str | None, bool]] = []
        channel_plans: list[_ChannelInsertPlan] = []

        for channel in session.channels.values():
            if channel.values.ndim != 1:
                raise ValueError(
                    f"Channel '{channel.name}' has {channel.values.ndim} dimensions. "
                    "Only 1D channel values can be persisted."
                )

            table_name, value_converter = self._resolve_channel_data_target(channel.values)
            channel_id = uuid.uuid4()

            channel_rows.append(
                (
                    channel_id,
                    channel.name,
                    session_id,
                    channel.unit,
                    channel.source,
                    channel.is_derived,
                )
            )
            channel_plans.append(
                _ChannelInsertPlan(
                    channel=channel,
                    channel_id=channel_id,
                    table_name=table_name,
                    value_converter=value_converter,
                )
            )

        if channel_rows:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO session_channel (
                        id,
                        name,
                        session_id,
                        unit,
                        source,
                        is_derived
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    channel_rows,
                )

        return channel_plans

    def _insert_metrics(
        self,
        connection: Connection[Any],
        session: CanonicalSession,
        session_id: uuid.UUID,
    ) -> None:
        metric_rows: list[tuple[uuid.UUID, uuid.UUID, str, float | None, str, str]] = []

        for metric in session.metrics.values():
            metric_rows.append(
                (
                    uuid.uuid4(),
                    session_id,
                    metric.name,
                    None if metric.value is None else float(metric.value),
                    metric.unit,
                    metric.source,
                )
            )

        if metric_rows:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO session_metric (
                        id,
                        session_id,
                        name,
                        value,
                        unit,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    metric_rows,
                )

    def _insert_events(
        self,
        connection: Connection[Any],
        session: CanonicalSession,
        session_id: uuid.UUID,
    ) -> None:
        event_rows: list[
            tuple[
                uuid.UUID,
                uuid.UUID,
                str,
                datetime | None,
                datetime | None,
                str,
                float | None,
                bool,
                float | None,
                float | None,
            ]
        ] = []

        for event in session.events:
            event_rows.append(
                (
                    uuid.uuid4(),
                    session_id,
                    event.event_type,
                    self._coerce_timestamp(event.start_time),
                    self._coerce_timestamp(event.end_time),
                    event.source,
                    None if event.confidence is None else float(event.confidence),
                    bool(event.foiling),
                    None if event.latitude is None else float(event.latitude),
                    None if event.longitude is None else float(event.longitude),
                )
            )

        if event_rows:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO session_event (
                        id,
                        session_id,
                        event_type,
                        start_time,
                        end_time,
                        source,
                        confidence,
                        foiling,
                        latitude,
                        longitude
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    event_rows,
                )

    def _insert_provenance(
        self,
        connection: Connection[Any],
        session: CanonicalSession,
        session_id: uuid.UUID,
    ) -> None:
        provenance_rows: list[tuple[uuid.UUID, uuid.UUID, str, str, str, str]] = []

        for record in session.provenance:
            provenance_rows.append(
                (
                    uuid.uuid4(),
                    session_id,
                    record.producer,
                    record.produced_type,
                    record.produced_name,
                    record.action,
                )
            )

        if provenance_rows:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO provenance_record (
                        id,
                        session_id,
                        producer,
                        produced_type,
                        produced_name,
                        action
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    provenance_rows,
                )

    def _copy_channel_values(
        self,
        connection: Connection[Any],
        channel_plans: list[_ChannelInsertPlan],
    ) -> None:
        if not channel_plans:
            return

        plans_by_table = {
            self.CHANNEL_DATA_TABLE_REAL: [],
            self.CHANNEL_DATA_TABLE_BOOLEAN: [],
            self.CHANNEL_DATA_TABLE_STRING: [],
        }
        for channel_plan in channel_plans:
            plans_by_table[channel_plan.table_name].append(channel_plan)

        for table_name, plans in plans_by_table.items():
            if not plans:
                continue

            with connection.cursor() as cursor:
                with cursor.copy(
                    f"COPY {table_name} (channel_id, timestamp, value) FROM STDIN"
                ) as copy:
                    for plan in plans:
                        timestamps = self._coerce_timestamp_array(plan.channel.timestamps)

                        for index, (timestamp, raw_value) in enumerate(
                            zip(timestamps, plan.channel.values, strict=True)
                        ):
                            if timestamp is None:
                                continue

                            try:
                                value = plan.value_converter(raw_value)
                            except (TypeError, ValueError) as exc:
                                raise ValueError(
                                    f"Unsupported value in channel '{plan.channel.name}' "
                                    f"at index {index}: {raw_value!r}"
                                ) from exc

                            if value is None:
                                continue

                            copy.write_row((plan.channel_id, timestamp, value))

    def _resolve_channel_data_target(
        self,
        values: np.ndarray,
    ) -> tuple[str, ChannelValueConverter]:
        value_kind = values.dtype.kind

        if value_kind == "b":
            return self.CHANNEL_DATA_TABLE_BOOLEAN, self._coerce_boolean_value
        if value_kind in {"i", "u", "f"}:
            return self.CHANNEL_DATA_TABLE_REAL, self._coerce_real_value
        if value_kind in {"U", "S", "M", "m"}:
            return self.CHANNEL_DATA_TABLE_STRING, self._coerce_string_value

        if value_kind == "O":
            non_null_value = next((value for value in values if value is not None), None)
            if non_null_value is None:
                return self.CHANNEL_DATA_TABLE_STRING, self._coerce_string_value

            if isinstance(non_null_value, (bool, np.bool_)):
                return self.CHANNEL_DATA_TABLE_BOOLEAN, self._coerce_boolean_value
            if isinstance(
                non_null_value,
                (int, float, np.integer, np.floating),
            ):
                return self.CHANNEL_DATA_TABLE_REAL, self._coerce_real_value

            return self.CHANNEL_DATA_TABLE_STRING, self._coerce_string_value

        raise TypeError(f"Unsupported channel value dtype: {values.dtype}")

    def _coerce_timestamp_array(self, timestamps: np.ndarray) -> list[datetime | None]:
        if np.issubdtype(timestamps.dtype, np.datetime64):
            converted = timestamps.astype("datetime64[us]").astype(datetime).tolist()
            return [self._ensure_utc_timestamp(value) for value in converted]

        if np.issubdtype(timestamps.dtype, np.number):
            timestamps_float = timestamps.astype(float, copy=False)
            result: list[datetime | None] = []
            for value in timestamps_float:
                if not np.isfinite(value):
                    result.append(None)
                    continue

                result.append(datetime.fromtimestamp(float(value), tz=timezone.utc))

            return result

        return [
            self._ensure_utc_timestamp(self._coerce_timestamp(value))
            for value in timestamps.tolist()
        ]

    def _coerce_timestamp(self, value: Any) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            return self._ensure_utc_timestamp(value)

        if isinstance(value, np.datetime64):
            if np.isnat(value):
                return None
            return self._ensure_utc_timestamp(
                value.astype("datetime64[us]").astype(datetime)
            )

        if isinstance(value, (int, float, np.integer, np.floating)):
            if not np.isfinite(value):
                return None
            return datetime.fromtimestamp(
                float(value), tz=timezone.utc
            )

        raise TypeError(f"Unsupported timestamp value type: {type(value).__name__}")

    def _ensure_utc_timestamp(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    def _coerce_real_value(self, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    def _coerce_boolean_value(self, value: Any) -> bool | None:
        if value is None:
            return None

        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "t", "1", "yes", "y"}:
                return True
            if normalized in {"false", "f", "0", "no", "n"}:
                return False

        raise TypeError(f"Unsupported boolean value type: {type(value).__name__}")

    def _coerce_string_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _coerce_session_id(self, session_id: str) -> uuid.UUID:
        try:
            return uuid.UUID(str(session_id))
        except ValueError:
            return uuid.uuid5(uuid.NAMESPACE_URL, str(session_id))

    def _resolve_boat_id_reference(self, boat_reference: str | None) -> uuid.UUID | str | None:
        if boat_reference is None:
            return None

        try:
            return uuid.UUID(boat_reference)
        except ValueError:
            return boat_reference

    def _lookup_boat_id(
        self,
        connection: Connection[Any],
        boat_reference: uuid.UUID | str | None,
    ) -> uuid.UUID | None:
        if boat_reference is None:
            return None

        if isinstance(boat_reference, uuid.UUID):
            return boat_reference

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM boat WHERE name = %s LIMIT 1",
                (boat_reference,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return row[0]
