import json
from pathlib import Path

import numpy as np
import pytest

from src.extraction.metaAdapter import MetaAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_payload() -> dict:
    return json.loads(
        (FIXTURES_DIR / "activity_20297966806.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def meta_file(tmp_path: Path, fixture_payload: dict) -> Path:
    file_path = tmp_path / "session.json"
    file_path.write_text(json.dumps(fixture_payload), encoding="utf-8")
    return file_path


@pytest.fixture
def adapter(meta_file: Path) -> MetaAdapter:
    return MetaAdapter(meta_file)


class TestMetaAdapterScalarFields:
    def test_get_session_name(self, adapter: MetaAdapter) -> None:
        assert adapter.get_session_name() == "demo session"

    def test_get_boat_name(self, adapter: MetaAdapter) -> None:
        assert adapter.get_boat_name() == "Demo Boat"

    def test_get_start_ts(self, adapter: MetaAdapter) -> None:
        assert adapter.get_start_ts() == np.datetime64("2025-09-06T10:30:00")

    def test_get_end_ts(self, adapter: MetaAdapter) -> None:
        assert adapter.get_end_ts() == np.datetime64("2025-09-06T12:36:00")

    def test_get_manual_wind_amt(self, adapter: MetaAdapter) -> None:
        assert adapter.get_manual_wind_amt() == 12.0

    def test_get_manual_wind_gust(self, adapter: MetaAdapter) -> None:
        assert adapter.get_manual_wind_gust() == 17.0

    def test_get_manual_wind_dir(self, adapter: MetaAdapter) -> None:
        assert adapter.get_manual_wind_dir() == 123

    def test_get_manual_wave_height(self, adapter: MetaAdapter) -> None:
        assert adapter.get_manual_wave_height() == pytest.approx(0.8)

    def test_get_ride_height_offset_cm(self, adapter: MetaAdapter) -> None:
        assert adapter.get_ride_height_offset_cm() == pytest.approx(-24.0)

    def test_get_notes(self, adapter: MetaAdapter) -> None:
        assert adapter.get_notes() == "Synthetic fixture data for parser tests."

    def test_get_exported_at(self, adapter: MetaAdapter) -> None:
        assert adapter.get_exported_at() == "2026-03-06T19:21:55.563Z"


class TestMetaAdapterDefaults:
    def test_get_session_name_uses_default_when_missing(self, tmp_path: Path) -> None:
        meta_file = tmp_path / "session.json"
        meta_file.write_text("{}", encoding="utf-8")

        adapter = MetaAdapter(meta_file)

        assert adapter.get_session_name() == "default session"
        assert adapter.get_boat_name() is None
        assert adapter.get_start_ts() is None
        assert adapter.get_end_ts() is None
        assert adapter.get_manual_wind_amt() is None
        assert adapter.get_manual_wind_gust() is None
        assert adapter.get_manual_wind_dir() is None
        assert adapter.get_manual_wave_height() is None
        assert adapter.get_ride_height_offset_cm() is None
        assert adapter.get_notes() is None
        assert adapter.get_exported_at() is None
        assert adapter.get_races() == []


class TestMetaAdapterRaces:
    def test_get_races_preserves_race_fields(self, adapter: MetaAdapter) -> None:
        races = adapter.get_races()

        assert len(races) == 1
        race = races[0]
        assert race.id == "188e5779-006e-4fb3-b9d1-754e193e4d34"
        assert race.name == "Race 1"
        assert race.start_at == np.datetime64("2025-09-06T08:34:20.000")
        assert race.finish_at == np.datetime64("2025-09-06T08:52:43.000")
