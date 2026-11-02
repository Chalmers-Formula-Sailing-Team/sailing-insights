from src.transformer.exclusionZones.exclusionZone import ExclusionZoneTransformer


class LangedragExclusion(ExclusionZoneTransformer):
    """
    Excludes samples recorded inside the Langedrag harbour area (Sweden).

    Raw coordinates are stored as (lon, lat) and converted to (lat, lon) for the
    exclusion polygon base class.
    """

    _coordinates_lon_lat = [
        [11.84590693977313, 57.66912353121583],
        [11.843456147508505, 57.666423574972214],
        [11.842139924278797, 57.66586202310302],
        [11.84192982566239, 57.66413553209276],
        [11.8506952123889, 57.6622279984031],
        [11.853470432896188, 57.66563428926537],
        [11.85421988609275, 57.66743700526112],
        [11.854531110377167, 57.668526068669166],
        [11.848786680497852, 57.66934540268869],
        [11.84789833826153, 57.66884114883072],
        [11.84590693977313, 57.66912353121583],
    ]

    @property
    def zone_name(self) -> str:
        return "langedrag"

    @property
    def polygon_coordinates(self) -> list[tuple[float, float]]:
        return [(lat, lon) for lon, lat in self._coordinates_lon_lat]
