from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

import pytest

from md_blueprints import __version__
from md_blueprints.init import action_tag, run_init
from md_blueprints.project import Project
from md_blueprints.scaffold import run_new
from md_blueprints.schema import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_TEMPLATE_PATHS = [
    "LICENSE",
    "motherduck.yml",
    "flights",
    "dives",
    "examples",
    "schemas/v1",
    ".dive-preview",
    "docs",
]


def test_optional_example_requires_explicit_activation(tmp_path: Path) -> None:
    run_init(tmp_path)
    assert Project(tmp_path).all_blueprint_names() == ["wikipedia-pageviews-ingest", "wikipedia-pageviews"]
    shutil.copytree(tmp_path / "examples/ncs-field-recovery", tmp_path / "projects/ncs-field-recovery")
    project = Project(tmp_path)
    assert "ncs-field-recovery" in project.all_blueprint_names()
    project.validate()


def test_slim_template_creates_optional_roots_on_demand(tmp_path: Path) -> None:
    run_init(tmp_path)
    for kind in ("guide", "role", "project"):
        run_new(tmp_path, kind, f"new-{kind}")
    assert (tmp_path / "guides/new-guide/guide.md").is_file()
    assert (tmp_path / "roles/new-role/blueprint.yml").is_file()
    assert (tmp_path / "projects/new-project/src/flight.py").is_file()
    assert not (tmp_path / "templates").exists()
    Project(tmp_path).validate()


def test_force_init_does_not_delete_existing_optional_roots(tmp_path: Path) -> None:
    (tmp_path / "guides/custom").mkdir(parents=True)
    customer_file = tmp_path / "guides/custom/notes.md"
    customer_file.write_text("Keep existing customer work.\n")
    run_init(tmp_path, force=True)
    assert customer_file.read_text() == "Keep existing customer work.\n"


def test_init_writes_customer_template_with_stamped_versions(tmp_path: Path) -> None:
    target = tmp_path / "customer-blueprints"

    run_init(target)

    assert (target / "motherduck.yml").is_file()
    assert (target / "LICENSE").is_file()
    assert (target / "flights/wikipedia-pageviews-ingest/blueprint.yml").is_file()
    assert (target / "dives/wikipedia-pageviews/blueprint.yml").is_file()
    assert (target / ".github/workflows/deploy_blueprints.yaml").is_file()
    assert (target / ".github/workflows/cleanup_preview_blueprints.yaml").is_file()
    assert (target / ".github/dependabot.yml").is_file()
    assert (target / ".dive-preview/.env.example").is_file()
    assert (target / "AGENTS.md").is_file()
    for unused in ["guides", "roles", "projects", "shared", "templates"]:
        assert not (target / unused).exists()
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
    assert "PYTHON ?= python3" in makefile
    assert "$(PYTHON) -m venv .venv" in makefile
    assert "CLI_SOURCE := git+https://github.com/motherduckdb/motherduck-blueprints.git@v$(CLI_VERSION)" in makefile
    assert 'installed_version="$$( [ -x "$(CLI)" ] && "$(CLI)" --version' in makefile
    assert 'if [ "$$installed_version" != "$(CLI_VERSION)" ]; then' in makefile
    assert '.venv/bin/python -m pip install "md-blueprints @ $(CLI_SOURCE)"' in makefile
    assert "install-deploy: $(CLI)" in makefile
    assert "$(CLI) install-cli" in makefile
    assert "md-blueprints-environment-model: v1" in deploy_workflow
    assert f"/.github/workflows/reusable_deploy_blueprints.yaml@{action_tag()}" in deploy_workflow
    assert f"/.github/workflows/reusable_cleanup_preview_blueprints.yaml@{action_tag()}" in cleanup_workflow
    deploy_workflow = (REPO_ROOT / ".github/workflows/reusable_deploy_blueprints.yaml").read_text()
    cleanup_workflow = (REPO_ROOT / ".github/workflows/reusable_cleanup_preview_blueprints.yaml").read_text()
    assert "targets.staging" in deploy_workflow
    assert "github.event_name == 'release'" in deploy_workflow
    assert "environment: ${{ needs.compute_changes.outputs.target_environment }}" in deploy_workflow
    assert "Release tag $RELEASE_TAG does not point to a commit" in deploy_workflow
    assert 'git", "show", f"origin/{base_ref}:motherduck.yml"' in deploy_workflow
    assert "branch_identity != base_identity" in deploy_workflow
    assert "must use deployment.tokenEnvVar: MOTHERDUCK_TOKEN" in deploy_workflow
    assert f"motherduckdb/motherduck-blueprints@{action_tag()}" in cleanup_workflow
    assert "environment: ${{ needs.resolve-environment.outputs.environment }}" in cleanup_workflow
    assert "github.event.pull_request.head.sha" in cleanup_workflow
    assert "github.event.pull_request.base.sha" in cleanup_workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in cleanup_workflow
    assert "pytz>=2024.1" in requirements
    assert "__MD_BLUEPRINTS_" not in readme
    assert "mock-test" not in makefile
    assert "package-smoke" not in makefile

    manifest = (target / "motherduck.yml").read_text(encoding="utf-8")
    assert "staging:" not in manifest
    assert manifest.count("environment: motherduck-production") == 2

    Project(target).validate()


def test_deploy_workflow_watches_all_deployable_roots() -> None:
    workflow = (REPO_ROOT / ".github/workflows/deploy_blueprints.yaml").read_text(encoding="utf-8")

    for root in ["flights", "dives", "guides", "roles", "projects"]:
        assert f'"{root}/**"' in workflow


def test_deploy_workflow_derives_staging_and_release_behavior_from_manifest() -> None:
    workflow = (REPO_ROOT / ".github/workflows/deploy_blueprints.yaml").read_text(encoding="utf-8")

    assert 'staging_enabled = "staging" in targets' in workflow
    assert 'target = "staging" if staging_enabled else "prod"' in workflow
    assert "deployment_enabled = staging_enabled" in workflow
    assert "target: prod" in workflow


def test_ci_runs_for_all_main_and_pull_request_changes() -> None:
    workflow = (REPO_ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")

    assert "paths:" not in workflow


def test_doctor_workflows_close_resolved_upgrade_issues() -> None:
    for workflow in [
        REPO_ROOT / ".github/workflows/blueprints_doctor.yaml",
        REPO_ROOT / ".github/workflows/reusable_blueprints_doctor.yaml",
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


def test_init_assembles_authoritative_repository_assets(tmp_path: Path) -> None:
    target = tmp_path / "customer-blueprints"

    run_init(target)

    source_files = set(repository_files(SHARED_TEMPLATE_PATHS))
    generated_files = set(files_under(target, SHARED_TEMPLATE_PATHS))
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


def test_asset_manifest_has_only_authoritative_sources() -> None:
    import json

    mapping = json.loads((REPO_ROOT / 'src/md_blueprints/asset-map.json').read_text())
    for destination, source in mapping.items():
        assert (REPO_ROOT / source).is_file(), source
        assert not (REPO_ROOT / 'src/md_blueprints' / destination).is_file(), destination
    assert set(mapping) >= {
        'schemas/v1/blueprint.schema.json',
        'template_repo/schemas/v1/blueprint.schema.json',
        'template_repo/.dive-preview/.env.example',
    }
