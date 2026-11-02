import numpy as np
import pytest
from src.analyzer.maneuverAnalyzer import ManeuverAnalyzer
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Metric,
    SessionMetadata,
)


def _build_session(
    *,
    timestamps: np.ndarray,
    speed_values: np.ndarray,
    base_twa_values: np.ndarray | None = None,
    manual_twa_values: np.ndarray | None = None,
) -> CanonicalSession:
    channels = {
        ChannelNames.LATITUDE.value: Channel(
            name=ChannelNames.LATITUDE.value,
            timestamps=timestamps.copy(),
            values=np.zeros(len(timestamps), dtype=float),
            unit="deg",
            source="gps",
        ),
        ChannelNames.LONGITUDE.value: Channel(
            name=ChannelNames.LONGITUDE.value,
            timestamps=timestamps.copy(),
            values=np.zeros(len(timestamps), dtype=float),
            unit="deg",
            source="gps",
        ),
        ChannelNames.SOG.value: Channel(
            name=ChannelNames.SOG.value,
            timestamps=timestamps.copy(),
            values=np.asarray(speed_values, dtype=float),
            unit="kn",
            source="gps",
        ),
    }

    if base_twa_values is not None:
        channels[ChannelNames.TWA.value] = Channel(
            name=ChannelNames.TWA.value,
            timestamps=timestamps.copy(),
            values=np.asarray(base_twa_values, dtype=float),
            unit="deg",
            source="sailmon_csv",
        )

    if manual_twa_values is not None:
        channels[
            f"{ChannelNames.TWA.value}_{MetricNames.MANUAL_WIND_DIRECTION.value}"
        ] = Channel(
            name=f"{ChannelNames.TWA.value}_{MetricNames.MANUAL_WIND_DIRECTION.value}",
            timestamps=timestamps.copy(),
            values=np.asarray(manual_twa_values, dtype=float),
            unit="deg",
            source="TWAAnalyzer",
            is_derived=True,
            metadata={
                "wind_direction_reference": MetricNames.MANUAL_WIND_DIRECTION.value,
                "wind_direction_reference_type": "metric",
                "wind_direction_alignment": "constant_manual_direction",
            },
        )

    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-maneuvers"),
        channels=channels,
        metrics={
            MetricNames.MANUAL_WIND_DIRECTION.value: Metric(
                name=MetricNames.MANUAL_WIND_DIRECTION.value,
                value=45.0,
                unit="deg",
                source="map_wind_picker",
            )
        },
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"min_tack_entry_speed_kn": -1.0},
            "min_tack_entry_speed must be greater than or equal to 0",
        ),
        (
            {"min_gybe_entry_speed_kn": -1.0},
            "min_gybe_entry_speed must be greater than or equal to 0",
        ),
        (
            {"min_entry_speed_percentage": -0.1},
            "min_entry_speed_percentage must be in \\[0,1\\]",
        ),
        (
            {"min_entry_speed_percentage": 1.1},
            "min_entry_speed_percentage must be in \\[0,1\\]",
        ),
        (
            {"foiling_percentage": -0.1},
            "foiling_percentage must be in \\[0,1\\]",
        ),
        (
            {"foiling_percentage": 1.1},
            "foiling_percentage must be in \\[0,1\\]",
        ),
    ],
)
def test_init_rejects_invalid_percentage_and_entry_thresholds(
    kwargs: dict[str, float],
    message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=message,
    ):
        ManeuverAnalyzer(**kwargs)


@pytest.mark.parametrize(
    ("previous_twa", "current_twa", "expected_event_type"),
    [
        (-40.0, 40.0, "tack"),
        (40.0, -40.0, "tack"),
        (-120.0, 120.0, "gybe"),
        (120.0, -120.0, "gybe"),
        (-120.0, 180.0, "gybe"),
        (-10.0, 0.0, "tack"),
    ],
)
def test_determine_event_type_distinguishes_zero_crossing_from_wrap(
    previous_twa: float,
    current_twa: float,
    expected_event_type: str,
) -> None:
    analyzer = ManeuverAnalyzer()

    event_type = analyzer._determine_event_type(
        1,
        np.array([0.0, 1.0], dtype=float),
        np.array([previous_twa, current_twa], dtype=float),
    )

    assert event_type == expected_event_type


