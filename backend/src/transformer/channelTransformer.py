from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from src.models.canonicalSession import CanonicalSession, ProvenanceRecord


class ChannelTransformer(ABC):
    """
    Base class for transformers that modify existing session channels.

    Provenance for channel transformations is stored on ``session.provenance``
    because channels themselves do not carry provenance records.
    """

    REQUIRED_CHANNELS: Sequence[str] = ()

    @property
    def required_channels(self) -> list[str]:
        return list(self.REQUIRED_CHANNELS)

    @property
    def producer(self) -> str:
        return self.__class__.__name__

    def transform(self, session: CanonicalSession) -> CanonicalSession:
        session.require_channels(self.required_channels)

        transformed_session = self._transform(session)
        if transformed_session is None:
            raise TypeError("ChannelTransformer._transform must return a CanonicalSession")

        provenance_records = self.build_provenance_records(transformed_session)
        if not provenance_records:
            raise ValueError(
                "ChannelTransformer must create at least one provenance record"
            )

        for record in provenance_records:
            self._validate_provenance_record(transformed_session, record)
            transformed_session.add_provenance(record)

        return transformed_session

    def print_summary(self) -> None:
        """Print a human-readable summary."""

    @abstractmethod
    def _transform(self, session: CanonicalSession) -> CanonicalSession:
        """Modify channels on the provided session and return that session."""

    @abstractmethod
    def build_provenance_records(
        self, session: CanonicalSession
    ) -> list[ProvenanceRecord]:
        """Describe the channel changes performed by this transformer."""

    def make_provenance_record(
        self,
        channel_name: str,
        *,
        action: str = "modified",
        inputs: list[str] | None = None,
        config: dict[str, Any] | None = None,
        changes: list[dict[str, Any]] | None = None,
    ) -> ProvenanceRecord:
        return ProvenanceRecord(
            producer=self.producer,
            produced_type="channel",
            produced_name=channel_name,
            action=action,
            inputs=list(inputs) if inputs is not None else self.required_channels,
            config=dict(config) if config is not None else {},
            changes=list(changes) if changes is not None else [],
        )

    def _validate_provenance_record(
        self, session: CanonicalSession, record: ProvenanceRecord
    ) -> None:
        if record.produced_type != "channel":
            raise ValueError(
                "ChannelTransformer provenance must have produced_type='channel'"
            )

        if record.produced_name not in session.channels:
            raise ValueError(
                f"ChannelTransformer provenance refers to unknown channel "
                f"'{record.produced_name}'"
            )
