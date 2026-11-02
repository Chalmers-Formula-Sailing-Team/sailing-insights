import numpy as np
import pytest

from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.transformer.channelTransformer import ChannelTransformer


@pytest.fixture
def session() -> CanonicalSession:
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
    speed_channel = Channel(
        name="speed",
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([4.0, 5.0, 6.0]),
        unit="kn",
        source="gps",
    )

    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-123"),
        channels={"lat": lat_channel, "lon": lon_channel, "speed": speed_channel},
    )


class OffsetSpeedTransformer(ChannelTransformer):
    REQUIRED_CHANNELS = ("speed",)

    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        speed_channel = session.get_channel("speed")
        speed_channel.values = speed_channel.values + 1.5
        return session

    def build_provenance_records(self, session: CanonicalSession):
        return [
            self.make_provenance_record(
                "speed",
                inputs=["speed"],
                config={"offset": 1.5},
                changes=[
                    {
                        "field": "values",
                        "operation": "offset",
                        "amount": 1.5,
                        "description": "Added a constant offset to the speed channel",
                    }
                ],
            )
        ]


class MissingChannelTransformer(ChannelTransformer):
    REQUIRED_CHANNELS = ("heel",)

    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        return session

    def build_provenance_records(self, session: CanonicalSession):
        return [self.make_provenance_record("lat")]


class NoProvenanceTransformer(ChannelTransformer):
    REQUIRED_CHANNELS = ("speed",)

    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        return session

    def build_provenance_records(self, session: CanonicalSession):
        return []


def test_transform_returns_session_and_modifies_existing_channel(
    session: CanonicalSession,
) -> None:
    transformer = OffsetSpeedTransformer()

    result = transformer.transform(session)

    assert result is session
    np.testing.assert_array_equal(result.get_channel("speed").values, [5.5, 6.5, 7.5])


def test_transform_adds_provenance_record_for_channel_changes(
    session: CanonicalSession,
) -> None:
    transformer = OffsetSpeedTransformer()

    result = transformer.transform(session)

    assert len(result.provenance) == 1
    record = result.provenance[0]
    assert record.producer == "OffsetSpeedTransformer"
    assert record.produced_type == "channel"
    assert record.produced_name == "speed"
    assert record.action == "modified"
    assert record.inputs == ["speed"]
    assert record.config == {"offset": 1.5}
    assert record.changes == [
        {
            "field": "values",
            "operation": "offset",
            "amount": 1.5,
            "description": "Added a constant offset to the speed channel",
        }
    ]


def test_transform_requires_declared_channels(session: CanonicalSession) -> None:
    transformer = MissingChannelTransformer()

    with pytest.raises(KeyError, match=r"Missing required channels: \['heel'\]"):
        transformer.transform(session)


def test_transform_requires_at_least_one_provenance_record(
    session: CanonicalSession,
) -> None:
    transformer = NoProvenanceTransformer()

    with pytest.raises(
        ValueError,
        match="ChannelTransformer must create at least one provenance record",
    ):
        transformer.transform(session)
