from __future__ import annotations

from pathlib import Path

from src.env import read_env_defaults, resolve_env_path


def test_read_env_defaults_uses_override_file_relative_to_project_root(
    monkeypatch, tmp_path
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    default_env_path = project_root / ".env"
    override_env_path = project_root / ".env.dev"

    default_env_path.write_text("POSTGRES_PORT=5434\n", encoding="utf-8")
    override_env_path.write_text("POSTGRES_PORT=5435\n", encoding="utf-8")

    monkeypatch.setenv("SAILING_INSIGHTS_ENV_FILE", ".env.dev")

    values = read_env_defaults(default_env_path)

    assert values["POSTGRES_PORT"] == "5435"


def test_resolve_env_path_keeps_default_without_override(tmp_path) -> None:
    default_env_path = tmp_path / ".env"

    resolved_path = resolve_env_path(default_env_path)

    assert resolved_path == Path(default_env_path)
