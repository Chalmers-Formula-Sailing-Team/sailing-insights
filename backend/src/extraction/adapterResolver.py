from src.models.job import Job

from src.extraction.sourceAdapter import SourceAdapter


class AdapterResolver:
    def __init__(self, adapters: list[SourceAdapter]):
        self.adapters = adapters

    def resolve(self, job: Job) -> SourceAdapter:
        matches = [adapter for adapter in self.adapters if adapter.can_handle(job)]

        if not matches:
            raise ValueError(f"No adapter found for file: {job.session_path}")

        if len(matches) > 1:
            raise ValueError(f"Multiple adapters matched file: {job.session_path}")

        return matches[0]
