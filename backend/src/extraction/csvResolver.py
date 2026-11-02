from __future__ import annotations

import csv
from pathlib import Path

from src.extraction.csvSourceAdapter import CsvSourceAdapter
from src.models.job import Job


class CsvResolver:
    def __init__(self, adapters: list[CsvSourceAdapter]):
        self.adapters = adapters

    def resolve(self, job: Job) -> CsvSourceAdapter:
        headers = self.read_headers(job.session_path)
        matches = [
            adapter for adapter in self.adapters if adapter.can_handle_headers(headers)
        ]

        if not matches:
            raise ValueError(
                "No CSV adapter found for file: "
                f"{job.session_path} with headers {sorted(headers)}"
            )

        if len(matches) > 1:
            raise ValueError(
                "Multiple CSV adapters matched file: "
                f"{job.session_path} with headers {sorted(headers)}"
            )

        return matches[0]

    def read_headers(self, session_path: str) -> set[str]:
        suffix = Path(session_path).suffix.lower()
        if suffix != ".csv":
            raise ValueError(f"CSV resolver only supports .csv files, got: {session_path}")

        with open(session_path, "r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file, delimiter=self._detect_delimiter(csv_file))
            try:
                headers = next(reader)
            except StopIteration as exc:
                raise ValueError(f"CSV file is empty: {session_path}") from exc

        normalized_headers = {header.strip() for header in headers if header.strip()}
        if not normalized_headers:
            raise ValueError(f"CSV file has no headers: {session_path}")

        return normalized_headers

    def _detect_delimiter(self, csv_file) -> str:
        position = csv_file.tell()
        first_line = csv_file.readline()
        csv_file.seek(position)

        if first_line.count(";") > first_line.count(","):
            return ";"
        return ","
