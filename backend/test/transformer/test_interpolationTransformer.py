from datetime import datetime, timezone

import numpy as np
import pytest

from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    ProvenanceRecord,
    SessionMetadata,
)
from src.transformer.interpolationTransformer import InterpolationTransformer


def make_session(
    *,
    lat_timestamps: np.ndarray | None = None,
    lat_values: np.ndarray | None = None,
    lon_timestamps: np.ndarray | None = None,
    lon_values: np.ndarray | None = None,
    extra_channels: dict[str, Channel] | None = None,
) -> CanonicalSession:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-interpolation"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=(
                    lat_timestamps
                    if lat_timestamps is not None
                    else np.array([0.0, 3.0, 10.0], dtype=float)
                ),
                values=(
                    lat_values
                    if lat_values is not None
                    else np.array([57.0, 60.0, 67.0], dtype=float)
                ),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=(
                    lon_timestamps
                    if lon_timestamps is not None
                    else np.array([0.0, 3.0, 10.0], dtype=float)
                ),
                values=(
                    lon_values
                    if lon_values is not None
                    else np.array([11.0, 14.0, 21.0], dtype=float)
                ),
                unit="deg",
                source="gps",
            ),
        },
    )

    for channel in (extra_channels or {}).values():
        session.add_channel(channel)

    return session


def test_transform_interpolates_all_channels_within_max_gap() -> None:
    heel_channel = Channel(
        name="heel",
        timestamps=np.array([0.0, 2.0], dtype=float),
        values=np.array([10.0, 14.0], dtype=float),
        unit="deg",
        source="imu",
    )
    session = make_session(extra_channels={"heel": heel_channel})

    transformer = InterpolationTransformer(max_gap_seconds=4.0, frequency_hz=1.0)
    result = transformer.transform(session)

    np.testing.assert_allclose(
        result.get_channel("lat").timestamps,
        np.array([0.0, 1.0, 2.0, 3.0, 10.0]),
    )
    np.testing.assert_allclose(
        result.get_channel("lat").values,
        np.array([57.0, 58.0, 59.0, 60.0, 67.0]),
    )
    np.testing.assert_allclose(
        result.get_channel("lon").timestamps,
        np.array([0.0, 1.0, 2.0, 3.0, 10.0]),
    )
    np.testing.assert_allclose(
        result.get_channel("lon").values,
        np.array([11.0, 12.0, 13.0, 14.0, 21.0]),
    )
    np.testing.assert_allclose(
        result.get_channel("heel").timestamps,
        np.array([0.0, 1.0, 2.0]),
    )
    np.testing.assert_allclose(
        result.get_channel("heel").values,
        np.array([10.0, 12.0, 14.0]),
    )

    records = {record.produced_name: record for record in result.provenance}
    assert records["lat"].changes[0]["operation"] == "interpolate"
    assert records["lat"].changes[0]["inserted_samples"] == 2
    assert records["lat"].changes[0]["interpolated_gaps"] == 1
    assert records["lat"].changes[0]["skipped_gaps"] == 1
    assert records["lat"].changes[0]["quality_percent"] == pytest.approx(30.0)
    assert records["heel"].changes[0]["inserted_samples"] == 1

    summary = transformer.summary
    assert summary.total_inserted_samples == 5
    assert summary.session_quality_percent == pytest.approx(100.0 * 8.0 / 22.0)
    assert summary.channel_quality_percent == {
        "lat": pytest.approx(30.0),
        "lon": pytest.approx(30.0),
        "heel": pytest.approx(100.0),
    }


def test_transform_does_not_interpolate_gaps_larger_than_max_gap() -> None:
    session = make_session()

    transformer = InterpolationTransformer(max_gap_seconds=2.5, frequency_hz=1.0)
    result = transformer.transform(session)

    np.testing.assert_allclose(result.get_channel("lat").timestamps, [0.0, 3.0, 10.0])
    np.testing.assert_allclose(result.get_channel("lat").values, [57.0, 60.0, 67.0])

    lat_record = next(record for record in result.provenance if record.produced_name == "lat")
    assert lat_record.changes[0]["operation"] == "noop"
    assert lat_record.changes[0]["inserted_samples"] == 0
    assert lat_record.changes[0]["interpolated_gaps"] == 0
    assert lat_record.changes[0]["skipped_gaps"] == 2


