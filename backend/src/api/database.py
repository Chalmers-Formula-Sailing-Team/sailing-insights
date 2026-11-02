from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg import Connection

from .constants import PROJECT_ROOT
from src.env import read_env_defaults


def _read_root_env_defaults() -> dict[str, str]:
    return read_env_defaults(PROJECT_ROOT / ".env")


def _connect_postgres() -> Connection[Any]:
    env_defaults = _read_root_env_defaults()

    db_host = os.getenv("POSTGRES_HOST") or env_defaults.get("POSTGRES_HOST") or "127.0.0.1"
    db_port = os.getenv("POSTGRES_PORT") or env_defaults.get("POSTGRES_PORT") or "5432"
    db_name = os.getenv("POSTGRES_DB") or env_defaults.get("POSTGRES_DB") or "sailing"
    db_user = os.getenv("POSTGRES_USER") or env_defaults.get("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    if db_password is None:
        db_password = env_defaults.get("POSTGRES_PASSWORD")

    if not db_user:
        raise ValueError("Missing database user: set POSTGRES_USER")
    if db_password is None:
        raise ValueError("Missing database password: set POSTGRES_PASSWORD")

    return psycopg.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        options="-c timezone=UTC",
    )


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
