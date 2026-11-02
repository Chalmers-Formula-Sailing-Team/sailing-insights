from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from .models import SessionDataChannel, SessionDataEvent, SessionDataSession, SessionRace
from .session_data import (
    _fetch_session_data_channels,
    _fetch_session_data_events,
    _fetch_session_data_session,
)


@dataclass(frozen=True, slots=True)
class ExportDocument:
    filename: str
    content: str


@dataclass(frozen=True, slots=True)
class SessionExportBundle:
    session: SessionDataSession
    channels: list[SessionDataChannel]
    events: list[SessionDataEvent]


@dataclass(frozen=True, slots=True)
class BoatSessionExportBundle:
    session: SessionDataSession
    channels: list[SessionDataChannel]
    events: list[SessionDataEvent]


@dataclass(frozen=True, slots=True)
class SessionRaceExportBundle:
    race: SessionRace
    bundle: SessionExportBundle


def _slugify_filename_part(value: str | None, fallback: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return fallback

    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or fallback


def _build_filename_date(value: datetime | None, fallback: str) -> str:
    if value is None:
        return fallback

    return _normalize_datetime(value).strftime("%Y%m%d")


def _build_session_export_base_name(
    session: SessionDataSession,
    scope_name: str,
) -> str:
    boat_name = _slugify_filename_part(session.boat_name, "unknown-boat")
    session_date = _build_filename_date(
        session.start_at or session.end_at,
        "undated",
    )
    scope = _slugify_filename_part(scope_name, "session")
    return f"{boat_name}_{session_date}_{scope}"


def _build_boat_export_base_name(
    boat_name: str | None,
    *,
    exported_at: datetime | None = None,
) -> str:
    normalized_boat_name = _slugify_filename_part(boat_name, "unknown-boat")
    export_date = _build_filename_date(exported_at or datetime.now(timezone.utc), "undated")
    return f"{normalized_boat_name}_exp_{export_date}"


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""

    return value.isoformat()


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _datetime_sort_key(value: datetime) -> float:
    return _normalize_datetime(value).timestamp()


def _format_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _normalize_event_type(value: str | None) -> str:
    return str(value or "").strip().lower()


def _resolve_session_export_bundle(
    connection: Connection[Any],
    session_id: str,
    *,
    start_time: datetime | None = None,
    finish_time: datetime | None = None,
) -> SessionExportBundle | None:
    session = _fetch_session_data_session(connection, session_id)
    if session is None:
        return None

    channels = _fetch_session_data_channels(
        connection,
        session_id,
        start_time=start_time,
        finish_time=finish_time,
    )
    events = _fetch_session_data_events(
        connection,
        session_id,
        start_time=start_time,
        finish_time=finish_time,
    )
    return SessionExportBundle(session=session, channels=channels, events=events)


def _fetch_boat_session_ids(connection: Connection[Any], boat_id: str) -> list[str]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT s.id::text AS id
            FROM session AS s
            WHERE s.boat_id::text = %s
            ORDER BY COALESCE(s.start_at, s.end_at) ASC NULLS LAST, s.name ASC, s.id ASC
            """,
            (boat_id,),
        )
        return [str(row["id"]) for row in cursor.fetchall()]


def _fetch_boat_name(connection: Connection[Any], boat_id: str) -> str | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT name
            FROM boat
            WHERE id::text = %s
            """,
            (boat_id,),
        )
        row = cursor.fetchone()
    return None if row is None else row["name"]