def test_determine_event_type_uses_classification_window_average() -> None:
    analyzer = ManeuverAnalyzer(classification_interval_seconds=3.0)

    event_type = analyzer._determine_event_type(
        4,
        np.arange(0.0, 8.0, 1.0, dtype=float),
        np.array([-42.0, -38.0, -44.0, -118.0, 39.0, 43.0, 41.0, 40.0]),
    )

    assert event_type == "tack"


def test_determine_event_type_rejects_invalid_index() -> None:
    analyzer = ManeuverAnalyzer()

    with pytest.raises(
        ValueError, match="maneuver index must have a previous TWA sample"
    ):
        analyzer._determine_event_type(
            0,
            np.array([0.0, 1.0], dtype=float),
            np.array([-40.0, 40.0], dtype=float),
        )


def test_determine_event_type_rejects_missing_twa_context() -> None:
    analyzer = ManeuverAnalyzer()

    with pytest.raises(ValueError, match="without finite TWA values"):
        analyzer._determine_event_type(
            1,
            np.array([0.0, 1.0], dtype=float),
            np.array([np.nan, np.nan], dtype=float),
        )


def test_analyze_prefers_manual_twa_channel_and_detects_non_foiling_tack() -> None:
    timestamps = np.arange(0.0, 26.0, 1.0, dtype=float)
    session = _build_session(
        timestamps=timestamps,
        speed_values=np.full(len(timestamps), 8.0, dtype=float),
        base_twa_values=np.full(len(timestamps), 150.0, dtype=float),
        manual_twa_values=np.concatenate(
            [
                np.full(8, -40.0, dtype=float),
                np.full(len(timestamps) - 8, 40.0, dtype=float),
            ]
        ),
    )

    result = ManeuverAnalyzer().analyze(session)

    tack_events = result.get_events(event_type="tack")
    gybe_events = result.get_events(event_type="gybe")
    assert len(tack_events) == 1
    assert len(gybe_events) == 0
    assert tack_events[0].start_time == 8.0
    assert tack_events[0].foiling is False
    assert tack_events[0].metadata["foiling_maneuver"] is False

    assert result.get_metric(MetricNames.TACK_COUNT.value).value == pytest.approx(1.0)
    assert result.get_metric(MetricNames.GYBE_COUNT.value).value == pytest.approx(0.0)
    assert result.get_metric(
        MetricNames.FOILING_TACK_COUNT.value
    ).value == pytest.approx(0.0)
    assert result.get_metric(
        MetricNames.FOILING_GYBE_COUNT.value
    ).value == pytest.approx(0.0)
    assert result.get_metric(
        MetricNames.FOILING_TACK_PERCENTAGE.value
    ).value == pytest.approx(0.0)
    assert result.get_metric(
        MetricNames.FOILING_GYBE_PERCENTAGE.value
    ).value == pytest.approx(0.0)

    assert len(result.provenance) == 7
    event_records = [
        record for record in result.provenance if record.produced_type == "event"
    ]
    assert len(event_records) == 1
    assert event_records[0].produced_name == "tack"
    assert event_records[0].inputs == [
        f"{ChannelNames.TWA.value}_{MetricNames.MANUAL_WIND_DIRECTION.value}",
        ChannelNames.SOG.value,
    ]


def test_foiling_speed_windows_exclude_maneuver_sample() -> None:
    timestamps = np.arange(0.0, 12.0, 1.0, dtype=float)
    speed_values = np.array(
        [8.0, 8.0, 8.0, 8.0, 8.0, 50.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0],
        dtype=float,
    )
    session = _build_session(
        timestamps=timestamps,
        speed_values=speed_values,
        manual_twa_values=np.concatenate(
            [
                np.full(5, -40.0, dtype=float),
                np.full(len(timestamps) - 5, 40.0, dtype=float),
            ]
        ),
    )

    result = ManeuverAnalyzer().analyze(session)

    tack_events = result.get_events(event_type="tack")
    assert len(tack_events) == 1
    assert tack_events[0].start_time == 5.0
    assert tack_events[0].metadata["avg_speed_before_kn"] == pytest.approx(8.0)
    assert tack_events[0].metadata["avg_speed_after_kn"] == pytest.approx(6.0)
    assert tack_events[0].foiling is False
    assert tack_events[0].metadata["foiling_maneuver"] is False