def test_transform_supports_multidimensional_channel_values() -> None:
    wind_channel = Channel(
        name="wind_vector",
        timestamps=np.array([0.0, 2.0], dtype=float),
        values=np.array([[0.0, 10.0], [2.0, 14.0]], dtype=float),
        unit="mixed",
        source="derived",
    )
    session = make_session(extra_channels={"wind_vector": wind_channel})

    transformer = InterpolationTransformer(max_gap_seconds=3.0, frequency_hz=1.0)
    result = transformer.transform(session)

    np.testing.assert_allclose(
        result.get_channel("wind_vector").timestamps,
        np.array([0.0, 1.0, 2.0]),
    )
    np.testing.assert_allclose(
        result.get_channel("wind_vector").values,
        np.array([[0.0, 10.0], [1.0, 12.0], [2.0, 14.0]]),
    )


def test_transform_supports_datetime64_timestamps() -> None:
    session = make_session(
        lat_timestamps=np.array(
            ["2025-09-06T08:30:00.000", "2025-09-06T08:30:02.000"],
            dtype="datetime64[ms]",
        ),
        lat_values=np.array([57.0, 59.0], dtype=float),
        lon_timestamps=np.array(
            ["2025-09-06T08:30:00.000", "2025-09-06T08:30:02.000"],
            dtype="datetime64[ms]",
        ),
        lon_values=np.array([11.0, 13.0], dtype=float),
    )

    transformer = InterpolationTransformer(max_gap_seconds=3.0, frequency_hz=1.0)
    result = transformer.transform(session)

    np.testing.assert_array_equal(
        result.get_channel("lat").timestamps,
        np.array(
            [
                "2025-09-06T08:30:00.000",
                "2025-09-06T08:30:01.000",
                "2025-09-06T08:30:02.000",
            ],
            dtype="datetime64[ns]",
        ),
    )
    np.testing.assert_allclose(result.get_channel("lat").values, [57.0, 58.0, 59.0])


def test_transform_supports_python_datetime_timestamps() -> None:
    timestamps = np.array(
        [
            datetime(2025, 9, 6, 8, 30, 0, tzinfo=timezone.utc),
            datetime(2025, 9, 6, 8, 30, 2, tzinfo=timezone.utc),
        ],
        dtype=object,
    )
    session = make_session(
        lat_timestamps=timestamps.copy(),
        lat_values=np.array([57.0, 59.0], dtype=float),
        lon_timestamps=timestamps.copy(),
        lon_values=np.array([11.0, 13.0], dtype=float),
    )

    transformer = InterpolationTransformer(max_gap_seconds=3.0, frequency_hz=1.0)
    result = transformer.transform(session)

    np.testing.assert_array_equal(
        result.get_channel("lat").timestamps,
        np.array(
            [
                datetime(2025, 9, 6, 8, 30, 0, tzinfo=timezone.utc),
                datetime(2025, 9, 6, 8, 30, 1, tzinfo=timezone.utc),
                datetime(2025, 9, 6, 8, 30, 2, tzinfo=timezone.utc),
            ],
            dtype=object,
        ),
    )
    np.testing.assert_allclose(result.get_channel("lat").values, [57.0, 58.0, 59.0])


def test_transform_keeps_empty_and_single_sample_channels_unchanged() -> None:
    empty_channel = Channel(
        name="awa",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="sensor",
    )
    single_sample_channel = Channel(
        name="aws",
        timestamps=np.array([5.0], dtype=float),
        values=np.array([12.0], dtype=float),
        unit="kn",
        source="sensor",
    )
    session = make_session(
        lat_timestamps=np.array([0.0], dtype=float),
        lat_values=np.array([57.0], dtype=float),
        lon_timestamps=np.array([0.0], dtype=float),
        lon_values=np.array([11.0], dtype=float),
        extra_channels={"awa": empty_channel, "aws": single_sample_channel},
    )

    transformer = InterpolationTransformer(max_gap_seconds=3.0, frequency_hz=2.0)
    result = transformer.transform(session)

    np.testing.assert_array_equal(result.get_channel("awa").timestamps, np.array([], dtype=float))
    np.testing.assert_array_equal(result.get_channel("awa").values, np.array([], dtype=float))
    np.testing.assert_array_equal(result.get_channel("aws").timestamps, np.array([5.0]))
    np.testing.assert_array_equal(result.get_channel("aws").values, np.array([12.0]))

    records = {record.produced_name: record for record in result.provenance}
    assert records["awa"].changes[0]["operation"] == "noop"
    assert records["aws"].changes[0]["operation"] == "noop"