def _build_event_flags(
    timestamps: list[datetime],
    events: list[SessionDataEvent],
) -> tuple[list[bool], list[bool]]:
    tack_flags = [False] * len(timestamps)
    gybe_flags = [False] * len(timestamps)
    if not timestamps:
        return tack_flags, gybe_flags

    normalized_timestamps = [_normalize_datetime(timestamp) for timestamp in timestamps]
    timestamp_to_index = {
        normalized_timestamp: index
        for index, normalized_timestamp in enumerate(normalized_timestamps)
    }

    for event in events:
        normalized_type = _normalize_event_type(event.event_type)
        if normalized_type == "tack":
            target_flags = tack_flags
        elif normalized_type in {"gybe", "jibe"}:
            target_flags = gybe_flags
        else:
            continue

        start_time = event.start_time
        end_time = event.end_time or event.start_time
        if start_time is None and end_time is None:
            continue

        normalized_start_time = (
            _normalize_datetime(start_time) if start_time is not None else None
        )
        normalized_end_time = (
            _normalize_datetime(end_time) if end_time is not None else None
        )

        if (
            normalized_start_time is not None
            and normalized_end_time is not None
            and normalized_end_time < normalized_start_time
        ):
            normalized_start_time, normalized_end_time = (
                normalized_end_time,
                normalized_start_time,
            )

        if (
            normalized_start_time is not None
            and normalized_end_time is not None
            and normalized_start_time != normalized_end_time
        ):
            for index, timestamp in enumerate(normalized_timestamps):
                if normalized_start_time <= timestamp <= normalized_end_time:
                    target_flags[index] = True
            continue

        anchor_time = normalized_start_time or normalized_end_time
        if anchor_time is None:
            continue

        exact_index = timestamp_to_index.get(anchor_time)
        if exact_index is not None:
            target_flags[exact_index] = True
            continue

        nearest_index = min(
            range(len(normalized_timestamps)),
            key=lambda index: abs(
                (normalized_timestamps[index] - anchor_time).total_seconds()
            ),
        )
        target_flags[nearest_index] = True

    return tack_flags, gybe_flags


def _build_session_csv_content(
    bundle: SessionExportBundle,
    *,
    include_session_columns: bool,
) -> str:
    channel_names = [channel.name for channel in bundle.channels]
    timestamps = sorted(
        {
            value.timestamp
            for channel in bundle.channels
            for value in channel.values
        },
        key=_datetime_sort_key,
    )

    channel_values_by_name: dict[str, dict[datetime, Any]] = {}
    for channel in bundle.channels:
        channel_values_by_name[channel.name] = {
            value.timestamp: value.value for value in channel.values
        }

    tack_flags, gybe_flags = _build_event_flags(timestamps, bundle.events)

    fieldnames = ["timestamp"]
    if include_session_columns:
        fieldnames = ["session_id", "session_name", *fieldnames]
    fieldnames.extend(channel_names)
    fieldnames.extend(["event_tack", "event_gybe"])

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for index, timestamp in enumerate(timestamps):
        row: dict[str, str] = {"timestamp": _format_timestamp(timestamp)}
        if include_session_columns:
            row["session_id"] = bundle.session.id
            row["session_name"] = bundle.session.name

        for channel_name in channel_names:
            row[channel_name] = _format_csv_value(
                channel_values_by_name[channel_name].get(timestamp)
            )

        row["event_tack"] = _format_csv_value(tack_flags[index])
        row["event_gybe"] = _format_csv_value(gybe_flags[index])
        writer.writerow(row)

    return output.getvalue()


def _build_session_txt_content(
    bundle: SessionExportBundle,
    *,
    scope_label: str,
    include_session_columns: bool,
) -> str:
    lines = [
        f"Export scope: {scope_label}",
        f"Session: {bundle.session.name} ({bundle.session.id})",
        f"Boat: {bundle.session.boat_name or 'Unknown boat'}",
        f"Rows: one row per timestamp found in the exported channels.",
        "Timestamp column: ISO 8601.",
    ]
    if include_session_columns:
        lines.append(
            "Session columns: session_id and session_name identify which session each row belongs to."
        )

    lines.extend(
        [
            "Event columns:",
            "event_tack: true when the timestamp falls within a tack event, otherwise false.",
            "event_gybe: true when the timestamp falls within a gybe or jibe event, otherwise false.",
            "",
            "Channel columns:",
        ]
    )

    if not bundle.channels:
        lines.append("No channels were available for this export.")
    else:
        for channel in bundle.channels:
            unit = channel.unit or "unitless"
            source = channel.source or "unknown source"
            derived = "derived" if channel.is_derived else "raw"
            lines.append(
                f"- {channel.name}: unit={unit}; type={channel.data_type}; source={source}; {derived}."
            )

    return "\n".join(lines) + "\n"


