import numpy as np
import pytest

from src.utils.geo import haversine_distance_m, kilometers_to_nm, meters_to_nm


def test_haversine_distance_m_returns_zero_for_identical_coordinates() -> None:
    assert haversine_distance_m(57.68, 11.87, 57.68, 11.87) == pytest.approx(0.0)


def test_haversine_distance_m_supports_vector_inputs() -> None:
    distances_m = haversine_distance_m(
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        np.array([0.0, 1.0]),
        np.array([1.0, 0.0]),
    )

    assert isinstance(distances_m, np.ndarray)
    assert distances_m.shape == (2,)
    assert distances_m[0] == pytest.approx(111_195, abs=200)
    assert distances_m[1] == pytest.approx(111_195, abs=200)


def test_meters_to_nm_converts_meters_to_nautical_miles() -> None:
    assert meters_to_nm(1852.0) == pytest.approx(1.0)


def test_kilometers_to_nm_converts_kilometers_to_nautical_miles() -> None:
    assert kilometers_to_nm(1.852) == pytest.approx(1.0)
