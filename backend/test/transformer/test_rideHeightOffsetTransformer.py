import numpy as np
import pytest

from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.transformer.rideHeightOffsetTransformer import RideHeightOffsetTransformer


@pytest.fixture
def session_with_height_channel() -> CanonicalSession:
    return CanonicalSession(
        metadata=SessionMetadata(
            session_id="session-height",
            extras={"rideHeightOffsetCm": -24.0},
        ),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "height_m": Channel(
                name="height_m",
                timestamps=np.array([0.0, 1.0, 2.0], dtype=float),
                values=np.array([0.42, 0.44, 0.46], dtype=float),
                unit="m",
                source="ehr_csv",
            ),
        },
    )


def test_transform_applies_ride_height_offset_in_meters(
    session_with_height_channel: CanonicalSession,
) -> None:
    transformer = RideHeightOffsetTransformer()

    result = transformer.transform(session_with_height_channel)

    assert result is session_with_height_channel
    np.testing.assert_allclose(
        result.get_channel("height_m").values,
        np.array([0.18, 0.20, 0.22], dtype=float),
    )


def test_transform_adds_provenance_record_for_applied_offset(
    session_with_height_channel: CanonicalSession,
) -> None:
    transformer = RideHeightOffsetTransformer()

    result = transformer.transform(session_with_height_channel)

    assert len(result.provenance) == 1
    record = result.provenance[0]
    assert record.producer == "RideHeightOffsetTransformer"
    assert record.produced_type == "channel"
    assert record.produced_name == "height_m"
    assert record.inputs == ["height_m"]
    assert record.config == {"offset_cm": -24.0, "offset_m": -0.24}
    assert record.changes == [
        {
            "field": "values",
            "operation": "offset_apply",
            "value_offset_cm": -24.0,
            "value_offset_m": -0.24,
            "description": "Applied ride height offset of -24 cm",
        }
    ]


def test_transform_noops_when_offset_metadata_missing() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-no-offset"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([], dtype=float),
                values=np.array([], dtype=float),
                unit="deg",
                source="gps",
            ),
            "height_m": Channel(
                name="height_m",
                timestamps=np.array([0.0, 1.0], dtype=float),
                values=np.array([0.42, 0.44], dtype=float),
                unit="m",
                source="ehr_csv",
            ),
        },
    )
    transformer = RideHeightOffsetTransformer()

    result = transformer.transform(session)

    np.testing.assert_allclose(
        result.get_channel("height_m").values,
        np.array([0.42, 0.44], dtype=float),
    )
    assert result.provenance[0].changes[0]["operation"] == "noop"


def test_transform_rejects_unsupported_height_unit(
    session_with_height_channel: CanonicalSession,
) -> None:
    session_with_height_channel.get_channel("height_m").unit = "cm"
    transformer = RideHeightOffsetTransformer()

    with pytest.raises(
        ValueError,
        match=(
            "RideHeightOffsetTransformer only supports unit 'm' for channel "
            "'height_m'; got 'cm'"
        ),
    ):
        transformer.transform(session_with_height_channel)
