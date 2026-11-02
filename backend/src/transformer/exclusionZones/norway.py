from src.transformer.exclusionZones.exclusionZone import ExclusionZoneTransformer


class AskoyExclusionZone(ExclusionZoneTransformer):
    """
    Excludes samples recorded inside the Askoy harbour area (Norway, close to Bergen).

    Raw coordinates are stored as (lon, lat) and converted to (lat, lon) for the
    exclusion polygon base class.
    """

    _coordinates_lon_lat = [
        [5.1058684, 60.4384086],
        [5.1096894, 60.4397578],
        [5.1142221, 60.4405339],
        [5.1196217, 60.4417794],
        [5.1237149, 60.4602171],
        [5.1017936, 60.4621677],
        [5.0843635, 60.4553664],
        [5.096233, 60.4397549],
        [5.0996206, 60.4365397],
        [5.1058684, 60.4384086],
    ]

    @property
    def zone_name(self) -> str:
        return "askoy"

    @property
    def polygon_coordinates(self) -> list[tuple[float, float]]:
        return [(lat, lon) for lon, lat in self._coordinates_lon_lat]
