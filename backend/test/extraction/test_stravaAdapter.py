from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from src.constants.ChannelNames import ChannelNames
from src.constants.MetricNames import MetricNames
from src.extraction.stravaAdapter import StravaAdapter
from src.models.canonicalSession import CanonicalSession
from src.models.job import Job

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _degrees_to_semicircles(value: float) -> int:
    return int(round(value * (2**31) / 180.0))


class FakeFitDataMessage:
    def __init__(self, name: str, values: dict[str, object], frame_type: int) -> None:
        self.name = name
        self._values = values
        self.frame_type = frame_type

    def get_value(self, field_name: str, fallback=None):
        return self._values.get(field_name, fallback)


class FakeFitReader:
    def __init__(self, path: str) -> None:
        self.path = path
        self._frames = [
            SimpleNamespace(frame_type=999, name="ignored"),
            FakeFitDataMessage(
                name="record",
                frame_type=4,
                values={
                    "timestamp": datetime(2025, 9, 6, 8, 30, 23, tzinfo=timezone.utc),
                    "position_lat": _degrees_to_semicircles(57.66800721175969),
                    "position_long": _degrees_to_semicircles(11.84245990589261),
                    "heart_rate": 120,
                },
            ),
            FakeFitDataMessage(
                name="record",
                frame_type=4,
                values={
                    "timestamp": datetime(2025, 9, 6, 8, 30, 24, tzinfo=timezone.utc),
                    "position_lat": _degrees_to_semicircles(57.66804736107588),
                    "position_long": _degrees_to_semicircles(11.842476418241858),
                    "heart_rate": 121,
                    "speed": 6.008999824523926,
                },
            ),
        ]

    def __enter__(self) -> FakeFitReader:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def __iter__(self):
        return iter(self._frames)


class FakeFitReaderWithDuplicateTimestamps(FakeFitReader):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self._frames = [
            FakeFitDataMessage(
                name="record",
                frame_type=4,
                values={
                    "timestamp": datetime(2025, 9, 6, 8, 30, 23, tzinfo=timezone.utc),
                    "position_lat": _degrees_to_semicircles(57.66800721175969),
                    "position_long": _degrees_to_semicircles(11.84245990589261),
                    "heart_rate": 120,
                    "speed": 5.5,
                },
            ),
            FakeFitDataMessage(
                name="record",
                frame_type=4,
                values={
                    "timestamp": datetime(2025, 9, 6, 8, 30, 23, tzinfo=timezone.utc),
                    "position_lat": _degrees_to_semicircles(57.66804736107588),
                    "position_long": _degrees_to_semicircles(11.842476418241858),
                    "heart_rate": 121,
                    "speed": 6.008999824523926,
                },
            ),
            FakeFitDataMessage(
                name="record",
                frame_type=4,
                values={
                    "timestamp": datetime(2025, 9, 6, 8, 30, 24, tzinfo=timezone.utc),
                    "position_lat": _degrees_to_semicircles(57.66808751039207),
                    "position_long": _degrees_to_semicircles(11.842492930591106),
                    "heart_rate": 122,
                    "speed": 6.2,
                },
            ),
        ]


@pytest.fixture
def adapter() -> StravaAdapter:
    return StravaAdapter()


@pytest.fixture
def fitdecode_stub(monkeypatch):
    module = SimpleNamespace(FIT_FRAME_DATA=4, FitReader=FakeFitReader)
    monkeypatch.setitem(sys.modules, "fitdecode", module)
    return module


@pytest.fixture
def fitdecode_duplicate_timestamp_stub(monkeypatch):
    module = SimpleNamespace(
        FIT_FRAME_DATA=4, FitReader=FakeFitReaderWithDuplicateTimestamps
    )
    monkeypatch.setitem(sys.modules, "fitdecode", module)
    return module


@pytest.fixture
def fit_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "session.fit"
    file_path.write_bytes(b"fake-fit-payload")
    return file_path


