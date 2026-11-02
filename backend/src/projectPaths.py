from __future__ import annotations

import os
from pathlib import Path


def _looks_like_repo_root(candidate: Path) -> bool:
    return (candidate / "backend" / "pyproject.toml").exists()


def _looks_like_backend_root(candidate: Path) -> bool:
    return (candidate / "pyproject.toml").exists() and (candidate / "src").is_dir()


def discover_project_root(
    module_path: Path | None = None,
    cwd: Path | None = None,
) -> Path:
    override = os.getenv("SAILING_INSIGHTS_PROJECT_ROOT") or os.getenv("PROJECT_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    resolved_cwd = (cwd or Path.cwd()).resolve()
    resolved_module_path = (module_path or Path(__file__)).resolve()

    candidates: list[Path] = []
    for candidate in [
        resolved_cwd,
        *resolved_cwd.parents,
        resolved_module_path.parent,
        *resolved_module_path.parents,
    ]:
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if _looks_like_repo_root(candidate):
            return candidate
        if _looks_like_backend_root(candidate):
            return candidate.parent

    # Fall back to the historical assumption when no better marker is available.
    if len(resolved_module_path.parents) > 3:
        return resolved_module_path.parents[3]
    return resolved_module_path.parent


PROJECT_ROOT = discover_project_root()