def test_quality_ignores_time_removed_by_exclusion_zones() -> None:
    session = make_session(
        lat_timestamps=np.array([0.0, 1.0, 4.0, 5.0], dtype=float),
        lat_values=np.array([57.0, 58.0, 61.0, 62.0], dtype=float),
        lon_timestamps=np.array([0.0, 1.0, 4.0, 5.0], dtype=float),
        lon_values=np.array([11.0, 12.0, 15.0, 16.0], dtype=float),
    )
    session.provenance.append(
        ProvenanceRecord(
            producer="HarbourExclusionTransformer",
            produced_type="channel",
            produced_name="lat",
            action="modified",
            config={
                "excluded_spans_ns": [
                    {
                        "start_ns": 2_000_000_000,
                        "end_ns": 3_000_000_000,
                    }
                ]
            },
            changes=[
                {
                    "field": "values",
                    "operation": "remove_by_time_span",
                    "count": 2,
                }
            ],
        )
    )

    transformer = InterpolationTransformer(max_gap_seconds=5.0, frequency_hz=1.0)
    result = transformer.transform(session)

    np.testing.assert_allclose(
        result.get_channel("lat").timestamps,
        np.array([0.0, 1.0, 4.0, 5.0]),
    )

    records = {record.produced_name: record for record in result.provenance}
    assert records["lat"].changes[0]["quality_percent"] == pytest.approx(100.0)

    summary = transformer.summary
    assert summary.session_quality_percent == pytest.approx(100.0)
    assert summary.channel_quality_percent == {
        "lat": pytest.approx(100.0),
        "lon": pytest.approx(100.0),
    }


def test_transform_rejects_non_increasing_timestamps() -> None:
    session = make_session(
        extra_channels={
            "heel": Channel(
                name="heel",
                timestamps=np.array([0.0, 1.0, 1.0], dtype=float),
                values=np.array([1.0, 2.0, 3.0], dtype=float),
                unit="deg",
                source="imu",
            )
        }
    )

    transformer = InterpolationTransformer(max_gap_seconds=5.0, frequency_hz=1.0)

    with pytest.raises(
        ValueError,
        match="Channel 'heel' timestamps must be strictly increasing for interpolation",
    ):
        transformer.transform(session)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_gap_seconds": 0.0, "frequency_hz": 1.0}, "max_gap_seconds must be greater than 0"),
        ({"max_gap_seconds": 2.0, "frequency_hz": 0.0}, "frequency_hz must be greater than 0"),
    ],
)
def test_init_rejects_non_positive_configuration(
    kwargs: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        InterpolationTransformer(**kwargs)


def test_print_summary_reports_session_and_channel_quality(
    capsys: pytest.CaptureFixture[str],
) -> None:
    heart_rate_channel = Channel(
        name="heart_rate",
        timestamps=np.array([0.0, 2.0], dtype=float),
        values=np.array([120.0, 130.0], dtype=float),
        unit="bpm",
        source="watch",
    )
    session = make_session(
        lat_timestamps=np.array([0.0, 2.0], dtype=float),
        lat_values=np.array([57.0, 59.0], dtype=float),
        lon_timestamps=np.array([0.0, 2.0], dtype=float),
        lon_values=np.array([11.0, 13.0], dtype=float),
        extra_channels={"heart_rate": heart_rate_channel},
    )

    transformer = InterpolationTransformer(max_gap_seconds=3.0, frequency_hz=1.0)
    transformer.transform(session)

    transformer.print_summary()

    captured = capsys.readouterr()
    assert (
        captured.out
        == "interpolation: inserted 3 points, session quality at 1 Hz: 100.0%\n"
        "interpolation channel quality: lat=100.0%, lon=100.0%, heart_rate=100.0%\n"
    )
