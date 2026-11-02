from datetime import datetime, timezone

import numpy as np
import pytest

from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.transformer.exclusionZones.exclusionZone import ExclusionZoneTransformer
from src.transformer.exclusionZones.sweden import LangedragExclusion


class HarbourExclusionTransformer(ExclusionZoneTransformer):
    @property
    def zone_name(self) -> str:
        return "harbour"

    @property
    def polygon_coordinates(self) -> list[tuple[float, float]]:
        return [
            (10.0, 10.0),
            (10.0, 12.0),
            (12.0, 12.0),
            (12.0, 10.0),
        ]


class InvalidPolygonTransformer(ExclusionZoneTransformer):
    @property
    def zone_name(self) -> str:
        return "invalid"

    @property
    def polygon_coordinates(self) -> list[tuple[float, float]]:
        return [(10.0, 10.0), (11.0, 11.0)]


class ClosedSquareExclusionTransformer(ExclusionZoneTransformer):
    @property
    def zone_name(self) -> str:
        return "closed-square"

    @property
    def polygon_coordinates(self) -> list[tuple[float, float]]:
        return [
            (10.0, 10.0),
            (10.0, 12.0),
            (12.0, 12.0),
            (12.0, 10.0),
            (10.0, 10.0),
        ]


def test_transform_removes_values_for_all_channels_by_excluded_timespans() -> None:
    lat_timestamps = np.array([0, 1, 2, 3, 4, 5], dtype=float)
    lon_timestamps = np.array([0, 1, 2, 3, 4, 5], dtype=float)
    heel_timestamps = np.arange(0.0, 5.0 + 0.1, 0.1, dtype=float)
    boat_speed_timestamps = np.array([0.5, 1.5, 2.5, 3.5, 4.5], dtype=float)

    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-exclusion"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=lat_timestamps.copy(),
                values=np.array([0.0, 0.0, 11.0, 11.0, 0.0, 0.0]),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=lon_timestamps.copy(),
                values=np.array([0.0, 0.0, 11.0, 11.0, 0.0, 0.0]),
                unit="deg",
                source="gps",
            ),
            "heel": Channel(
                name="heel",
                timestamps=heel_timestamps.copy(),
                values=np.arange(heel_timestamps.size, dtype=float),
                unit="deg",
                source="imu",
            ),
            "boat_speed": Channel(
                name="boat_speed",
                timestamps=boat_speed_timestamps.copy(),
                values=np.array([4.2, 4.4, 4.6, 4.8, 5.0], dtype=float),
                unit="kn",
                source="gps",
            ),
        },
    )

    transformer = HarbourExclusionTransformer()
    result = transformer.transform(session)

    np.testing.assert_array_equal(result.get_channel("lat").timestamps, [0.0, 1.0, 4.0, 5.0])
    np.testing.assert_array_equal(result.get_channel("lon").timestamps, [0.0, 1.0, 4.0, 5.0])

    heel_after = result.get_channel("heel").timestamps
    assert not np.any((heel_after >= 2.0) & (heel_after <= 3.0))
    assert heel_after.size == heel_timestamps.size - 11

    np.testing.assert_array_equal(
        result.get_channel("boat_speed").timestamps, [0.5, 1.5, 3.5, 4.5]
    )

    records_by_channel = {record.produced_name: record for record in result.provenance}
    assert set(records_by_channel.keys()) == {"lat", "lon", "heel", "boat_speed"}

    heel_record = records_by_channel["heel"]
    assert heel_record.changes[0]["operation"] == "remove_by_time_span"
    assert heel_record.changes[0]["count"] == 11
    assert heel_record.config["zone_name"] == "harbour"
    assert len(heel_record.config["excluded_spans_ns"]) == 1


