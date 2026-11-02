from pathlib import Path

from src.models.job import Job


class FileModule:
    def __init__(self, supported_files: list[str], meta_extension: str = ".json"):
        self.meta_extension = meta_extension.lower()
        # normalize extensions once
        self.supported_files = {ext.lower() for ext in supported_files}
        # meta files are always supported but not treated as session files
        self.supported_files.add(self.meta_extension)

    def extract_folder(self, folder_path: str) -> list[Job]:
        """
        Scan a folder for session+meta pairs.

        A job is created when:
          - there is a "session file" with an extension in supported_files (excluding meta_extension)
          - there is a meta file with the same stem and meta_extension

        Example: session123.gpx + session123.json -> one Job
        """
        folder = Path(folder_path)

        if not folder.exists():
            raise FileNotFoundError(f"Folder does not exist: {str(folder.absolute())}")
        if not folder.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {str(folder.absolute())}"
            )

        meta_ext = self.meta_extension

        # 1) Collect files once
        metas_by_stem: dict[str, Path] = {}
        sessions_by_stem: dict[str, Path] = {}

        for file in folder.iterdir():
            if not file.is_file():
                continue

            ext = file.suffix.lower()
            if ext not in self.supported_files:
                continue

            stem = file.stem
            if ext == meta_ext:
                metas_by_stem[stem] = file
            else:
                # If multiple session files share a stem (rare), choose one deterministically.
                # Here: keep the first one encountered.
                sessions_by_stem.setdefault(stem, file)

        # 2) Pair by stem intersection
        jobs: list[Job] = []
        for stem, session_path in sessions_by_stem.items():
            meta_path = metas_by_stem.get(stem)
            if meta_path is not None:
                jobs.append(
                    Job(session_path=str(session_path), meta_path=str(meta_path))
                )

        return jobs
