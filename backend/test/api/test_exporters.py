from __future__ import annotations

from datetime import datetime, timezone

from src.api import (
    SessionDataChannel,
    SessionDataEvent,
    SessionDataSession,
    SessionDataValue,
    SessionRace,
)
from src.api.exporters import (
    SessionExportBundle,
    SessionRaceExportBundle,
    build_boat_export_documents,
    build_race_export_documents,
    build_session_export_documents,
    build_session_races_export_documents,
)


def test_build_session_export_documents_aligns_channels_and_marks_events() -> None:
    first = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    second = datetime(2026, 6, 1, 10, 0, 1, tzinfo=timezone.utc)
    third = datetime(2026, 6, 1, 10, 0, 2, tzinfo=timezone.utc)
    bundle = SessionExportBundle(
        session=SessionDataSession(
            id="session-1",
            name="Morning Session",
            start_at=first,
            end_at=third,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            wind_speed_kts=12.0,
            wind_gust_kts=15.0,
            wind_direction_deg=220.0,
            wave_height_m=0.5,
            notes="notes",
        ),
        channels=[
            SessionDataChannel(
                id="channel-1",
                name="sog",
                unit="kn",
                source="GarminAdapter",
                is_derived=False,
                data_type="real",
                values=[
                    SessionDataValue(timestamp=first, value=12.3),
                    SessionDataValue(timestamp=third, value=13.1),
                ],
            ),
            SessionDataChannel(
                id="channel-2",
                name="heel",
                unit="deg",
                source="GarminAdapter",
                is_derived=False,
                data_type="real",
                values=[
                    SessionDataValue(timestamp=second, value=18.5),
                ],
            ),
        ],
        events=[
            SessionDataEvent(
                id="event-1",
                event_type="tack",
                start_time=second,
                end_time=third,
                source="ManeuverAnalyzer",
                confidence=0.9,
                foiling=False,
            ),
            SessionDataEvent(
                id="event-2",
                event_type="gybe",
                start_time=first,
                end_time=first,
                source="ManeuverAnalyzer",
                confidence=0.8,
                foiling=False,
            ),
        ],
    )

    csv_document, txt_document = build_session_export_documents(bundle)

    assert csv_document.filename == "sips_20260601_morning-session.csv"
    assert "timestamp,sog,heel,event_tack,event_gybe" in csv_document.content
    assert "2026-06-01T10:00:00+00:00,12.3,,false,true" in csv_document.content
    assert "2026-06-01T10:00:01+00:00,,18.5,true,false" in csv_document.content
    assert "2026-06-01T10:00:02+00:00,13.1,,true,false" in csv_document.content
    assert "event_tack: true when the timestamp falls within a tack event" in txt_document.content
    assert "- sog: unit=kn; type=real; source=GarminAdapter; raw." in txt_document.content


def test_build_race_export_documents_use_race_name_in_filename() -> None:
    timestamp = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    bundle = SessionExportBundle(
        session=SessionDataSession(
            id="session-1",
            name="Afternoon Session",
            start_at=timestamp,
            end_at=timestamp,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            wind_speed_kts=12.0,
            wind_gust_kts=15.0,
            wind_direction_deg=220.0,
            wave_height_m=0.5,
            notes=None,
        ),
        channels=[],
        events=[],
    )

    csv_document, txt_document = build_race_export_documents(
        bundle,
        race_name="Race 3",
        race_id="race-3",
    )

    assert csv_document.filename == "sips_20260601_race-3.csv"
    assert txt_document.filename == "sips_20260601_race-3.txt"
    assert "Export scope: race (Race 3)" in txt_document.content


