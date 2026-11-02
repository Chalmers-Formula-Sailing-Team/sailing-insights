from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Callable

from psycopg import Connection
from psycopg.rows import dict_row

from src.analyzer.courseAnalyzer import COGAnalyzer, TurnRateAnalyzer
from src.analyzer.foilingAnalyzer import FoilingAnalyzer
from src.analyzer.maneuverAnalyzer import ManeuverAnalyzer
from src.analyzer.sessionAnalyzer import SessionAnalyzer
from src.analyzer.windAngleAnlayzer import TWAAnalyzer
from src.api.session_data import (
    _build_canonical_session_from_database,
    _persist_session_with_existing_connection,
    _remove_analyzer_outputs,
)
from src.constants.ChannelNames import ChannelNames
from src.models.canonicalSession import CanonicalSession
from src.persistence.sessionPersistence import SessionPersistence
from src.transformer.boatSpeedTransformer import BoatSpeedTransformer
from src.transformer.exclusionZones.exclusionZoneHandler import ExclusionZoneHandler
from src.transformer.interpolationTransformer import InterpolationTransformer
from src.transformer.rideHeightOffsetTransformer import RideHeightOffsetTransformer

ConnectionFactory = Callable[[], Connection[Any]]
TransformerFactory = Callable[[], Any]
AnalyzerFactory = Callable[[], Any]


@dataclass(slots=True)
class BackfillSummary:
    requested_sessions: int = 0
    processed_sessions: int = 0
    persisted_sessions: int = 0
    missing_sessions: list[str] = field(default_factory=list)
    ride_height_not_backfilled: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


class CurrentPipelineBackfill:
    LEGACY_CHANNEL_RENAMES: dict[str, str] = {
        "boat_speed": ChannelNames.SOG.value,
        "wind_gust_amt": ChannelNames.TWG_EXTERNAL.value,
        "wind_dir": ChannelNames.TWD_EXTERNAL.value,
        "wind_amt": ChannelNames.TWS_EXTERNAL.value,
    }

    def __init__(
        self,
        connection_factory: ConnectionFactory | None = None,
        transformer_factories: list[TransformerFactory] | None = None,
        analyzer_factories: list[AnalyzerFactory] | None = None,
    ) -> None:
        persistence = SessionPersistence(connection_factory=connection_factory)
        self._connection_factory = persistence._connection_factory
        self._transformer_factories = transformer_factories or [
            ExclusionZoneHandler,
            BoatSpeedTransformer,
            lambda: InterpolationTransformer(max_gap_seconds=5, frequency_hz=1),
        ]
        self._analyzer_factories = analyzer_factories or [
            COGAnalyzer,
            TurnRateAnalyzer,
            TWAAnalyzer,
            lambda: ManeuverAnalyzer(foiling_speed_knots=7.0),
            lambda: FoilingAnalyzer(foiling_speed_knots=7.0),
            SessionAnalyzer,
        ]

    def run(
        self,
        *,
        session_ids: list[str] | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> BackfillSummary:
        resolved_session_ids = session_ids or self._list_session_ids(limit=limit)
        summary = BackfillSummary(requested_sessions=len(resolved_session_ids))

        for session_id in resolved_session_ids:
            try:
                with self._connection_factory() as connection:
                    processed = self.backfill_session(
                        connection,
                        session_id,
                        dry_run=dry_run,
                    )
            except Exception as exc:
                summary.errors.append((session_id, str(exc)))
                continue

            if not processed:
                summary.missing_sessions.append(session_id)
                continue

            summary.processed_sessions += 1
            if dry_run:
                continue
            summary.persisted_sessions += 1

        return summary

    def backfill_session(
        self,
        connection: Connection[Any],
        session_id: str,
        *,
        dry_run: bool = False,
    ) -> bool:
        session = _build_canonical_session_from_database(connection, session_id)
        if session is None:
            return False

        self._rename_legacy_channels(session)
        self._remove_recomputed_outputs(session)

        transformers = [factory() for factory in self._transformer_factories]
        for transformer in transformers:
            session = transformer.transform(session)
            transformer.print_summary()

        analyzers = [factory() for factory in self._analyzer_factories]
        for analyzer in analyzers:
            session = analyzer.analyze(session)
            analyzer.print_summary()

        if not dry_run:
            _persist_session_with_existing_connection(connection, session)

        return True

    def _rename_legacy_channels(self, session: CanonicalSession) -> None:
        for legacy_name, current_name in self.LEGACY_CHANNEL_RENAMES.items():
            if legacy_name not in session.channels:
                continue

            if current_name in session.channels:
                continue

            channel = session.channels.pop(legacy_name)
            channel.name = current_name
            session.channels[current_name] = channel

            for record in session.provenance:
                if (
                    record.produced_type == "channel"
                    and record.produced_name == legacy_name
                ):
                    record.produced_name = current_name
                record.inputs = [
                    current_name if input_name == legacy_name else input_name
                    for input_name in record.inputs
                ]

    def _list_session_ids(self, *, limit: int | None = None) -> list[str]:
        with self._connection_factory() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                query = """
                    SELECT id::text AS id
                    FROM session
                    ORDER BY start_at ASC NULLS LAST, id ASC
                """
                params: tuple[object, ...] = ()
                if limit is not None:
                    query += " LIMIT %s"
                    params = (limit,)
                cursor.execute(query, params)
                return [str(row["id"]) for row in cursor.fetchall()]

    def _remove_recomputed_outputs(self, session: CanonicalSession) -> None:
        self._remove_transformer_provenance(session)
        for producer_name in self._analyzer_producer_names():
            _remove_analyzer_outputs(session, producer_name=producer_name)

    def _remove_transformer_provenance(self, session: CanonicalSession) -> None:
        producer_names = self._transformer_producer_names()
        session.provenance = [
            record
            for record in session.provenance
            if record.producer not in producer_names
        ]

    def _transformer_producer_names(self) -> set[str]:
        producer_names: set[str] = set()
        for factory in self._transformer_factories:
            producer_names.update(self._resolve_processor_producer_names(factory()))
        return producer_names

    def _analyzer_producer_names(self) -> list[str]:
        return [
            self._resolve_processor_producer_names(factory()).pop()
            for factory in self._analyzer_factories
        ]

    def _resolve_processor_producer_names(self, processor: Any) -> set[str]:
        if isinstance(processor, ExclusionZoneHandler):
            return {zone.__class__.__name__ for zone in processor.zones}
        return {processor.__class__.__name__}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill persisted sessions by rebuilding them from the database and "
            "rerunning the current transform/analyzer pipeline."
        )
    )
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        help="Backfill only the specified session id. Repeatable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Backfill at most this many sessions when --session-id is not provided.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the backfill pipeline without persisting results.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backfill = CurrentPipelineBackfill()
    summary = backfill.run(
        session_ids=args.session_ids,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print(
        "backfill summary: "
        f"requested={summary.requested_sessions}, "
        f"processed={summary.processed_sessions}, "
        f"persisted={summary.persisted_sessions}, "
        f"missing={len(summary.missing_sessions)}, "
        f"errors={len(summary.errors)}"
    )
    print(
        "ride height backfill note: "
        f"{RideHeightOffsetTransformer.__name__} cannot be reconstructed from the "
        "current database state because rideHeightOffsetCm is not persisted."
    )
    if summary.missing_sessions:
        print(f"missing sessions: {', '.join(summary.missing_sessions)}")
    if summary.errors:
        for session_id, error in summary.errors:
            print(f"error for session {session_id}: {error}")


if __name__ == "__main__":
    main()
