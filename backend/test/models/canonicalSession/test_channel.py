import numpy as np
import pytest
from src.models.canonicalSession import Channel


def test_channel_valid_1d_values():
    timestamps = np.array([0.0, 1.0, 2.0])
    values = np.array([10.0, 11.0, 12.0])

    channel = Channel(
        name="temperature",
        timestamps=timestamps,
        values=values,
        unit="C",
        source="sensor_a",
    )

    assert channel.name == "temperature"
    assert channel.timestamps is timestamps
    assert channel.values is values
    assert channel.unit == "C"
    assert channel.source == "sensor_a"
    assert channel.is_derived is False
    assert channel.metadata == {}


def test_channel_valid_2d_values():
    timestamps = np.array([0.0, 1.0, 2.0])
    values = np.array(
        [
            [1.0, 2.0],
            [3.0, 4.0],
            [5.0, 6.0],
        ]
    )

    channel = Channel(
        name="vector_signal",
        timestamps=timestamps,
        values=values,
    )

    assert channel.timestamps.shape == (3,)
    assert channel.values.shape == (3, 2)


def test_channel_allows_empty_arrays():
    timestamps = np.array([])
    values = np.array([])

    channel = Channel(
        name="empty",
        timestamps=timestamps,
        values=values,
    )

    assert len(channel.timestamps) == 0
    assert len(channel.values) == 0


def test_channel_raises_when_timestamps_and_values_lengths_differ_for_1d_values():
    timestamps = np.array([0.0, 1.0, 2.0])
    values = np.array([10.0, 11.0])

    with pytest.raises(
        ValueError,
        match=r"mismatched timestamps and values length: 3 != 2",
    ):
        Channel(
            name="bad_channel",
            timestamps=timestamps,
            values=values,
        )


def test_channel_raises_when_timestamps_is_not_numpy_array():
    timestamps = [0.0, 1.0, 2.0]
    values = np.array([10.0, 11.0, 12.0])

    with pytest.raises(
        TypeError,
        match=r"timestamps must be a numpy array",
    ):
        Channel(
            name="bad_timestamps",
            timestamps=timestamps,
            values=values,
        )


def test_channel_raises_when_values_is_not_numpy_array():
    timestamps = np.array([0.0, 1.0, 2.0])
    values = [10.0, 11.0, 12.0]

    with pytest.raises(
        TypeError,
        match=r"values must be a numpy array",
    ):
        Channel(
            name="bad_values",
            timestamps=timestamps,
            values=values,
        )


def test_channel_raises_when_timestamps_is_not_1d():
    timestamps = np.array([[0.0, 1.0, 2.0]])
    values = np.array([10.0, 11.0, 12.0])

    with pytest.raises(
        ValueError,
    ):
        Channel(
            name="bad_timestamps_dim",
            timestamps=timestamps,
            values=values,
        )


def test_channel_raises_when_values_first_dimension_does_not_match_timestamps():
    timestamps = np.array([0.0, 1.0, 2.0])
    values = np.array(
        [
            [1.0, 2.0],
            [3.0, 4.0],
        ]
    )  # first dimension is 2, should be 3

    with pytest.raises(
        ValueError,
    ):
        Channel(
            name="bad_2d_values",
            timestamps=timestamps,
            values=values,
        )


def test_channel_custom_flags_and_metadata():
    timestamps = np.array([0.0, 1.0])
    values = np.array([5.0, 6.0])
    metadata = {"quality": "good", "sensor_id": 42}

    channel = Channel(
        name="derived_signal",
        timestamps=timestamps,
        values=values,
        is_derived=True,
        metadata=metadata,
    )

    assert channel.is_derived is True
    assert channel.metadata == metadata


def test_channel_metadata_uses_independent_default_dict():
    timestamps = np.array([0.0])
    values = np.array([1.0])

    channel1 = Channel(name="c1", timestamps=timestamps, values=values)
    channel2 = Channel(name="c2", timestamps=timestamps, values=values)

    channel1.metadata["x"] = 123

    assert channel1.metadata == {"x": 123}
    assert channel2.metadata == {}
