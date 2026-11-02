import numpy as np
import src.jobProcessor as job_processor_module
from src.extraction.csvAdapter import CsvAdapter
from src.extraction.garminAdapter import GarminAdapter
from src.extraction.stravaAdapter import StravaAdapter
from src.jobProcessor import JobProcessor
from src.models.canonicalSession import CanonicalSession, Channel, SessionMetadata
from src.models.job import Job


def test_job_processor_registers_csv_manager_adapter() -> None:
    processor = JobProcessor()

    assert [type(adapter) for adapter in processor.source_adapters] == [
        GarminAdapter,
        StravaAdapter,
        CsvAdapter,
    ]


def test_process_job_calls_print_summary_for_each_transformer_and_analyzer(
    monkeypatch,
) -> None:
    summary_calls: list[str] = []
    persisted_sessions: list[CanonicalSession] = []

    class FakeAdapter:
        def parse_job(self, job: Job) -> CanonicalSession:
            return CanonicalSession(
                metadata=SessionMetadata(session_id="session-job-processor"),
                channels={
                    "lat": Channel(
                        name="lat",
                        timestamps=np.array([0.0], dtype=float),
                        values=np.array([57.0], dtype=float),
                        unit="deg",
                        source="gps",
                    ),
                    "lon": Channel(
                        name="lon",
                        timestamps=np.array([0.0], dtype=float),
                        values=np.array([11.0], dtype=float),
                        unit="deg",
                        source="gps",
                    ),
                },
            )

    class FakeAdapterResolver:
        def __init__(self, source_adapters) -> None:
            self.source_adapters = source_adapters

        def resolve(self, job: Job) -> FakeAdapter:
            return FakeAdapter()

    class FakeTransformer:
        def __init__(self, name: str) -> None:
            self.name = name

        def transform(self, session: CanonicalSession) -> CanonicalSession:
            return session

        def print_summary(self) -> None:
            summary_calls.append(self.name)

    class FakeAnalyzer:
        def __init__(self, name: str) -> None:
            self.name = name

        def analyze(self, session: CanonicalSession) -> CanonicalSession:
            return session

        def print_summary(self) -> None:
            summary_calls.append(self.name)

    class FakeSessionPersistence:
        def persist(self, session: CanonicalSession) -> None:
            persisted_sessions.append(session)

    monkeypatch.setattr(job_processor_module, "AdapterResolver", FakeAdapterResolver)
    monkeypatch.setattr(
        job_processor_module,
        "ExclusionZoneHandler",
        lambda: FakeTransformer("ExclusionZoneHandler"),
    )
    monkeypatch.setattr(
        job_processor_module,
        "BoatSpeedTransformer",
        lambda: FakeTransformer("BoatSpeedTransformer"),
    )
    monkeypatch.setattr(
        job_processor_module,
        "InterpolationTransformer",
        lambda **kwargs: FakeTransformer("InterpolationTransformer"),
    )
    monkeypatch.setattr(
        job_processor_module,
        "COGAnalyzer",
        lambda: FakeAnalyzer("COGAnalyzer"),
    )
    monkeypatch.setattr(
        job_processor_module,
        "TurnRateAnalyzer",
        lambda: FakeAnalyzer("TurnRateAnalyzer"),
    )
    monkeypatch.setattr(
        job_processor_module,
        "TWAAnalyzer",
        lambda: FakeAnalyzer("TWAAnalyzer"),
    )
    monkeypatch.setattr(
        job_processor_module,
        "ManeuverAnalyzer",
        lambda: FakeAnalyzer("ManeuverAnalyzer"),
    )
    monkeypatch.setattr(
        job_processor_module,
        "FoilingAnalyzer",
        lambda: FakeAnalyzer("FoilingAnalyzer"),
    )

    monkeypatch.setattr(
        job_processor_module,
        "SessionAnalyzer",
        lambda: FakeAnalyzer("SessionAnalyzer"),
    )

    processor = JobProcessor()
    processor.session_persistence = FakeSessionPersistence()

    processor.process_job(Job(session_path="session.tcx", meta_path="meta.json"))

    assert summary_calls == [
        "ExclusionZoneHandler",
        "BoatSpeedTransformer",
        "InterpolationTransformer",
        "COGAnalyzer",
        "TurnRateAnalyzer",
        "TWAAnalyzer",
        "ManeuverAnalyzer",
        "FoilingAnalyzer",
        "SessionAnalyzer",
    ]
    assert len(persisted_sessions) == 1