@pytest.fixture
def meta_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "session.json"
    file_path.write_text(
        (FIXTURES_DIR / "activity_20297966806.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return file_path


@pytest.fixture
def fit_job(fit_file: Path, meta_file: Path) -> Job:
    return Job(session_path=str(fit_file), meta_path=str(meta_file))


@pytest.fixture
def activity_metadata() -> dict:
    return json.loads(
        (FIXTURES_DIR / "activity_20297966806.json").read_text(encoding="utf-8")
    )


class TestStravaAdapterCanHandle:
    def test_can_handle_returns_true_for_fit_file(
        self, adapter: StravaAdapter, fit_job: Job
    ) -> None:
        assert adapter.can_handle(fit_job) is True

    def test_can_handle_returns_false_for_non_fit_file(
        self, adapter: StravaAdapter, tmp_path: Path
    ) -> None:
        session_file = tmp_path / "session.tcx"
        session_file.write_text("<tcx></tcx>", encoding="utf-8")

        meta_file = tmp_path / "session.json"
        meta_file.write_text("{}", encoding="utf-8")

        job = Job(session_path=str(session_file), meta_path=str(meta_file))

        assert adapter.can_handle(job) is False

    def test_can_handle_uppercase_suffix(
        self, adapter: StravaAdapter, tmp_path: Path
    ) -> None:
        session_file = tmp_path / "session.FIT"
        session_file.write_bytes(b"fake-fit-payload")

        meta_file = tmp_path / "session.json"
        meta_file.write_text("{}", encoding="utf-8")

        job = Job(session_path=str(session_file), meta_path=str(meta_file))

        assert adapter.can_handle(job) is True


class TestStravaAdapterParseJobExpectedContract:
    def test_parse_job_returns_canonical_session(
        self, adapter: StravaAdapter, fit_job: Job, fitdecode_stub
    ) -> None:
        session = adapter.parse_job(fit_job)

        assert isinstance(session, CanonicalSession)

    def test_parse_job_extracts_record_channels(
        self, adapter: StravaAdapter, fit_job: Job, fitdecode_stub
    ) -> None:
        session = adapter.parse_job(fit_job)

        assert session.channels[
            ChannelNames.LATITUDE.value
        ].values.tolist() == pytest.approx([57.66800721175969, 57.66804736107588])
        assert session.channels[
            ChannelNames.LONGITUDE.value
        ].values.tolist() == pytest.approx([11.84245990589261, 11.842476418241858])
        assert session.channels[ChannelNames.HEART_RATE.value].values.tolist() == [
            120,
            121,
        ]
        assert session.channels[
            ChannelNames.SOG.value
        ].values.tolist() == pytest.approx([6.008999824523926])

    def test_parse_job_emits_utc_timestamps(
        self, adapter: StravaAdapter, fit_job: Job, fitdecode_stub
    ) -> None:
        session = adapter.parse_job(fit_job)

        assert session.channels[ChannelNames.LATITUDE.value].timestamps.tolist() == [
            np.datetime64("2025-09-06T08:30:23.000"),
            np.datetime64("2025-09-06T08:30:24.000"),
        ]
        assert session.channels[ChannelNames.SOG.value].timestamps.tolist() == [
            np.datetime64("2025-09-06T08:30:24.000")
        ]

    def test_parse_job_sets_expected_metadata_and_metrics(
        self,
        adapter: StravaAdapter,
        fit_job: Job,
        fitdecode_stub,
        activity_metadata: dict,
    ) -> None:
        session = adapter.parse_job(fit_job)

        assert session.metadata.source_type == "strava"
        assert session.metadata.session_name == activity_metadata["sessionName"]
        assert session.metadata.boat_id == activity_metadata["boat"]
        assert session.metadata.notes == activity_metadata["notes"]
        assert session.metadata.extras == {
            "exportedAt": activity_metadata["exportedAt"],
            "rideHeightOffsetCm": float(activity_metadata["rideHeightOffsetCm"]),
        }
        assert set(session.metrics) == {
            MetricNames.MANUAL_WIND_SPEED.value,
            MetricNames.MANUAL_WIND_GUST.value,
            MetricNames.MANUAL_WIND_DIRECTION.value,
            MetricNames.MANUAL_WAVE_HEIGHT.value,
        }

    def test_parse_job_deduplicates_repeated_fit_timestamps(
        self,
        adapter: StravaAdapter,
        fit_job: Job,
        fitdecode_duplicate_timestamp_stub,
    ) -> None:
        session = adapter.parse_job(fit_job)

        assert session.channels[ChannelNames.LATITUDE.value].timestamps.tolist() == [
            np.datetime64("2025-09-06T08:30:23.000"),
            np.datetime64("2025-09-06T08:30:24.000"),
        ]
        assert session.channels[
            ChannelNames.LATITUDE.value
        ].values.tolist() == pytest.approx([57.66804736107588, 57.66808751039207])
        assert session.channels[
            ChannelNames.LONGITUDE.value
        ].values.tolist() == pytest.approx([11.842476418241858, 11.842492930591106])
        assert session.channels[ChannelNames.HEART_RATE.value].values.tolist() == [
            121,
            122,
        ]
        assert session.channels[
            ChannelNames.SOG.value
        ].values.tolist() == pytest.approx([6.008999824523926, 6.2])

    def test_parse_job_raises_helpful_error_without_fitdecode(
        self, adapter: StravaAdapter, fit_job: Job, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            adapter,
            "_load_fitdecode",
            lambda: (_ for _ in ()).throw(
                ModuleNotFoundError(
                    "StravaAdapter requires the 'fitdecode' package to parse .fit files."
                )
            ),
        )

        with pytest.raises(
            ModuleNotFoundError,
            match="StravaAdapter requires the 'fitdecode' package",
        ):
            adapter.parse_job(fit_job)
