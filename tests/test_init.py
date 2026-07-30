from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from md_blueprints import __version__
from md_blueprints.init import action_major_tag, run_init
from md_blueprints.project import Project
from md_blueprints.schema import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
MIRRORED_TEMPLATE_PATHS = [
    "motherduck.yml",
    "flights",
    "dives",
    "guides",
    "roles",
    "projects",
    "shared",
    "schemas/v1",
    ".dive-preview",
    "templates/blueprint",
    "docs",
]


def test_init_writes_customer_template_with_stamped_versions(tmp_path: Path) -> None:
    target = tmp_path / "customer-blueprints"

    run_init(target)

    assert (target / "motherduck.yml").is_file()
    assert (target / "flights/wikipedia-pageviews-ingest/blueprint.yml").is_file()
    assert (target / "dives/wikipedia-pageviews/blueprint.yml").is_file()
    assert (target / ".github/workflows/deploy_blueprints.yaml").is_file()
    assert (target / ".github/workflows/cleanup_preview_blueprints.yaml").is_file()
    assert (target / ".github/dependabot.yml").is_file()
    assert (target / ".dive-preview/.env.example").is_file()
    assert (target / "guides/README.md").is_file()
    assert (target / "roles/README.md").is_file()
    assert (target / "shared/README.md").is_file()
    assert not (target / "src").exists()
    assert not (target / "pyproject.toml").exists()
    assert not (target / "CHANGELOG.md").exists()
    assert not (target / ".github/workflows/ci.yaml").exists()
    assert not (target / ".github/workflows/release.yaml").exists()
    assert not (target / ".dive-preview/src/dive.tsx").exists()

    makefile = (target / "Makefile").read_text(encoding="utf-8")
    deploy_workflow = (target / ".github/workflows/deploy_blueprints.yaml").read_text(encoding="utf-8")
    cleanup_workflow = (target / ".github/workflows/cleanup_preview_blueprints.yaml").read_text(encoding="utf-8")
    readme = (target / "README.md").read_text(encoding="utf-8")
    requirements = (target / "flights/wikipedia-pageviews-ingest/src/requirements.txt").read_text(encoding="utf-8")

    assert f"CLI_VERSION := {__version__}" in makefile
    assert "CLI_SOURCE := git+https://github.com/motherduckdb/motherduck-blueprints.git@v$(CLI_VERSION)" in makefile
    assert 'installed_version="$$( [ -x "$(CLI)" ] && "$(CLI)" --version' in makefile
    assert 'if [ "$$installed_version" != "$(CLI_VERSION)" ]; then' in makefile
    assert '.venv/bin/python -m pip install "md-blueprints @ $(CLI_SOURCE)"' in makefile
    assert "install-deploy: $(CLI)" in makefile
    assert '.venv/bin/python -m pip install "md-blueprints[deploy] @ $(CLI_SOURCE)"' in makefile
    assert f"motherduckdb/motherduck-blueprints@{action_major_tag()}" in deploy_workflow
    assert '"guides/**"' in deploy_workflow
    assert '"roles/**"' in deploy_workflow
    assert f"motherduckdb/motherduck-blueprints@{action_major_tag()}" in cleanup_workflow
    assert "github.event.pull_request.head.sha" in cleanup_workflow
    assert "github.event.pull_request.base.sha" in cleanup_workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in cleanup_workflow
    assert "pytz>=2024.1" in requirements
    assert "__MD_BLUEPRINTS_" not in readme
    assert "mock-test" not in makefile
    assert "package-smoke" not in makefile

    Project(target).validate()


def test_deploy_workflow_watches_all_deployable_roots() -> None:
    workflow = (REPO_ROOT / ".github/workflows/deploy_blueprints.yaml").read_text(encoding="utf-8")

    for root in ["flights", "dives", "guides", "roles", "projects"]:
        assert f'"{root}/**"' in workflow


def test_ci_runs_for_all_main_and_pull_request_changes() -> None:
    workflow = (REPO_ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")

    assert "paths:" not in workflow


def test_doctor_workflows_close_resolved_upgrade_issues() -> None:
    for workflow in [
        REPO_ROOT / ".github/workflows/blueprints_doctor.yaml",
        REPO_ROOT / "src/md_blueprints/template_repo/.github/workflows/blueprints_doctor.yaml",
    ]:
        text = workflow.read_text(encoding="utf-8")
        assert "DOCTOR_OUTCOME" in text
        assert "state: 'all'" in text
        assert "state_reason: 'completed'" in text


def test_init_refuses_non_empty_directory_without_force(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "README.md").write_text("existing\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="is not empty"):
        run_init(target)


def test_init_force_overwrites_template_files(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "README.md").write_text("existing\n", encoding="utf-8")

    run_init(target, force=True)

    assert "MotherDuck Blueprints" in (target / "README.md").read_text(encoding="utf-8")


def test_init_force_refuses_symlink_that_escapes_target(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    outside = tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    (target / "docs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValidationError, match="outside"):
        run_init(target, force=True)

    assert list(outside.iterdir()) == []


def test_init_template_does_not_drift_from_mirrored_repo_paths(tmp_path: Path) -> None:
    target = tmp_path / "customer-blueprints"

    run_init(target)

    source_files = set(repository_files(MIRRORED_TEMPLATE_PATHS))
    generated_files = set(files_under(target, MIRRORED_TEMPLATE_PATHS))
    assert generated_files == source_files

    drifted = [
        path
        for path in sorted(source_files)
        if (target / path).read_bytes() != (REPO_ROOT / path).read_bytes()
    ]
    assert drifted == []


def repository_files(paths: list[str]) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *paths],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [Path(line) for line in result.stdout.splitlines() if (REPO_ROOT / line).is_file()]


def files_under(root: Path, paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for relative in paths:
        candidate = root / relative
        if candidate.is_file():
            files.append(Path(relative))
            continue
        files.extend(path.relative_to(root) for path in candidate.rglob("*") if path.is_file())
    return sorted(files)