def test_build_boat_export_documents_include_session_columns() -> None:
    first = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    second = datetime(2026, 6, 2, 11, 0, 0, tzinfo=timezone.utc)
    first_bundle = SessionExportBundle(
        session=SessionDataSession(
            id="session-1",
            name="Morning",
            start_at=first,
            end_at=first,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
            notes=None,
        ),
        channels=[
            SessionDataChannel(
                id="channel-1",
                name="sog",
                unit="kn",
                source="GarminAdapter",
                is_derived=False,
                data_type="real",
                values=[SessionDataValue(timestamp=first, value=11.2)],
            )
        ],
        events=[],
    )
    second_bundle = SessionExportBundle(
        session=SessionDataSession(
            id="session-2",
            name="Afternoon",
            start_at=second,
            end_at=second,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
            notes=None,
        ),
        channels=[
            SessionDataChannel(
                id="channel-2",
                name="twa",
                unit="deg",
                source="TWAAnalyzer",
                is_derived=True,
                data_type="real",
                values=[SessionDataValue(timestamp=second, value=-42.0)],
            )
        ],
        events=[],
    )

    csv_document, txt_document = build_boat_export_documents(
        "SIPS",
        "boat-1",
        [first_bundle, second_bundle],
        exported_at=datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert csv_document.filename == "sips_exp_20260609.csv"
    assert "session_id,session_name,timestamp,sog,twa,event_tack,event_gybe" in csv_document.content
    assert "session-1,Morning,2026-06-01T10:00:00+00:00,11.2,,false,false" in csv_document.content
    assert "session-2,Afternoon,2026-06-02T11:00:00+00:00,,-42.0,false,false" in csv_document.content
    assert "Session columns: session_id and session_name identify which session each row belongs to." in txt_document.content
    assert "- sog: unit=kn; type=real; source=GarminAdapter; raw" in txt_document.content
    assert "- twa: unit=deg; type=real; source=TWAAnalyzer; derived" in txt_document.content


def test_build_session_races_export_documents_include_only_race_rows() -> None:
    first = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    second = datetime(2026, 6, 1, 10, 5, 0, tzinfo=timezone.utc)
    third = datetime(2026, 6, 1, 10, 10, 0, tzinfo=timezone.utc)
    fourth = datetime(2026, 6, 1, 10, 15, 0, tzinfo=timezone.utc)
    first_bundle = SessionExportBundle(
        session=SessionDataSession(
            id="session-1",
            name="Race Day",
            start_at=first,
            end_at=fourth,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
            notes=None,
        ),
        channels=[
            SessionDataChannel(
                id="channel-1",
                name="sog",
                unit="kn",
                source="GarminAdapter",
                is_derived=False,
                data_type="real",
                values=[SessionDataValue(timestamp=first, value=11.2)],
            )
        ],
        events=[],
    )
    second_bundle = SessionExportBundle(
        session=SessionDataSession(
            id="session-1",
            name="Race Day",
            start_at=first,
            end_at=fourth,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
            notes=None,
        ),
        channels=[
            SessionDataChannel(
                id="channel-2",
                name="twa",
                unit="deg",
                source="TWAAnalyzer",
                is_derived=True,
                data_type="real",
                values=[SessionDataValue(timestamp=fourth, value=-42.0)],
            )
        ],
        events=[],
    )

    csv_document, txt_document = build_session_races_export_documents(
        "Race Day",
        "session-1",
        [
            SessionRaceExportBundle(
                race=SessionRace(
                    id="race-1",
                    session_id="session-1",
                    name="Race 1",
                    start_time=first,
                    finish_time=second,
                ),
                bundle=first_bundle,
            ),
            SessionRaceExportBundle(
                race=SessionRace(
                    id="race-2",
                    session_id="session-1",
                    name="Race 2",
                    start_time=third,
                    finish_time=fourth,
                ),
                bundle=second_bundle,
            ),
        ],
    )

    assert csv_document.filename == "sips_20260601_races.csv"
    assert "race_id,race_name,timestamp,sog,twa,event_tack,event_gybe" in csv_document.content
    assert "race-1,Race 1,2026-06-01T10:00:00+00:00,11.2,,false,false" in csv_document.content
    assert "race-2,Race 2,2026-06-01T10:15:00+00:00,,-42.0,false,false" in csv_document.content
    assert "Excluded data: timestamps between races are not included." in txt_document.content
    assert "Race columns: race_id and race_name identify which saved race each row belongs to." in txt_document.content


def test_build_session_export_documents_handles_mixed_naive_and_aware_datetimes() -> None:
    naive_timestamp = datetime(2026, 6, 1, 10, 0, 0)
    aware_timestamp = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    bundle = SessionExportBundle(
        session=SessionDataSession(
            id="session-1",
            name="Mixed Timezones",
            start_at=aware_timestamp,
            end_at=aware_timestamp,
            boat_id="boat-1",
            boat_name="SIPS",
            source="garmin",
            wind_speed_kts=None,
            wind_gust_kts=None,
            wind_direction_deg=None,
            wave_height_m=None,
            notes=None,
        ),
        channels=[
            SessionDataChannel(
                id="channel-1",
                name="sog",
                unit="kn",
                source="GarminAdapter",
                is_derived=False,
                data_type="real",
                values=[SessionDataValue(timestamp=naive_timestamp, value=12.3)],
            )
        ],
        events=[
            SessionDataEvent(
                id="event-1",
                event_type="tack",
                start_time=aware_timestamp,
                end_time=aware_timestamp,
                source="ManeuverAnalyzer",
                confidence=0.8,
                foiling=False,
            )
        ],
    )

    csv_document, _ = build_session_export_documents(bundle)

    assert "timestamp,sog,event_tack,event_gybe" in csv_document.content
    assert "2026-06-01T10:00:00,12.3,true,false" in csv_document.content
