from pathlib import Path

from src.projectPaths import discover_project_root


def _make_repo_layout(tmp_path: Path) -> Path:
    repo_root = tmp_path / "sailing_insights"
    (repo_root / "backend" / "src" / "api").mkdir(parents=True)
    (repo_root / "backend" / "pyproject.toml").write_text("", encoding="utf-8")
    (repo_root / ".env").write_text("POSTGRES_USER=tester\n", encoding="utf-8")
    return repo_root


def test_discover_project_root_from_backend_source_path(tmp_path: Path) -> None:
    repo_root = _make_repo_layout(tmp_path)
    module_path = repo_root / "backend" / "src" / "api" / "constants.py"

    result = discover_project_root(module_path=module_path, cwd=repo_root)

    assert result == repo_root


def test_discover_project_root_from_site_packages_path_and_repo_cwd(
    tmp_path: Path,
) -> None:
    repo_root = _make_repo_layout(tmp_path)
    module_path = (
        repo_root
        / "backend"
        / ".venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "src"
        / "api"
        / "constants.py"
    )
    module_path.parent.mkdir(parents=True)
    module_path.write_text("", encoding="utf-8")

    result = discover_project_root(module_path=module_path, cwd=repo_root)

    assert result == repo_root


def test_discover_project_root_from_site_packages_path_and_backend_cwd(
    tmp_path: Path,
) -> None:
    repo_root = _make_repo_layout(tmp_path)
    module_path = (
        repo_root
        / "backend"
        / ".venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "src"
        / "api"
        / "constants.py"
    )
    module_path.parent.mkdir(parents=True)
    module_path.write_text("", encoding="utf-8")

    result = discover_project_root(module_path=module_path, cwd=repo_root / "backend")

    assert result == repo_root
