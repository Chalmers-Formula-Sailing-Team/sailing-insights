import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from src.models.job import Job


def parse_datetime(value: str | None) -> np.datetime64 | None:
    if value in (None, ""):
        return None

    normalized = value.replace("Z", "+00:00")

    dt = datetime.fromisoformat(normalized)

    if dt.tzinfo is None:
        raise ValueError(f"Timezone required in datetime string: {value}")

    dt_utc = dt.astimezone(timezone.utc)

    return np.datetime64(
        dt_utc.replace(tzinfo=None),
        "ns",
    )


def parse_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def parse_int(value: str | float | int | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def build_session_id(job: Job) -> str:
    # Include the staged import path so each upload job gets its own session id,
    # even when users repeatedly upload files named "session.tcx". Use lexical
    # absolute paths so macOS /tmp does not resolve to /private/tmp.
    seed = str(Path(job.session_path).absolute())
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