def test_tack_detection_uses_tack_entry_speed_percentage() -> None:
    timestamps = np.arange(0.0, 12.0, 1.0, dtype=float)
    session = _build_session(
        timestamps=timestamps,
        speed_values=np.array(
            [8.0, 8.0, 1.4, 1.4, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0],
            dtype=float,
        ),
        manual_twa_values=np.concatenate(
            [
                np.full(5, -40.0, dtype=float),
                np.full(len(timestamps) - 5, 40.0, dtype=float),
            ]
        ),
    )

    result = ManeuverAnalyzer(
        min_tack_entry_speed_kn=1.5,
        min_entry_speed_percentage=0.75,
    ).analyze(session)

    assert result.get_events(event_type="tack") == []
    assert result.get_metric(MetricNames.TACK_COUNT.value).value == pytest.approx(0.0)


def test_gybe_detection_uses_gybe_entry_speed_percentage() -> None:
    timestamps = np.arange(0.0, 12.0, 1.0, dtype=float)
    session = _build_session(
        timestamps=timestamps,
        speed_values=np.array(
            [8.0, 8.0, 1.9, 1.9, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0],
            dtype=float,
        ),
        manual_twa_values=np.concatenate(
            [
                np.full(5, -120.0, dtype=float),
                np.full(len(timestamps) - 5, 120.0, dtype=float),
            ]
        ),
    )

    result = ManeuverAnalyzer(
        min_gybe_entry_speed_kn=2.0,
        min_entry_speed_percentage=0.75,
    ).analyze(session)

    assert result.get_events(event_type="gybe") == []
    assert result.get_metric(MetricNames.GYBE_COUNT.value).value == pytest.approx(0.0)


def test_analyze_dedupes_close_candidates_and_classifies_gybe() -> None:
    timestamps = np.arange(0.0, 41.0, 1.0, dtype=float)
    twa_values = np.concatenate(
        [
            np.full(5, -120.0, dtype=float),
            np.full(7, 120.0, dtype=float),
            np.full(len(timestamps) - 12, -120.0, dtype=float),
        ]
    )
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-gybe"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=timestamps.copy(),
                values=np.zeros(len(timestamps), dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=timestamps.copy(),
                values=np.zeros(len(timestamps), dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=timestamps.copy(),
                values=np.full(len(timestamps), 5.0, dtype=float),
                unit="kn",
                source="gps",
            ),
            ChannelNames.TWA.value: Channel(
                name=ChannelNames.TWA.value,
                timestamps=timestamps.copy(),
                values=twa_values,
                unit="deg",
                source="sailmon_csv",
            ),
        },
    )

    result = ManeuverAnalyzer().analyze(session)

    tack_events = result.get_events(event_type="tack")
    gybe_events = result.get_events(event_type="gybe")
    assert len(tack_events) == 0
    assert len(gybe_events) == 1
    assert gybe_events[0].start_time == 5.0
    assert gybe_events[0].foiling is False
    assert gybe_events[0].metadata["foiling_maneuver"] is False

    assert result.get_metric(MetricNames.TACK_COUNT.value).value == pytest.approx(0.0)
    assert result.get_metric(MetricNames.GYBE_COUNT.value).value == pytest.approx(1.0)
    assert result.get_metric(
        MetricNames.FOILING_GYBE_PERCENTAGE.value
    ).value == pytest.approx(0.0)


