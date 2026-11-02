from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import HTTPException, UploadFile, status

from .constants import PROJECT_ROOT
from .models import JobResponse

JOB_PAYLOAD_ROOT = Path(
    os.getenv("SESSION_UPLOAD_DIR", str(PROJECT_ROOT / "data" / "jobs"))
)
JOB_PAYLOAD_ROOT.mkdir(parents=True, exist_ok=True)

_jobs: dict[str, JobResponse] = {}
_jobs_lock = Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _set_job_state(
    job_id: str,
    *,
    status_value: Literal["queued", "running", "completed", "failed"],
    progress_percent: float | None = None,
    message: str | None = None,
    output_file_path: str | None = None,
    error: str | None = None,
) -> None:
    with _jobs_lock:
        previous = _jobs.get(job_id)
        if previous is None:
            return
        _jobs[job_id] = previous.model_copy(
            update={
                "status": status_value,
                "progress_percent": progress_percent
                if progress_percent is not None
                else previous.progress_percent,
                "message": message if message is not None else previous.message,
                "output_file_path": output_file_path
                if output_file_path is not None
                else previous.output_file_path,
                "error": error,
                "updated_at": _utc_now(),
            }
        )


def _get_job(job_id: str) -> JobResponse | None:
    with _jobs_lock:
        return _jobs.get(job_id)


SUPPORTED_SESSION_EXTENSIONS = (".tcx", ".fit", ".csv")


def _validate_upload_filenames(
    tcx_file: UploadFile, metadata_json: UploadFile
) -> str:
    tcx_name = (tcx_file.filename or "").lower()
    metadata_name = (metadata_json.filename or "").lower()

    for extension in SUPPORTED_SESSION_EXTENSIONS:
        if tcx_name.endswith(extension):
            break
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`tcx_file` must be a .tcx, .fit, or .csv file.",
        )

    if not metadata_name.endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`metadata_json` must be a .json file.",
        )

    return extension
