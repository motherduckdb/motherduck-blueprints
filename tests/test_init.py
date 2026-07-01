from __future__ import annotations

from pathlib import Path

import pytest

from md_blueprints import __version__
from md_blueprints.init import action_major_tag, run_init
from md_blueprints.project import Project
from md_blueprints.schema import ValidationError


def test_init_writes_customer_template_with_stamped_versions(tmp_path: Path) -> None:
    target = tmp_path / "customer-blueprints"

    run_init(target)

    assert (target / "motherduck.yml").is_file()
    assert (target / "blueprints/wikipedia-pageviews/blueprint.yml").is_file()
    assert (target / ".github/workflows/deploy_blueprints.yaml").is_file()
    assert (target / ".github/workflows/cleanup_preview_blueprints.yaml").is_file()
    assert (target / ".github/dependabot.yml").is_file()
    assert (target / ".dive-preview/.env.example").is_file()
    assert (target / "context/policies/.gitkeep").is_file()
    assert (target / "context/schemas/.gitkeep").is_file()
    assert not (target / "src").exists()
    assert not (target / "pyproject.toml").exists()
    assert not (target / "CHANGELOG.md").exists()
    assert not (target / ".github/workflows/ci.yaml").exists()
    assert not (target / ".github/workflows/release.yaml").exists()
    assert not (target / ".dive-preview/src/dive.tsx").exists()

    makefile = (target / "Makefile").read_text(encoding="utf-8")
    deploy_workflow = (target / ".github/workflows/deploy_blueprints.yaml").read_text(encoding="utf-8")
    readme = (target / "README.md").read_text(encoding="utf-8")
    requirements = (target / "blueprints/wikipedia-pageviews/src/requirements.txt").read_text(encoding="utf-8")

    assert f"CLI_VERSION := {__version__}" in makefile
    assert f"motherduckdb/motherduck-blueprints@{action_major_tag()}" in deploy_workflow
    assert "pytz>=2024.1" in requirements
    assert "__MD_BLUEPRINTS_" not in readme
    assert "mock-test" not in makefile
    assert "package-smoke" not in makefile

    Project(target).validate()


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
