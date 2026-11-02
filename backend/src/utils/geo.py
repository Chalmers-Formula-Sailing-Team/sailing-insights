from __future__ import annotations

import numpy as np

EARTH_RADIUS_M = 6_371_008.8
METER_PER_NAUTICAL_MILE = 1852.0
METERS_PER_KILOMETER = 1000.0


def haversine_distance_m(
    latitude_a_deg: float | np.ndarray,
    longitude_a_deg: float | np.ndarray,
    latitude_b_deg: float | np.ndarray,
    longitude_b_deg: float | np.ndarray,
) -> float | np.ndarray:
    lat_a = np.radians(latitude_a_deg)
    lon_a = np.radians(longitude_a_deg)
    lat_b = np.radians(latitude_b_deg)
    lon_b = np.radians(longitude_b_deg)

    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    sin_half_delta_lat = np.sin(delta_lat / 2.0)
    sin_half_delta_lon = np.sin(delta_lon / 2.0)

    haversine_a = (
        sin_half_delta_lat**2
        + np.cos(lat_a) * np.cos(lat_b) * sin_half_delta_lon**2
    )
    haversine_a = np.clip(haversine_a, 0.0, 1.0)
    central_angle = 2.0 * np.arctan2(
        np.sqrt(haversine_a), np.sqrt(1.0 - haversine_a)
    )

    return EARTH_RADIUS_M * central_angle


def meters_to_nm(distance_m: float | np.ndarray) -> float | np.ndarray:
    return distance_m / METER_PER_NAUTICAL_MILE


def kilometers_to_nm(distance_km: float | np.ndarray) -> float | np.ndarray:
    return meters_to_nm(distance_km * METERS_PER_KILOMETER)
