from __future__ import annotations

import os
from pathlib import Path

ENV_FILE_ENV_VAR = "SAILING_INSIGHTS_ENV_FILE"


def resolve_env_path(default_path: Path) -> Path:
    override = os.getenv(ENV_FILE_ENV_VAR)
    if not override:
        return default_path

    override_path = Path(override).expanduser()
    if not override_path.is_absolute():
        override_path = default_path.parent / override_path
    return override_path.resolve()


def read_env_defaults(default_path: Path) -> dict[str, str]:
    env_path = resolve_env_path(default_path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key:
            continue

        parsed_value = value.strip()
        if (
            len(parsed_value) >= 2
            and parsed_value[0] == parsed_value[-1]
            and parsed_value[0] in {"'", '"'}
        ):
            parsed_value = parsed_value[1:-1]

        values[key] = parsed_value

    return values
