from src.analyzer.courseAnalyzer import COGAnalyzer, TurnRateAnalyzer
from src.analyzer.foilingAnalyzer import FoilingAnalyzer
from src.analyzer.maneuverAnalyzer import ManeuverAnalyzer
from src.analyzer.sessionAnalyzer import SessionAnalyzer
from src.analyzer.windAngleAnlayzer import TWAAnalyzer
from src.extraction.adapterResolver import AdapterResolver
from src.extraction.csvAdapter import CsvAdapter
from src.extraction.garminAdapter import GarminAdapter
from src.extraction.stravaAdapter import StravaAdapter
from src.models.job import Job
from src.persistence.sessionPersistence import SessionPersistence
from src.transformer.boatSpeedTransformer import BoatSpeedTransformer
from src.transformer.exclusionZones.exclusionZoneHandler import ExclusionZoneHandler
from src.transformer.interpolationTransformer import InterpolationTransformer
from src.transformer.rideHeightOffsetTransformer import RideHeightOffsetTransformer


class JobProcessor:
    """The main task of the JobProcessor is to orchestrate and manage a processing Job."""

    def __init__(self):
        self.source_adapters = [GarminAdapter(), StravaAdapter(), CsvAdapter()]
        self.session_persistence = SessionPersistence()

    def process_job(self, job: Job) -> None:
        # extract canonical session

        adapter_resolver = AdapterResolver(self.source_adapters)
        adapter = adapter_resolver.resolve(job)

        session = adapter.parse_job(job)
        for channel in session.channels.values():
            print(
                f"name: {channel.name}, unit: {channel.unit}, samples: {len(channel.values)}"
            )
        # transform
        transformers = [
            ExclusionZoneHandler(),
            BoatSpeedTransformer(),
        ]
        if session.has_channel(RideHeightOffsetTransformer.HEIGHT_CHANNEL_NAME):
            transformers.append(RideHeightOffsetTransformer())
        transformers.append(InterpolationTransformer(max_gap_seconds=5, frequency_hz=1))
        for transformer in transformers:
            session = transformer.transform(session)
            transformer.print_summary()

        # analyze
        analyzers = [
            COGAnalyzer(),
            TurnRateAnalyzer(),
            TWAAnalyzer(),
            ManeuverAnalyzer(),
            FoilingAnalyzer(),
            SessionAnalyzer(),
        ]

        for analyzer in analyzers:
            session = analyzer.analyze(session)
            analyzer.print_summary()

        # persist
        self.session_persistence.persist(session)
