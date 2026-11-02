from src.transformer.exclusionZones.exclusionZone import ExclusionZoneTransformer


class MalcesineExclusion(ExclusionZoneTransformer):
    """
    Excludes samples recorded inside the Harbout of Malcesine.

    Raw coordinates are stored as (lon, lat) and converted to (lat, lon) for the
    exclusion polygon base class.
    """

    _coordinates_lon_lat = [
        [10.8340738, 45.7945034],
        [10.8337533, 45.7947188],
        [10.8338141, 45.7950438],
        [10.8341181, 45.7953477],
        [10.8343794, 45.7956399],
        [10.8346111, 45.7958328],
        [10.8347693, 45.7959652],
        [10.8348888, 45.796454],
        [10.8353511, 45.79682],
        [10.8367774, 45.7981532],
        [10.8410408, 45.7970874],
        [10.8392345, 45.7928608],
        [10.8376425, 45.7909182],
        [10.8326215, 45.7931597],
        [10.8335093, 45.7939282],
        [10.8340738, 45.7945034],
    ]

    @property
    def zone_name(self) -> str:
        return "malcesine"

    @property
    def polygon_coordinates(self) -> list[tuple[float, float]]:
        return [(lat, lon) for lon, lat in self._coordinates_lon_lat]
