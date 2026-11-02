from abc import ABC, abstractmethod

from src.models.canonicalSession import CanonicalSession
from src.models.job import Job


class SourceAdapter(ABC):
    @abstractmethod
    def can_handle(self, job: Job) -> bool:
        pass

    @abstractmethod
    def parse_job(self, job: Job) -> CanonicalSession:
        pass
