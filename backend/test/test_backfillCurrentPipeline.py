from __future__ import annotations

import numpy as np
import src.backfillCurrentPipeline as backfill_module
from src.backfillCurrentPipeline import CurrentPipelineBackfill
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Event,
    Metric,
    ProvenanceRecord,
    SessionMetadata,
)


class _FakeConnection:
    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN204, ANN001
        return False


def _build_session() -> CanonicalSession:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-1"),
        channels={
            "lat": Channel(
                name="lat",
                timestamps=np.array([0.0, 1.0], dtype=float),
                values=np.array([57.0, 57.1], dtype=float),
                unit="deg",
                source="gps",
            ),
            "lon": Channel(
                name="lon",
                timestamps=np.array([0.0, 1.0], dtype=float),
                values=np.array([11.0, 11.1], dtype=float),
                unit="deg",
                source="gps",
            ),
            "sog": Channel(
                name="sog",
                timestamps=np.array([0.0, 1.0], dtype=float),
                values=np.array([12.0, 13.0], dtype=float),
                unit="kn",
                source="gps",
            ),
            "legacy_channel": Channel(
                name="legacy_channel",
                timestamps=np.array([0.0], dtype=float),
                values=np.array([1.0], dtype=float),
                unit="deg",
                source="FakeAnalyzer",
                is_derived=True,
            ),
        },
        metrics={
            "legacy_metric": Metric(
                name="legacy_metric",
                value=1.0,
                unit="kn",
                source="FakeAnalyzer",
            )
        },
        events=[
            Event(
                event_type="legacy_event",
                start_time=0.0,
                source="FakeAnalyzer",
            )
        ],
        provenance=[
            ProvenanceRecord(
                producer="FakeTransformer",
                produced_type="channel",
                produced_name="sog",
            ),
            ProvenanceRecord(
                producer="FakeAnalyzer",
                produced_type="channel",
                produced_name="legacy_channel",
            ),
            ProvenanceRecord(
                producer="FakeAnalyzer",
                produced_type="metric",
                produced_name="legacy_metric",
            ),
            ProvenanceRecord(
                producer="FakeAnalyzer",
                produced_type="event",
                produced_name="legacy_event",
            ),
        ],
    )
    return session


def test_backfill_session_recomputes_outputs_and_persists(monkeypatch) -> None:
    persisted_sessions: list[CanonicalSession] = []

    class FakeTransformer:
        def transform(self, session: CanonicalSession) -> CanonicalSession:
            session.provenance.append(
                ProvenanceRecord(
                    producer=self.__class__.__name__,
                    produced_type="channel",
                    produced_name="sog",
                )
            )
            return session

        def print_summary(self) -> None:
            return None

    class FakeAnalyzer:
        def analyze(self, session: CanonicalSession) -> CanonicalSession:
            session.add_metric(
                Metric(
                    name="fresh_metric",
                    value=2.0,
                    unit="kn",
                    source=self.__class__.__name__,
                )
            )
            session.provenance.append(
                ProvenanceRecord(
                    producer=self.__class__.__name__,
                    produced_type="metric",
                    produced_name="fresh_metric",
                )
            )
            return session

        def print_summary(self) -> None:
            return None

    monkeypatch.setattr(
        backfill_module,
        "_build_canonical_session_from_database",
        lambda connection, session_id: _build_session(),
    )
    monkeypatch.setattr(
        backfill_module,
        "_persist_session_with_existing_connection",
        lambda connection, session: persisted_sessions.append(session),
    )

    backfill = CurrentPipelineBackfill(
        connection_factory=lambda: _FakeConnection(),
        transformer_factories=[FakeTransformer],
        analyzer_factories=[FakeAnalyzer],
    )

    processed = backfill.backfill_session(_FakeConnection(), "session-1")

    assert processed is True
    assert len(persisted_sessions) == 1

    persisted = persisted_sessions[0]
    assert "legacy_channel" not in persisted.channels
    assert "legacy_metric" not in persisted.metrics
    assert [event.event_type for event in persisted.events] == []
    assert persisted.get_metric("fresh_metric").value == 2.0
    assert [record.producer for record in persisted.provenance] == [
        "FakeTransformer",
        "FakeAnalyzer",
    ]


def test_run_collects_missing_sessions_and_errors(monkeypatch) -> None:
    class StubBackfill(CurrentPipelineBackfill):
        def __init__(self) -> None:
            pass

        def backfill_session(
            self,
            connection,
            session_id: str,
            *,
            dry_run: bool = False,
        ) -> bool:
            if session_id == "missing":
                return False
            if session_id == "broken":
                raise ValueError("boom")
            return True

    backfill = StubBackfill()
    backfill._connection_factory = lambda: _FakeConnection()

    summary = backfill.run(session_ids=["ok", "missing", "broken"], dry_run=True)

    assert summary.requested_sessions == 3
    assert summary.processed_sessions == 1
    assert summary.persisted_sessions == 0
    assert summary.missing_sessions == ["missing"]
    assert summary.errors == [("broken", "boom")]


def test_rename_legacy_channels_updates_session_and_provenance() -> None:
    session = CanonicalSession(
        metadata=SessionMetadata(session_id="session-rename"),
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
            "boat_speed": Channel(
                name="boat_speed",
                timestamps=np.array([0.0], dtype=float),
                values=np.array([12.0], dtype=float),
                unit="kn",
                source="gps",
            ),
            "wind_dir": Channel(
                name="wind_dir",
                timestamps=np.array([0.0], dtype=float),
                values=np.array([220.0], dtype=float),
                unit="deg",
                source="weather",
            ),
        },
        provenance=[
            ProvenanceRecord(
                producer="LegacyProducer",
                produced_type="channel",
                produced_name="boat_speed",
                inputs=["boat_speed", "wind_dir"],
            )
        ],
    )

    backfill = CurrentPipelineBackfill(connection_factory=lambda: _FakeConnection())
    backfill._rename_legacy_channels(session)

    assert "boat_speed" not in session.channels
    assert "wind_dir" not in session.channels
    assert "sog" in session.channels
    assert "twd_external" in session.channels
    assert session.get_channel("sog").name == "sog"
    assert session.get_channel("twd_external").name == "twd_external"
    assert session.provenance[0].produced_name == "sog"
    assert session.provenance[0].inputs == ["sog", "twd_external"]
