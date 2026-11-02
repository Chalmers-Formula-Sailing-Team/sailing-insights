import pytest

from src.extraction.adapterResolver import AdapterResolver
from src.models.job import Job


class DummyAdapter:
    def __init__(self, can_handle_result: bool):
        self.can_handle_result = can_handle_result

    def can_handle(self, job: Job) -> bool:
        return self.can_handle_result


def test_resolve_returns_matching_adapter():
    job = Job(session_path="session1.tcx", meta_path="session1.json")
    matching_adapter = DummyAdapter(True)
    non_matching_adapter = DummyAdapter(False)

    resolver = AdapterResolver([non_matching_adapter, matching_adapter])

    result = resolver.resolve(job)

    assert result is matching_adapter


def test_resolve_raises_when_no_adapter_matches():
    job = Job(session_path="session1.tcx", meta_path="session1.json")
    adapter1 = DummyAdapter(False)
    adapter2 = DummyAdapter(False)

    resolver = AdapterResolver([adapter1, adapter2])

    with pytest.raises(ValueError, match="No adapter found for file: session1.tcx"):
        resolver.resolve(job)


def test_resolve_raises_when_multiple_adapters_match():
    job = Job(session_path="session1.tcx", meta_path="session1.json")
    adapter1 = DummyAdapter(True)
    adapter2 = DummyAdapter(True)

    resolver = AdapterResolver([adapter1, adapter2])

    with pytest.raises(
        ValueError, match="Multiple adapters matched file: session1.tcx"
    ):
        resolver.resolve(job)
