import numpy as np
import pytest
from src.analyzer.analyzer import Analyzer
from src.models.canonicalSession import (
    CanonicalSession,
    Channel,
    Event,
    Metric,
    SessionMetadata,
)


@pytest.fixture
def session() -> CanonicalSession:
    lat_channel = Channel(
        name="lat",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    lon_channel = Channel(
        name="lon",
        timestamps=np.array([], dtype=float),
        values=np.array([], dtype=float),
        unit="deg",
        source="gps",
    )
    boat_speed_channel = Channel(
        name="boat_speed",
        timestamps=np.array([1.0, 2.0, 3.0]),
        values=np.array([4.0, 5.0, 6.0]),
        unit="kn",
        source="gps",
    )

    return CanonicalSession(
        metadata=SessionMetadata(session_id="session-123"),
        channels={
            "lat": lat_channel,
            "lon": lon_channel,
            "boat_speed": boat_speed_channel,
        },
    )


class SessionSummaryAnalyzer(Analyzer):
    REQUIRED_CHANNELS = ("boat_speed",)

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        speed = session.get_channel("boat_speed")

        session.add_metric(
            Metric(
                name="avg_boat_speed",
                value=float(np.mean(speed.values)),
                unit="kn",
                source=self.producer,
            )
        )
        self.add_channel(
            session,
            Channel(
                name="boat_speed_smooth",
                timestamps=speed.timestamps.copy(),
                values=np.convolve(speed.values, np.ones(3) / 3, mode="same"),
                unit="kn",
                source=self.producer,
                is_derived=True,
            ),
        )
        session.add_event(
            Event(
                event_type="high_speed_segment",
                start_time=float(speed.timestamps[-1]),
                source=self.producer,
            )
        )
        return session

    def build_provenance_records(self, session: CanonicalSession):
        return [
            self.make_provenance_record(
                "metric",
                "avg_boat_speed",
                inputs=["boat_speed"],
                config={"method": "mean"},
            ),
            self.make_provenance_record(
                "channel",
                "boat_speed_smooth",
                inputs=["boat_speed"],
                config={"method": "moving_average", "window": 3},
            ),
            self.make_provenance_record(
                "event",
                "high_speed_segment",
                inputs=["boat_speed"],
                config={"trigger": "last_sample"},
            ),
        ]


class MissingChannelAnalyzer(Analyzer):
    REQUIRED_CHANNELS = ("heel",)

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        return session

    def build_provenance_records(self, session: CanonicalSession):
        return [self.make_provenance_record("channel", "lat")]


class NoProvenanceAnalyzer(Analyzer):
    REQUIRED_CHANNELS = ("boat_speed",)

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        return session

    def build_provenance_records(self, session: CanonicalSession):
        return []


class UnknownOutputAnalyzer(Analyzer):
    REQUIRED_CHANNELS = ("boat_speed",)

    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        return session

    def build_provenance_records(self, session: CanonicalSession):
        return [self.make_provenance_record("metric", "avg_speed_that_does_not_exist")]


def test_analyze_adds_outputs_and_provenance(session: CanonicalSession) -> None:
    analyzer = SessionSummaryAnalyzer()

    result = analyzer.analyze(session)

    assert result is session
    assert result.has_metric("avg_boat_speed")
    assert result.has_channel("boat_speed_smooth")
    assert len(result.get_events(event_type="high_speed_segment")) == 1

    assert len(result.provenance) == 3
    records = {
        (record.produced_type, record.produced_name): record
        for record in result.provenance
    }
    assert set(records.keys()) == {
        ("metric", "avg_boat_speed"),
        ("channel", "boat_speed_smooth"),
        ("event", "high_speed_segment"),
    }


def test_analyze_requires_declared_channels(session: CanonicalSession) -> None:
    analyzer = MissingChannelAnalyzer()

    with pytest.raises(KeyError, match=r"Missing required channels: \['heel'\]"):
        analyzer.analyze(session)


def test_analyze_requires_at_least_one_provenance_record(
    session: CanonicalSession,
) -> None:
    analyzer = NoProvenanceAnalyzer()

    with pytest.raises(
        ValueError,
        match="Analyzer must create at least one provenance record",
    ):
        analyzer.analyze(session)


def test_analyze_rejects_unknown_provenance_outputs(session: CanonicalSession) -> None:
    analyzer = UnknownOutputAnalyzer()

    with pytest.raises(
        ValueError,
        match="Analyzer provenance refers to unknown metric 'avg_speed_that_does_not_exist'",
    ):
        analyzer.analyze(session)