def test_transform_is_noop_when_session_never_enters_zone() -> None:
    lat_channel = Channel(
        name="lat",
        timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
        values=np.array([0.0, 1.0, 2.0], dtype=float),
        unit="deg",
        source="gps",
    )
    lon_channel = Channel(
        name="lon",
        timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
        values=np.array([0.0, 1.0, 2.0], dtype=float),
        unit="deg",
        source="gps",
    )
    heel_channel = Channel(
        name="heel",
        timestamps=np.array([0.0, 0.5, 1.0, 1.5, 2.0], dtype=float),
        values=np.array([5.0, 6.0, 7.0, 8.0, 9.0], dtype=float),
        unit="deg",
        source="imu",
    )
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-noop"),
        channels={"lat": lat_channel, "lon": lon_channel, "heel": heel_channel},
    )

    lat_before = lat_channel.timestamps.copy()
    lon_before = lon_channel.timestamps.copy()
    heel_before = heel_channel.timestamps.copy()

    transformer = HarbourExclusionTransformer()
    result = transformer.transform(session)

    np.testing.assert_array_equal(result.get_channel("lat").timestamps, lat_before)
    np.testing.assert_array_equal(result.get_channel("lon").timestamps, lon_before)
    np.testing.assert_array_equal(result.get_channel("heel").timestamps, heel_before)

    for record in result.provenance:
        assert record.changes[0]["operation"] == "noop"
        assert record.changes[0]["count"] == 0


def test_transform_supports_object_datetime_timestamps() -> None:
    timestamps = np.array(
        [
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 10, 2, tzinfo=timezone.utc),
        ],
        dtype=object,
    )
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-object-datetime"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=timestamps.copy(),
                values=np.array([0.0, 11.0, 0.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=timestamps.copy(),
                values=np.array([0.0, 11.0, 0.0], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    transformer = HarbourExclusionTransformer()
    result = transformer.transform(session)

    np.testing.assert_array_equal(
        result.get_channel("lat").timestamps,
        np.array([timestamps[0], timestamps[2]], dtype=object),
    )
    np.testing.assert_array_equal(
        result.get_channel("lon").timestamps,
        np.array([timestamps[0], timestamps[2]], dtype=object),
    )


def test_transform_rejects_polygon_with_less_than_three_points() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-invalid-polygon"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([0.0], dtype=float),
                values=np.array([0.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([0.0], dtype=float),
                values=np.array([0.0], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    transformer = InvalidPolygonTransformer()

    with pytest.raises(
        ValueError, match="polygon_coordinates must contain at least 3 points"
    ):
        transformer.transform(session)


def test_transform_requires_identical_lat_lon_timestamps() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-mismatch"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([0.0, 1.0], dtype=float),
                values=np.array([0.0, 11.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([0.0, 2.0], dtype=float),
                values=np.array([0.0, 11.0], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    transformer = HarbourExclusionTransformer()

    with pytest.raises(
        ValueError,
        match="lat and lon channels must share identical timestamps for zone exclusion",
    ):
        transformer.transform(session)


def test_langedrag_exclusion_exposes_zone_name_and_lat_lon_polygon() -> None:
    transformer = LangedragExclusion()

    assert transformer.zone_name == "langedrag"
    assert transformer.polygon_coordinates[0] == (
        57.66912353121583,
        11.84590693977313,
    )


def test_closed_polygon_does_not_mark_all_points_inside() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-closed-polygon"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
                values=np.array([20.0, 21.0, 22.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
                values=np.array([20.0, 21.0, 22.0], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )

    transformer = ClosedSquareExclusionTransformer()
    result = transformer.transform(session)

    np.testing.assert_array_equal(result.get_channel("lat").timestamps, [0.0, 1.0, 2.0])
    np.testing.assert_array_equal(result.get_channel("lon").timestamps, [0.0, 1.0, 2.0])
    assert all(record.changes[0]["operation"] == "noop" for record in result.provenance)


def test_print_summary_reports_removed_samples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-summary"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
                values=np.array([0.0, 11.0, 0.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
                values=np.array([0.0, 11.0, 0.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            "heel": Channel(
                name="heel",
                timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
                values=np.array([1.0, 2.0, 3.0], dtype=float),
                unit="deg",
                source="imu",
            ),
        },
    )
    transformer = HarbourExclusionTransformer()
    transformer.transform(session)

    transformer.print_summary()

    captured = capsys.readouterr()
    assert (
        captured.out
        == "exclusion zone 'harbour': removed 3 sample(s) across 3 channel(s) in 1 time windows\n"
    )
