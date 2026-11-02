import numpy as np
import pytest
from src.analyzer.windAngleAnlayzer import TWAAnalyzer
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
    cog_values: np.ndarray,
    wind_direction_values: np.ndarray | None = None,
    wind_direction_timestamps: np.ndarray | None = None,
    manual_wind_direction: float | None = None,
    include_existing_twa: bool = False,
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
        ChannelNames.COG.value: Channel(
            name=ChannelNames.COG.value,
            timestamps=timestamps.copy(),
            values=np.asarray(cog_values, dtype=float),
            unit="deg",
            source="COGAnalyzer",
        ),
    }

    if wind_direction_values is not None:
        channels[ChannelNames.TWD_EXTERNAL.value] = Channel(
            name=ChannelNames.TWD_EXTERNAL.value,
            timestamps=(
                wind_direction_timestamps.copy()
                if wind_direction_timestamps is not None
                else timestamps.copy()
            ),
            values=np.asarray(wind_direction_values, dtype=float),
            unit="deg",
            source="WeatherAnalyzer",
        )

    if include_existing_twa:
        channels[ChannelNames.TWA.value] = Channel(
            name=ChannelNames.TWA.value,
            timestamps=timestamps.copy(),
            values=np.asarray([1.0] * len(timestamps), dtype=float),
            unit="deg",
            source="sailmon_csv",
        )

    metrics = {}
    if manual_wind_direction is not None:
        metrics[MetricNames.MANUAL_WIND_DIRECTION.value] = Metric(
            name=MetricNames.MANUAL_WIND_DIRECTION.value,
            value=manual_wind_direction,
            unit="deg",
            source=MetricNames.MANUAL_WIND_SOURCE.value,
        )

    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-twa"),
        channels=channels,
        metrics=metrics,
    )


def test_analyze_prefers_manual_wind_direction_when_available() -> None:
    timestamps = np.array([0.0, 10.0, 20.0], dtype=float)
    session = _build_session(
        timestamps=timestamps,
        cog_values=np.array([0.0, 0.0, 0.0], dtype=float),
        wind_direction_timestamps=np.array([0.0, 20.0], dtype=float),
        wind_direction_values=np.array([350.0, 10.0], dtype=float),
        manual_wind_direction=90.0,
    )

    result = TWAAnalyzer().analyze(session)

    twa_channel = result.get_channel(ChannelNames.TWA.value)
    np.testing.assert_allclose(twa_channel.values, np.array([90.0, 90.0, 90.0]))
    assert (
        twa_channel.metadata["wind_direction_reference"]
        == MetricNames.MANUAL_WIND_DIRECTION.value
    )
    assert twa_channel.metadata["wind_direction_reference_type"] == "metric"
    assert (
        twa_channel.metadata["wind_direction_alignment"] == "constant_manual_direction"
    )
    assert len(result.provenance) == 1
    assert result.provenance[0].inputs == [
        ChannelNames.COG.value,
        MetricNames.MANUAL_WIND_DIRECTION.value,
    ]


def test_analyze_uses_external_wind_direction_with_circular_interpolation() -> None:
    timestamps = np.array([0.0, 10.0, 20.0], dtype=float)
    session = _build_session(
        timestamps=timestamps,
        cog_values=np.array([0.0, 0.0, 0.0], dtype=float),
        wind_direction_timestamps=np.array([0.0, 20.0], dtype=float),
        wind_direction_values=np.array([350.0, 10.0], dtype=float),
    )

    result = TWAAnalyzer().analyze(session)

    twa_channel = result.get_channel(ChannelNames.TWA.value)
    np.testing.assert_allclose(twa_channel.values, np.array([-10.0, 0.0, 10.0]))
    assert (
        twa_channel.metadata["wind_direction_reference"]
        == ChannelNames.TWD_EXTERNAL.value
    )
    assert twa_channel.metadata["wind_direction_reference_type"] == "channel"
    assert (
        twa_channel.metadata["wind_direction_alignment"]
        == "circular_interpolation_to_cog_timestamps"
    )
    assert len(result.provenance) == 1
    assert result.provenance[0].inputs == [
        ChannelNames.COG.value,
        ChannelNames.TWD_EXTERNAL.value,
    ]


