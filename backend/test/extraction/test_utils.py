import numpy as np
import pytest
from src.extraction.utils import (
    build_session_id,
    parse_datetime,
    parse_float,
    parse_int,
)
from src.models.job import Job


class TestParseDatetime:
    def test_returns_none_for_none(self) -> None:
        assert parse_datetime(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert parse_datetime("") is None

    def test_parses_naive_iso_datetime(self) -> None:
        with pytest.raises(
            ValueError,
            match="Timezone required in datetime string: 2025-09-06T10:30:00",
        ):
            parse_datetime("2025-09-06T10:30:00")

    def test_time_alredy_in_UTC(self) -> None:
        assert parse_datetime("2025-09-06T08:34:20.000Z") == np.datetime64(
            "2025-09-06T08:34:20.000"
        )

    def test_normalizes_offset_datetime_to_utc(self) -> None:
        assert parse_datetime("2025-09-06T10:34:20.000+02:00") == np.datetime64(
            "2025-09-06T08:34:20.000"
        )

    def test_normalizes_neg_offset_datetime_to_utc(self) -> None:
        assert parse_datetime("2025-09-06T10:34:20.000-04:00") == np.datetime64(
            "2025-09-06T14:34:20.000"
        )


class TestParseFloat:
    def test_returns_none_for_none(self) -> None:
        assert parse_float(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert parse_float("") is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("12", 12.0), ("12.5", 12.5), (12, 12.0), (12.5, 12.5)],
    )
    def test_parses_numeric_values(
        self, value: str | float | int, expected: float
    ) -> None:
        assert parse_float(value) == expected


class TestParseInt:
    def test_returns_none_for_none(self) -> None:
        assert parse_int(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert parse_int("") is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("123", 123), (123, 123), (123.9, 123)],
    )
    def test_parses_numeric_values(
        self, value: str | float | int, expected: int
    ) -> None:
        assert parse_int(value) == expected


class TestBuildSessionId:
    def test_returns_uuid_string_based_on_staged_session_path(self) -> None:
        job = Job(session_path="/tmp/session.tcx", meta_path="/tmp/session.json")

        session_id = build_session_id(job)

        assert session_id == "baa7e665-8d13-5d8e-8c09-794c372b83f8"

    def test_same_full_path_produces_same_id(self) -> None:
        first_job = Job(
            session_path="/tmp/import-a/session.tcx",
            meta_path="/tmp/import-a/session.json",
        )
        second_job = Job(
            session_path="/tmp/import-a/session.tcx",
            meta_path="/tmp/import-a/session.json",
        )

        assert build_session_id(first_job) == build_session_id(second_job)

    def test_same_filename_in_different_paths_produces_different_ids(self) -> None:
        first_job = Job(
            session_path="/tmp/import-a/session.tcx",
            meta_path="/tmp/import-a/session.json",
        )
        second_job = Job(
            session_path="/var/tmp/import-b/session.tcx",
            meta_path="/var/tmp/import-b/session.json",
        )

        assert build_session_id(first_job) != build_session_id(second_job)

    def test_different_filenames_produce_different_ids(self) -> None:
        first_job = Job(
            session_path="/tmp/session-a.tcx",
            meta_path="/tmp/session-a.json",
        )
        second_job = Job(
            session_path="/tmp/session-b.tcx",
            meta_path="/tmp/session-b.json",
        )

        assert build_session_id(first_job) != build_session_id(second_job)
