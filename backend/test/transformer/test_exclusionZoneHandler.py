import numpy as np
from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.transformer.exclusionZones.exclusionZoneHandler import ExclusionZoneHandler
from src.transformer.exclusionZones.italy import MalcesineExclusion
from src.transformer.exclusionZones.norway import AskoyExclusionZone
from src.transformer.exclusionZones.sweden import LangedragExclusion


class FakeZone:
    def __init__(self, name: str, visited: list[str]) -> None:
        self.name = name
        self.visited = visited

    def transform(self, session: CanonicalSession) -> CanonicalSession:
        self.visited.append(self.name)
        return session

    def print_summary(self) -> None:
        print(f"zone {self.name}")


def _make_session() -> CanonicalSession:
    timestamps = np.array([0.0], dtype=float)
    return CanonicalSession(
        metadata=SessionMetadata(session_id="handler-session"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=timestamps.copy(),
                values=np.array([57.0], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=timestamps.copy(),
                values=np.array([11.0], dtype=float),
                unit="deg",
                source="gps",
            ),
        },
    )


def test_transform_applies_all_configured_zones_in_order() -> None:
    visited: list[str] = []
    handler = ExclusionZoneHandler(
        zones=[FakeZone("alpha", visited), FakeZone("beta", visited)]
    )

    result = handler.transform(_make_session())

    assert result.metadata.session_id == "handler-session"
    assert visited == ["alpha", "beta"]


def test_print_summary_delegates_to_each_zone(capsys) -> None:
    visited: list[str] = []
    handler = ExclusionZoneHandler(
        zones=[FakeZone("alpha", visited), FakeZone("beta", visited)]
    )

    handler.print_summary()

    captured = capsys.readouterr()
    assert captured.out == "zone alpha\nzone beta\n"


def test_discover_zones_loads_all_zone_transformers_in_module_order() -> None:
    handler = ExclusionZoneHandler()

    assert [type(zone) for zone in handler.zones] == [
        MalcesineExclusion,
        AskoyExclusionZone,
        LangedragExclusion,
    ]
