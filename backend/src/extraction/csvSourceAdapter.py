from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection

from src.models.canonicalSession import CanonicalSession
from src.models.job import Job


class CsvSourceAdapter(ABC):
    @property
    @abstractmethod
    def required_headers(self) -> set[str]:
        """Return the CSV headers required for this adapter to parse a file."""

    def can_handle_headers(self, headers: Collection[str]) -> bool:
        normalized_headers = {header.strip() for header in headers}
        return self.required_headers.issubset(normalized_headers)

    @abstractmethod
    def parse_job(self, job: Job) -> CanonicalSession:
        pass