def build_session_export_documents(bundle: SessionExportBundle) -> tuple[ExportDocument, ExportDocument]:
    base_name = _build_session_export_base_name(bundle.session, bundle.session.name)
    return (
        ExportDocument(
            filename=f"{base_name}.csv",
            content=_build_session_csv_content(bundle, include_session_columns=False),
        ),
        ExportDocument(
            filename=f"{base_name}.txt",
            content=_build_session_txt_content(
                bundle,
                scope_label="session",
                include_session_columns=False,
            ),
        ),
    )


def build_race_export_documents(
    bundle: SessionExportBundle,
    *,
    race_name: str,
    race_id: str,
) -> tuple[ExportDocument, ExportDocument]:
    race_base_name = _slugify_filename_part(race_name, f"race-{race_id}")
    base_name = _build_session_export_base_name(bundle.session, race_base_name)
    return (
        ExportDocument(
            filename=f"{base_name}.csv",
            content=_build_session_csv_content(bundle, include_session_columns=False),
        ),
        ExportDocument(
            filename=f"{base_name}.txt",
            content=_build_session_txt_content(
                bundle,
                scope_label=f"race ({race_name})",
                include_session_columns=False,
            ),
        ),
    )


def build_session_races_export_documents(
    session_name: str,
    session_id: str,
    race_bundles: list[SessionRaceExportBundle],
) -> tuple[ExportDocument, ExportDocument]:
    sorted_race_bundles = sorted(
        race_bundles,
        key=lambda race_bundle: (
            _format_timestamp(race_bundle.race.start_time),
            _format_timestamp(race_bundle.race.finish_time),
            race_bundle.race.name,
            race_bundle.race.id,
        ),
    )
    all_channel_names = sorted(
        {
            channel.name
            for race_bundle in sorted_race_bundles
            for channel in race_bundle.bundle.channels
        }
    )
    fieldnames = [
        "race_id",
        "race_name",
        "timestamp",
        *all_channel_names,
        "event_tack",
        "event_gybe",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    channel_notes: dict[str, set[str]] = defaultdict(set)

    for race_bundle in sorted_race_bundles:
        race_csv = _build_session_csv_content(
            race_bundle.bundle,
            include_session_columns=False,
        )
        reader = csv.DictReader(io.StringIO(race_csv))
        bundle_channel_names = {channel.name for channel in race_bundle.bundle.channels}

        for channel in race_bundle.bundle.channels:
            channel_notes[channel.name].add(
                f"unit={channel.unit or 'unitless'}; type={channel.data_type}; source={channel.source or 'unknown source'}; {'derived' if channel.is_derived else 'raw'}"
            )

        for row in reader:
            normalized_row = {name: "" for name in fieldnames}
            normalized_row["race_id"] = race_bundle.race.id
            normalized_row["race_name"] = race_bundle.race.name
            normalized_row["timestamp"] = row.get("timestamp", "")
            normalized_row["event_tack"] = row.get("event_tack", "false")
            normalized_row["event_gybe"] = row.get("event_gybe", "false")
            for channel_name in bundle_channel_names:
                normalized_row[channel_name] = row.get(channel_name, "")
            writer.writerow(normalized_row)

    txt_lines = [
        "Export scope: session races",
        f"Session: {session_name} ({session_id})",
        "Rows: one row per timestamp found inside the saved race windows only.",
        "Excluded data: timestamps between races are not included.",
        "Timestamp column: ISO 8601.",
        "Race columns: race_id and race_name identify which saved race each row belongs to.",
        "Event columns:",
        "event_tack: true when the timestamp falls within a tack event, otherwise false.",
        "event_gybe: true when the timestamp falls within a gybe or jibe event, otherwise false.",
        "",
        "Channel columns:",
    ]

    if not all_channel_names:
        txt_lines.append("No channels were available for this export.")
    else:
        for channel_name in all_channel_names:
            notes = sorted(channel_notes.get(channel_name) or {"no metadata available"})
            txt_lines.append(f"- {channel_name}: {' | '.join(notes)}")

    reference_session = (
        sorted_race_bundles[0].bundle.session
        if sorted_race_bundles
        else SessionDataSession(
            id=session_id,
            name=session_name,
            start_at=None,
            end_at=None,
            boat_id=None,
            boat_name=None,
            source=None,
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
            notes=None,
        )
    )
    base_name = _build_session_export_base_name(reference_session, "races")
    return (
        ExportDocument(
            filename=f"{base_name}.csv",
            content=output.getvalue(),
        ),
        ExportDocument(
            filename=f"{base_name}.txt",
            content="\n".join(txt_lines) + "\n",
        ),
    )


def build_boat_export_documents(
    boat_name: str | None,
    boat_id: str,
    bundles: list[BoatSessionExportBundle],
    *,
    exported_at: datetime | None = None,
) -> tuple[ExportDocument, ExportDocument]:
    sorted_bundles = sorted(
        bundles,
        key=lambda bundle: (
            _format_timestamp(bundle.session.start_at or bundle.session.end_at),
            bundle.session.name,
            bundle.session.id,
        ),
    )
    all_channel_names = sorted(
        {
            channel.name
            for bundle in sorted_bundles
            for channel in bundle.channels
        }
    )
    fieldnames = ["session_id", "session_name", "timestamp", *all_channel_names, "event_tack", "event_gybe"]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    channel_notes: dict[str, set[str]] = defaultdict(set)

    for bundle in sorted_bundles:
        session_csv = _build_session_csv_content(bundle, include_session_columns=True)
        reader = csv.DictReader(io.StringIO(session_csv))
        bundle_channel_names = {channel.name for channel in bundle.channels}

        for channel in bundle.channels:
            channel_notes[channel.name].add(
                f"unit={channel.unit or 'unitless'}; type={channel.data_type}; source={channel.source or 'unknown source'}; {'derived' if channel.is_derived else 'raw'}"
            )

        for row in reader:
            normalized_row = {name: "" for name in fieldnames}
            normalized_row["session_id"] = row.get("session_id", "")
            normalized_row["session_name"] = row.get("session_name", "")
            normalized_row["timestamp"] = row.get("timestamp", "")
            normalized_row["event_tack"] = row.get("event_tack", "false")
            normalized_row["event_gybe"] = row.get("event_gybe", "false")
            for channel_name in bundle_channel_names:
                normalized_row[channel_name] = row.get(channel_name, "")
            writer.writerow(normalized_row)

    txt_lines = [
        "Export scope: boat",
        f"Boat: {boat_name or 'Unknown boat'} ({boat_id})",
        "Rows: one row per timestamp found in each session's exported channels.",
        "Timestamp column: ISO 8601.",
        "Session columns: session_id and session_name identify which session each row belongs to.",
        "Event columns:",
        "event_tack: true when the timestamp falls within a tack event, otherwise false.",
        "event_gybe: true when the timestamp falls within a gybe or jibe event, otherwise false.",
        "",
        "Channel columns:",
    ]

    if not all_channel_names:
        txt_lines.append("No channels were available for this export.")
    else:
        for channel_name in all_channel_names:
            notes = sorted(channel_notes.get(channel_name) or {"no metadata available"})
            txt_lines.append(f"- {channel_name}: {' | '.join(notes)}")

    base_name = _build_boat_export_base_name(
        boat_name or boat_id,
        exported_at=exported_at,
    )
    return (
        ExportDocument(filename=f"{base_name}.csv", content=output.getvalue()),
        ExportDocument(filename=f"{base_name}.txt", content="\n".join(txt_lines) + "\n"),
    )