def test_gybe_is_foiling_when_enough_window_samples_stay_above_threshold() -> None:
    timestamps = np.arange(0.0, 14.0, 1.0, dtype=float)
    session = _build_session(
        timestamps=timestamps,
        speed_values=np.array(
            [8.0, 8.0, 8.0, 8.0, 8.0, 9.0, 11.0, 10.0, 8.5, 8.0, 8.0, 8.0, 8.0, 8.0],
            dtype=float,
        ),
        manual_twa_values=np.concatenate(
            [
                np.full(6, -120.0, dtype=float),
                np.full(len(timestamps) - 6, 120.0, dtype=float),
            ]
        ),
    )

    result = ManeuverAnalyzer().analyze(session)

    gybe_events = result.get_events(event_type="gybe")
    assert len(gybe_events) == 1
    assert gybe_events[0].foiling is True
    assert gybe_events[0].metadata["foiling_maneuver"] is True


def test_gybe_is_not_foiling_when_window_samples_drop_below_required_percentage() -> (
    None
):
    timestamps = np.arange(0.0, 14.0, 1.0, dtype=float)
    session = _build_session(
        timestamps=timestamps,
        speed_values=np.array(
            [8.0, 8.0, 8.0, 8.0, 8.0, 9.0, 11.0, 6.7, 6.6, 8.0, 8.0, 8.0, 8.0, 8.0],
            dtype=float,
        ),
        manual_twa_values=np.concatenate(
            [
                np.full(6, -120.0, dtype=float),
                np.full(len(timestamps) - 6, 120.0, dtype=float),
            ]
        ),
    )

    result = ManeuverAnalyzer().analyze(session)

    gybe_events = result.get_events(event_type="gybe")
    assert len(gybe_events) == 1
    assert gybe_events[0].metadata["avg_speed_before_kn"] == pytest.approx(8.2)
    assert gybe_events[0].metadata["avg_speed_after_kn"] == pytest.approx(
        7.46, abs=0.01
    )
    assert gybe_events[0].foiling is False
    assert gybe_events[0].metadata["foiling_maneuver"] is False


def test_gybe_foiling_percentage_can_be_configured() -> None:
    timestamps = np.arange(0.0, 14.0, 1.0, dtype=float)
    session = _build_session(
        timestamps=timestamps,
        speed_values=np.array(
            [8.0, 8.0, 8.0, 8.0, 8.0, 9.0, 11.0, 6.7, 6.6, 8.0, 8.0, 8.0, 8.0, 8.0],
            dtype=float,
        ),
        manual_twa_values=np.concatenate(
            [
                np.full(6, -120.0, dtype=float),
                np.full(len(timestamps) - 6, 120.0, dtype=float),
            ]
        ),
    )

    result = ManeuverAnalyzer(foiling_percentage=0.6).analyze(session)

    gybe_events = result.get_events(event_type="gybe")
    assert len(gybe_events) == 1
    assert gybe_events[0].foiling is True
    assert result.get_metric(
        MetricNames.FOILING_GYBE_PERCENTAGE.value
    ).value == pytest.approx(100.0)


def test_print_summary_reports_maneuver_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    timestamps = np.arange(0.0, 26.0, 1.0, dtype=float)
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-summary"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=timestamps.copy(),
                values=np.zeros(len(timestamps), dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=timestamps.copy(),
                values=np.zeros(len(timestamps), dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=timestamps.copy(),
                values=np.full(len(timestamps), 8.0, dtype=float),
                unit="kn",
                source="gps",
            ),
            ChannelNames.TWA.value: Channel(
                name=ChannelNames.TWA.value,
                timestamps=timestamps.copy(),
                values=np.concatenate(
                    [
                        np.full(8, -40.0, dtype=float),
                        np.full(len(timestamps) - 8, 40.0, dtype=float),
                    ]
                ),
                unit="deg",
                source="TWAAnalyzer",
            ),
        },
    )
    analyzer = ManeuverAnalyzer()

    analyzer.analyze(session)
    analyzer.print_summary()

    assert (
        capsys.readouterr().out
        == "maneuvers: 1 tacks (0 foiling, 0.0%), 0 gybes (0 foiling, 0.0%)\n"
        "1970-01-01T00:00:08Z | tack | 8.0 kn | 8.0 kn\n"
    )