def test_analyze_falls_back_to_manual_wind_direction_when_external_is_unusable() -> (
    None
):
    timestamps = np.array([0.0, 10.0, 20.0], dtype=float)
    session = _build_session(
        timestamps=timestamps,
        cog_values=np.array([10.0, 20.0, 30.0], dtype=float),
        wind_direction_timestamps=np.array([], dtype=float),
        wind_direction_values=np.array([], dtype=float),
        manual_wind_direction=40.0,
    )

    result = TWAAnalyzer().analyze(session)

    twa_channel = result.get_channel(ChannelNames.TWA.value)
    np.testing.assert_allclose(twa_channel.values, np.array([30.0, 20.0, 10.0]))
    assert (
        twa_channel.metadata["wind_direction_reference"]
        == MetricNames.MANUAL_WIND_DIRECTION.value
    )
    assert twa_channel.metadata["wind_direction_reference_type"] == "metric"
    assert (
        twa_channel.metadata["wind_direction_alignment"] == "constant_manual_direction"
    )


def test_analyze_appends_manual_wind_reference_name_when_twa_already_exists() -> None:
    timestamps = np.array([0.0, 10.0, 20.0], dtype=float)
    session = _build_session(
        timestamps=timestamps,
        cog_values=np.array([0.0, 0.0, 0.0], dtype=float),
        manual_wind_direction=15.0,
        include_existing_twa=True,
    )

    result = TWAAnalyzer().analyze(session)

    assert result.get_channel(ChannelNames.TWA.value).source == "sailmon_csv"
    assert result.has_channel("twa_manual_wind_direction_deg")
    np.testing.assert_allclose(
        result.get_channel("twa_manual_wind_direction_deg").values,
        np.array([15.0, 15.0, 15.0]),
    )
    assert result.provenance[0].produced_name == "twa_manual_wind_direction_deg"


def test_analyze_is_noop_when_no_wind_direction_reference_exists() -> None:
    timestamps = np.array([0.0, 10.0, 20.0], dtype=float)
    session = _build_session(
        timestamps=timestamps,
        cog_values=np.array([0.0, 5.0, 10.0], dtype=float),
    )

    result = TWAAnalyzer().analyze(session)

    assert result is session
    assert set(result.channels.keys()) == {
        ChannelNames.LATITUDE.value,
        ChannelNames.LONGITUDE.value,
        ChannelNames.COG.value,
    }
    assert result.provenance == []


def test_print_summary_reports_wind_dir_channel_reference(
    capsys: pytest.CaptureFixture[str],
) -> None:
    timestamps = np.array([0.0, 10.0, 20.0], dtype=float)
    session = _build_session(
        timestamps=timestamps,
        cog_values=np.array([0.0, 0.0, 0.0], dtype=float),
        wind_direction_values=np.array([15.0, 15.0, 15.0], dtype=float),
    )
    analyzer = TWAAnalyzer()

    analyzer.analyze(session)
    analyzer.print_summary()

    assert capsys.readouterr().out == "twa: twa from wind dir channel (twa)\n"


def test_print_summary_reports_manual_wind_entry_reference(
    capsys: pytest.CaptureFixture[str],
) -> None:
    timestamps = np.array([0.0, 10.0, 20.0], dtype=float)
    session = _build_session(
        timestamps=timestamps,
        cog_values=np.array([10.0, 20.0, 30.0], dtype=float),
        manual_wind_direction=40.0,
    )
    analyzer = TWAAnalyzer()

    analyzer.analyze(session)
    analyzer.print_summary()

    assert capsys.readouterr().out == "twa: twa from manual wind entry (twa)\n"
