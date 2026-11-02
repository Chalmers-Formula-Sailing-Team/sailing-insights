from __future__ import annotations

from pathlib import Path

from src.extraction.csvResolver import CsvResolver
from src.extraction.csvSourceAdapter import CsvSourceAdapter
from src.extraction.erhAdapter import ERHAdapter
from src.extraction.sailmonAdapter import SailmonAdapter
from src.extraction.sourceAdapter import SourceAdapter
from src.models.canonicalSession import CanonicalSession
from src.models.job import Job


class CsvAdapter(SourceAdapter):
    """Entry-point adapter for CSV session files."""

    def __init__(self, csv_adapters: list[CsvSourceAdapter] | None = None):
        self.csv_adapters = csv_adapters or [SailmonAdapter(), ERHAdapter()]
        self.csv_resolver = CsvResolver(self.csv_adapters)

    def can_handle(self, job: Job) -> bool:
        return Path(job.session_path).suffix.lower() == ".csv"

    def parse_job(self, job: Job) -> CanonicalSession:
        adapter = self.csv_resolver.resolve(job)
        return adapter.parse_job(job)
