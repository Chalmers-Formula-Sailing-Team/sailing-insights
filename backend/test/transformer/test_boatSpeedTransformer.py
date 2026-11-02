import numpy as np
import pytest
from src.constants.ChannelNames import ChannelNames
from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.transformer.boatSpeedTransformer import BoatSpeedTransformer
from src.utils.speed_conversion import mps_to_kn


@pytest.fixture
def session_mps() -> CanonicalSession:
    lat_channel = Channel(
        name="lat",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    lon_channel = Channel(
        name="lon",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    boat_speed_channel = Channel(
        name=ChannelNames.SOG.value,
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([0.0, 5.0, 10.89]),
        unit="m/s",
        source="garmin_tcx",
    )

    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-123"),
        channels={
            "lat": lat_channel,
            "lon": lon_channel,
            ChannelNames.SOG.value: boat_speed_channel,
        },
    )


@pytest.fixture
def session_kn() -> CanonicalSession:
    lat_channel = Channel(
        name="lat",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    lon_channel = Channel(
        name="lon",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    boat_speed_channel = Channel(
        name=ChannelNames.SOG.value,
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([0.0, 9.7192, 21.1684176]),
        unit="kn",
        source="garmin_tcx",
    )

    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-456"),
        channels={
            "lat": lat_channel,
            "lon": lon_channel,
            ChannelNames.SOG.value: boat_speed_channel,
        },
    )


def test_transform_converts_boat_speed_from_mps_to_kn(
    session_mps: CanonicalSession,
) -> None:
    transformer = BoatSpeedTransformer()

    result = transformer.transform(session_mps)

    assert result is session_mps
    np.testing.assert_allclose(
        result.get_channel(ChannelNames.SOG.value).values,
        mps_to_kn(np.array([0.0, 5.0, 10.89])),
    )
    assert result.get_channel(ChannelNames.SOG.value).unit == "kn"


def test_transform_adds_provenance_record(session_mps: CanonicalSession) -> None:
    transformer = BoatSpeedTransformer()

    result = transformer.transform(session_mps)

    assert len(result.provenance) == 1

    records = {record.produced_name: record for record in result.provenance}
    assert set(records.keys()) == {ChannelNames.SOG.value}

    for channel_name in (ChannelNames.SOG.value,):
        record = records[channel_name]
        assert record.producer == "BoatSpeedTransformer"
        assert record.produced_type == "channel"
        assert record.produced_name == channel_name
        assert record.action == "modified"
        assert record.inputs == [channel_name]
        assert record.config == {"target_unit": "kn"}
        assert record.changes == [
            {
                "field": "unit",
                "operation": "unit_convert",
                "from": "m/s",
                "to": "kn",
                "description": "Converted boat speed values from m/s to kn",
            }
        ]


def test_transform_noop_when_boat_speed_already_kn(
    session_kn: CanonicalSession,
) -> None:
    transformer = BoatSpeedTransformer()
    original_values = session_kn.get_channel(ChannelNames.SOG.value).values.copy()

    result = transformer.transform(session_kn)

    np.testing.assert_array_equal(
        result.get_channel(ChannelNames.SOG.value).values, original_values
    )
    assert result.get_channel(ChannelNames.SOG.value).unit == "kn"
    assert result.provenance[0].changes[0]["operation"] == "noop"


def test_transform_requires_sog_channel() -> None:
    lat_channel = Channel(
        name="lat",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    lon_channel = Channel(
        name="lon",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-missing"),
        channels={"lat": lat_channel, "lon": lon_channel},
    )

    transformer = BoatSpeedTransformer()

    with pytest.raises(
        KeyError,
        match=rf"Missing required channels: \['{ChannelNames.SOG.value}'\]",
    ):
        transformer.transform(session)


def test_transform_rejects_unsupported_unit(session_mps: CanonicalSession) -> None:
    session_mps.get_channel(ChannelNames.SOG.value).unit = "mph"
    transformer = BoatSpeedTransformer()

    with pytest.raises(
        ValueError,
        match=(
            "BoatSpeedTransformer only supports units 'm/s' or 'kn' for channel "
            f"'{ChannelNames.SOG.value}'; got 'mph'"
        ),
    ):
        transformer.transform(session_mps)


def test_transform_keeps_non_boat_speed_channels_unchanged() -> None:
    lat_channel = Channel(
        name="lat",
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([54.1, 54.2, 54.3]),
        unit="deg",
        source="gps",
    )
    lon_channel = Channel(
        name="lon",
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([10.1, 10.2, 10.3]),
        unit="deg",
        source="gps",
    )
    heart_rate_channel = Channel(
        name="heart_rate",
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([120, 125, 130]),
        unit="bpm",
        source="watch",
    )
    boat_speed_channel = Channel(
        name=ChannelNames.SOG.value,
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([4.0, 5.0, 6.0]),
        unit="m/s",
        source="garmin_tcx",
    )

    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-unchanged"),
        channels={
            "lat": lat_channel,
            "lon": lon_channel,
            "heart_rate": heart_rate_channel,
            ChannelNames.SOG.value: boat_speed_channel,
        },
    )
    transformer = BoatSpeedTransformer()

    non_speed_channel_names = [
        name for name in session.channels if name != ChannelNames.SOG.value
    ]
    before_count = len(session.channels)
    before_channel_names = set(session.channels.keys())
    before_non_speed = {
        name: {
            "channel": session.channels[name],
            "timestamps": session.channels[name].timestamps.copy(),
            "values": session.channels[name].values.copy(),
            "unit": session.channels[name].unit,
            "source": session.channels[name].source,
            "is_derived": session.channels[name].is_derived,
            "metadata": dict(session.channels[name].metadata),
        }
        for name in non_speed_channel_names
    }

    result = transformer.transform(session)

    assert len(result.channels) == before_count
    assert set(result.channels.keys()) == before_channel_names

    for name in non_speed_channel_names:
        before = before_non_speed[name]
        after = result.channels[name]

        assert after is before["channel"]
        np.testing.assert_array_equal(after.timestamps, before["timestamps"])
        np.testing.assert_array_equal(after.values, before["values"])
        assert after.unit == before["unit"]
        assert after.source == before["source"]
        assert after.is_derived == before["is_derived"]
        assert after.metadata == before["metadata"]


def test_print_summary_reports_conversion_counts(
    session_mps: CanonicalSession, capsys: pytest.CaptureFixture[str]
) -> None:
    transformer = BoatSpeedTransformer()
    transformer.transform(session_mps)

    transformer.print_summary()

    captured = capsys.readouterr()
    assert captured.out == "boat speed: converted 1 channel(s) to kn, 0 already in kn\n"
