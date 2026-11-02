from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from src.models.canonicalSession import CanonicalSession, Channel, ProvenanceRecord


class Analyzer(ABC):
    """
    Base class for analyzers that add derived outputs to a session.

    Analyzers can create channels, events, metrics, and artifacts.
    Provenance for these outputs is stored on ``session.provenance``.
    """

    REQUIRED_CHANNELS: Sequence[str] = ()
    ALLOWED_PRODUCED_TYPES: frozenset[str] = frozenset(
        {"channel", "event", "metric", "artifact"}
    )

    @property
    def required_channels(self) -> list[str]:
        return list(self.REQUIRED_CHANNELS)

    @property
    def producer(self) -> str:
        return self.__class__.__name__

    def analyze(self, session: CanonicalSession) -> CanonicalSession:
        self._prepare_analysis_state()
        session.require_channels(self.required_channels)

        analyzed_session = self._analyze(session)
        if analyzed_session is None:
            raise TypeError("Analyzer._analyze must return a CanonicalSession")

        provenance_records = self.build_provenance_records(analyzed_session)
        if not provenance_records:
            raise ValueError("Analyzer must create at least one provenance record")

        for record in provenance_records:
            self._validate_provenance_record(analyzed_session, record)
            analyzed_session.add_provenance(record)

        return analyzed_session

    def print_summary(self) -> None:
        """Print a human-readable summary."""

    @abstractmethod
    def _analyze(self, session: CanonicalSession) -> CanonicalSession:
        """Add analysis outputs on the provided session and return that session."""

    @abstractmethod
    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        """Describe the outputs produced by this analyzer."""

    def make_provenance_record(
        self,
        produced_type: str,
        produced_name: str,
        *,
        action: str = "created",
        inputs: list[str] | None = None,
        config: dict[str, Any] | None = None,
        changes: list[dict[str, Any]] | None = None,
    ) -> ProvenanceRecord:
        if produced_type == "channel":
            produced_name = self._resolved_channel_name(produced_name)

        return ProvenanceRecord(
            producer=self.producer,
            produced_type=produced_type,
            produced_name=produced_name,
            action=action,
            inputs=list(inputs) if inputs is not None else self.required_channels,
            config=dict(config) if config is not None else {},
            changes=list(changes) if changes is not None else [],
        )

    def _validate_provenance_record(
        self, session: CanonicalSession, record: ProvenanceRecord
    ) -> None:
        if record.produced_type not in self.ALLOWED_PRODUCED_TYPES:
            raise ValueError(
                "Analyzer provenance has unsupported produced_type "
                f"'{record.produced_type}'"
            )

        if (
            record.produced_type == "channel"
            and record.produced_name not in session.channels
        ):
            raise ValueError(
                "Analyzer provenance refers to unknown channel "
                f"'{record.produced_name}'"
            )

        if (
            record.produced_type == "metric"
            and record.produced_name not in session.metrics
        ):
            raise ValueError(
                f"Analyzer provenance refers to unknown metric '{record.produced_name}'"
            )

        if (
            record.produced_type == "artifact"
            and record.produced_name not in session.artifacts
        ):
            raise ValueError(
                "Analyzer provenance refers to unknown artifact "
                f"'{record.produced_name}'"
            )

        if record.produced_type == "event" and not any(
            event.event_type == record.produced_name for event in session.events
        ):
            raise ValueError(
                f"Analyzer provenance refers to unknown event '{record.produced_name}'"
            )

    def add_channel(self, session: CanonicalSession, channel: Channel) -> str:
        actual_name = self._unique_channel_name(session, channel.name)
        channel.name = actual_name
        session.add_channel(channel)
        self._produced_channel_names[self._current_channel_base_name] = actual_name
        self._current_channel_base_name = None
        return actual_name

    def _prepare_analysis_state(self) -> None:
        self._produced_channel_names: dict[str, str] = {}
        self._current_channel_base_name: str | None = None

    def _resolved_channel_name(self, channel_name: str) -> str:
        produced_channel_names = getattr(self, "_produced_channel_names", {})
        return produced_channel_names.get(channel_name, channel_name)

    def _unique_channel_name(self, session: CanonicalSession, desired_name: str) -> str:
        self._current_channel_base_name = desired_name
        if desired_name not in session.channels:
            return desired_name

        producer_suffix = self._producer_suffix()
        candidate_name = f"{desired_name}_{producer_suffix}"
        if candidate_name not in session.channels:
            return candidate_name

        index = 2
        while f"{candidate_name}_{index}" in session.channels:
            index += 1
        return f"{candidate_name}_{index}"

    def _producer_suffix(self) -> str:
        producer = self.producer
        return producer[:1].lower() + producer[1:]
        return producer[:1].lower() + producer[1:]
        return producer[:1].lower() + producer[1:]
