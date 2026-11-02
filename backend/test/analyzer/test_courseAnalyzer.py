import numpy as np
import pytest

from src.analyzer.courseAnalyzer import COGAnalyzer, TurnRateAnalyzer
from src.constants.ChannelNames import ChannelNames
from src.models.canonicalSession import (CanonicalSession, Channel,
                                         SessionMetadata)


@pytest.fixture
def session() -> CanonicalSession:
    timestamps = np.array(
        [
            "2026-05-01T10:00:00",
            "2026-05-01T10:00:01",
            "2026-05-01T10:00:02",
        ],
        dtype="datetime64[s]",
    )

    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-course"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=timestamps.copy(),
                values=np.array([0.0, 0.0, 1.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=timestamps.copy(),
                values=np.array([0.0, 1.0, 1.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=timestamps.copy(),
                values=np.array([4.0, 4.0, 4.0], dtype=float),
                unit="kn",
                source="gps",
            ),
        },
    )


def test_analyze_adds_cog_channel_and_provenance(session: CanonicalSession) -> None:
    analyzer = COGAnalyzer()

    result = analyzer.analyze(session)

    assert result is session
    assert result.has_channel(ChannelNames.COG.value)

    cog_channel = result.get_channel(ChannelNames.COG.value)
    assert cog_channel.unit == "deg"
    assert cog_channel.source == "COGAnalyzer"
    assert cog_channel.is_derived is True
    assert cog_channel.metadata == {
        "channels": [
            ChannelNames.LATITUDE.value,
            ChannelNames.LONGITUDE.value,
        ],
        "method": "initial_bearing_previous_sample",
    }
    assert np.array_equal(
        cog_channel.timestamps,
        result.get_channel(ChannelNames.LATITUDE.value).timestamps,
    )
    assert np.isnan(cog_channel.values[0])
    assert cog_channel.values[1] == pytest.approx(90.0)
    assert cog_channel.values[2] == pytest.approx(0.0)

    assert len(result.provenance) == 1
    record = result.provenance[0]
    assert record.producer == "COGAnalyzer"
    assert record.produced_type == "channel"
    assert record.produced_name == ChannelNames.COG.value
    assert record.inputs == [
        ChannelNames.LATITUDE.value,
        ChannelNames.LONGITUDE.value,
    ]
    assert record.config == {
        "method": "initial_bearing_previous_sample",
        "channels": [
            ChannelNames.LATITUDE.value,
            ChannelNames.LONGITUDE.value,
        ],
        "unit": "deg",
    }
    assert record.changes == [
        {
            "field": "values",
            "operation": "calculate_course_over_ground",
            "description": "Computed course over ground from consecutive lat/lon samples",
        }
    ]


def test_cog_returns_empty_channel_for_empty_track() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-empty-course"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([], dtype="datetime64[ms]"),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([], dtype="datetime64[ms]"),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    result = COGAnalyzer().analyze(session)

    cog_channel = result.get_channel(ChannelNames.COG.value)
    assert cog_channel.values.shape == (0,)
    assert cog_channel.timestamps.shape == (0,)


def test_analyze_requires_identical_lat_lon_timestamps() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-course-mismatch"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=np.array([0.0, 1.0], dtype=float),
                values=np.array([57.0, 57.1], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=np.array([0.0, 2.0], dtype=float),
                values=np.array([11.0, 11.1], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    with pytest.raises(
        ValueError,
        match=(
            f"COGAnalyzer requires '{ChannelNames.LATITUDE.value}' and "
            f"'{ChannelNames.LONGITUDE.value}' to share identical timestamps"
        ),
    ):
        COGAnalyzer().analyze(session)


def test_print_summary_outputs_average_course(
    session: CanonicalSession, capsys: pytest.CaptureFixture[str]
) -> None:
    analyzer = COGAnalyzer()

    analyzer.analyze(session)
    analyzer.print_summary()

    assert capsys.readouterr().out == "average_course: 45.0 deg\n"


def test_analyze_renames_cog_channel_when_raw_cog_already_exists() -> None:
    timestamps = np.array(
        [
            "2026-05-01T10:00:00",
            "2026-05-01T10:00:01",
            "2026-05-01T10:00:02",
        ],
        dtype="datetime64[s]",
    )
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-course-existing-cog"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=timestamps.copy(),
                values=np.array([0.0, 0.0, 1.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=timestamps.copy(),
                values=np.array([0.0, 1.0, 1.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.COG.value: Channel(
                name=ChannelNames.COG.value,
                timestamps=timestamps.copy(),
                values=np.array([10.0, 20.0, 30.0], dtype=float),
                unit="deg",
                source="sailmon_csv",
            ),
        },
    )

    result = COGAnalyzer().analyze(session)

    assert result.has_channel(ChannelNames.COG.value)
    assert result.has_channel(f"{ChannelNames.COG.value}_cogAnalyzer")
    assert result.get_channel(ChannelNames.COG.value).source == "sailmon_csv"
    assert (
        result.get_channel(f"{ChannelNames.COG.value}_cogAnalyzer").source
        == "COGAnalyzer"
    )
    assert (
        result.provenance[0].produced_name == f"{ChannelNames.COG.value}_cogAnalyzer"
    )
    assert (
        result.provenance[0].produced_name == f"{ChannelNames.COG.value}_cogAnalyzer"
    )


def test_turn_rate_analyze_adds_channel_and_provenance() -> None:
    timestamps = np.array(
        [
            "2026-05-01T10:00:00",
            "2026-05-01T10:00:01",
            "2026-05-01T10:00:03",
            "2026-05-01T10:00:04",
            "2026-05-01T10:00:07",
            "2026-05-01T10:00:08",
        ],
        dtype="datetime64[s]",
    )
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-turn-rate"),
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
            ChannelNames.COG.value: Channel(
                name=ChannelNames.COG.value,
                timestamps=timestamps.copy(),
                values=np.array([350.0, 355.0, 359.0, 2.0, 6.0, 1.0], dtype=float),
                unit="deg",
                source="COGAnalyzer",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=timestamps.copy(),
                values=np.array([3.0, 3.0, 3.0, 3.0, 3.0, 3.0], dtype=float),
                unit="kn",
                source="gps",
            ),
        },
    )

    result = TurnRateAnalyzer().analyze(session)

    assert result.has_channel(ChannelNames.TURN_RATE.value)
    turn_rate_channel = result.get_channel(ChannelNames.TURN_RATE.value)
    assert turn_rate_channel.unit == "deg/s"
    assert turn_rate_channel.source == "TurnRateAnalyzer"
    assert turn_rate_channel.is_derived is True
    assert turn_rate_channel.metadata == {
        "channels": [
            ChannelNames.COG.value,
            ChannelNames.SOG.value,
        ],
        "method": "signed_circular_difference_over_elapsed_seconds",
        "time_delta_source": "channel_timestamps",
        "min_speed_kn": 1.0,
        "speed_alignment": "linear_interpolation_to_cog_timestamps",
    }
    np.testing.assert_allclose(
        turn_rate_channel.values,
        np.array([np.nan, 5.0, 2.0, 3.0, 4.0 / 3.0, -5.0]),
        equal_nan=True,
    )

    assert len(result.provenance) == 1
    record = result.provenance[0]
    assert record.producer == "TurnRateAnalyzer"
    assert record.produced_type == "channel"
    assert record.produced_name == ChannelNames.TURN_RATE.value
    assert record.inputs == [ChannelNames.COG.value, ChannelNames.SOG.value]
    assert record.config == {
        "channels": [
            ChannelNames.COG.value,
            ChannelNames.SOG.value,
        ],
        "method": "signed_circular_difference_over_elapsed_seconds",
        "time_delta_source": "channel_timestamps",
        "min_speed_kn": 1.0,
        "speed_alignment": "linear_interpolation_to_cog_timestamps",
        "unit": "deg/s",
    }
    assert record.changes == [
        {
            "field": "values",
            "operation": "calculate_turn_rate_from_course_over_ground",
            "description": "Computed signed turn rate from consecutive COG samples and elapsed time",
        }
    ]


def test_turn_rate_init_rejects_negative_min_speed_knots() -> None:
    with pytest.raises(
        ValueError, match="min_speed_knots must be greater than or equal to 0"
    ):
        TurnRateAnalyzer(min_speed_knots=-0.1)


def test_turn_rate_returns_nan_for_invalid_samples_non_positive_time_delta_or_low_speed() -> None:
    timestamps = np.array([0.0, 1.0, 1.0, 3.0], dtype=float)
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-turn-rate-invalid"),
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
            ChannelNames.COG.value: Channel(
                name=ChannelNames.COG.value,
                timestamps=timestamps.copy(),
                values=np.array([10.0, np.nan, 20.0, 30.0], dtype=float),
                unit="deg",
                source="COGAnalyzer",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=timestamps.copy(),
                values=np.array([2.0, 0.5, 2.0, 2.0], dtype=float),
                unit="kn",
                source="gps",
            ),
        },
    )

    result = TurnRateAnalyzer().analyze(session)

    np.testing.assert_allclose(
        result.get_channel(ChannelNames.TURN_RATE.value).values,
        np.array([np.nan, np.nan, np.nan, 5.0]),
        equal_nan=True,
    )


def test_turn_rate_skips_segments_when_either_speed_sample_is_at_or_below_one_knot() -> None:
    timestamps = np.array([0.0, 1.0, 2.0, 3.0], dtype=float)
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-turn-rate-low-speed"),
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
            ChannelNames.COG.value: Channel(
                name=ChannelNames.COG.value,
                timestamps=timestamps.copy(),
                values=np.array([10.0, 20.0, 35.0, 50.0], dtype=float),
                unit="deg",
                source="COGAnalyzer",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=timestamps.copy(),
                values=np.array([1.0, 1.2, 1.5, 0.8], dtype=float),
                unit="kn",
                source="gps",
            ),
        },
    )

    result = TurnRateAnalyzer().analyze(session)

    np.testing.assert_allclose(
        result.get_channel(ChannelNames.TURN_RATE.value).values,
        np.array([np.nan, np.nan, 15.0, np.nan]),
        equal_nan=True,
    )


