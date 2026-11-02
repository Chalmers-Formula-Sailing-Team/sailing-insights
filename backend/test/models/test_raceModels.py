import numpy as np
from src.models.raceModels import Race


def test_race_stores_explicit_values() -> None:
    start_time = np.datetime64("2026-03-07T10:00:00")
    finish_time = np.datetime64("2026-03-07T11:00:00")

    race = Race(
        id="race-1",
        name="Saturday Series",
        start_at=start_time,
        finish_at=finish_time,
        metadata={"source": "manual"},
    )

    assert race.id == "race-1"
    assert race.name == "Saturday Series"
    assert race.start_at == start_time
    assert race.finish_at == finish_time
    assert race.metadata == {"source": "manual"}


def test_race_defaults_optional_fields_to_empty_or_none() -> None:
    race = Race(
        id="race-2",
        name="Training",
        start_at=None,
        finish_at=None,
    )

    assert race.start_at is None
    assert race.finish_at is None
    assert race.metadata == {}


def test_race_default_mutable_fields_are_independent() -> None:
    first = Race(id="race-1", name="One", start_at=None, finish_at=None)
    second = Race(id="race-2", name="Two", start_at=None, finish_at=None)

    first.metadata["fleet"] = "A"

    assert second.metadata == {}