def test_turn_rate_uses_configured_min_speed_threshold() -> None:
    timestamps = np.array([0.0, 1.0, 2.0], dtype=float)
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-turn-rate-custom-threshold"),
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
            ChannelNames.COG.value: Channel(
                name=ChannelNames.COG.value,
                timestamps=timestamps.copy(),
                values=np.array([10.0, 25.0, 45.0], dtype=float),
                unit="deg",
                source="COGAnalyzer",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=timestamps.copy(),
                values=np.array([1.6, 1.7, 2.1], dtype=float),
                unit="kn",
                source="gps",
            ),
        },
    )

    result = TurnRateAnalyzer(min_speed_knots=1.8).analyze(session)

    turn_rate_channel = result.get_channel(ChannelNames.TURN_RATE.value)
    np.testing.assert_allclose(
        turn_rate_channel.values,
        np.array([np.nan, np.nan, np.nan]),
        equal_nan=True,
    )
    assert turn_rate_channel.metadata["min_speed_kn"] == 1.8


def test_turn_rate_aligns_speed_values_to_cog_timestamps_when_lengths_differ() -> None:
    cog_timestamps = np.array([0.0, 1.0, 2.0, 3.0], dtype=float)
    speed_timestamps = np.array([0.0, 1.0, 3.0], dtype=float)
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-turn-rate-speed-alignment"),
        channels={
            ChannelNames.LATITUDE.value: Channel(
                name=ChannelNames.LATITUDE.value,
                timestamps=cog_timestamps.copy(),
                values=np.zeros(len(cog_timestamps), dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.LONGITUDE.value: Channel(
                name=ChannelNames.LONGITUDE.value,
                timestamps=cog_timestamps.copy(),
                values=np.zeros(len(cog_timestamps), dtype=float),
                unit="deg",
                source="gps",
            ),
            ChannelNames.COG.value: Channel(
                name=ChannelNames.COG.value,
                timestamps=cog_timestamps.copy(),
                values=np.array([10.0, 20.0, 35.0, 50.0], dtype=float),
                unit="deg",
                source="COGAnalyzer",
            ),
            ChannelNames.SOG.value: Channel(
                name=ChannelNames.SOG.value,
                timestamps=speed_timestamps.copy(),
                values=np.array([2.0, 2.0, 2.0], dtype=float),
                unit="kn",
                source="gps",
            ),
        },
    )

    result = TurnRateAnalyzer().analyze(session)

    np.testing.assert_allclose(
        result.get_channel(ChannelNames.TURN_RATE.value).values,
        np.array([np.nan, 10.0, 15.0, 15.0]),
        equal_nan=True,
    )
