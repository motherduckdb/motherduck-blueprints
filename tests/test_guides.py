from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from md_blueprints.cli import main
from md_blueprints.guides import BEGIN, DIRECTORY, STATE, run_guides
from md_blueprints.init import run_init
from md_blueprints.project import Project
from md_blueprints.scaffold import run_new
from md_blueprints.schema import ValidationError


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_init_generates_valid_private_orientation_and_is_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_init(tmp_path)
    run_guides(tmp_path, "init")
    project = Project(tmp_path)
    assert project.validate()
    for target in project.target_names():
        guide = project.render_all(target, branch="test/guides", names=["repository-overview"])[0].guides["overview"]
        assert guide["deploy"] is False
        assert guide["access"] == "user"
        assert guide["references"] == []
    content = (tmp_path / DIRECTORY / "guide.md").read_text()
    assert "wikipedia-pageviews-ingest.pageviews" in content
    assert "wikipedia_pageviews" in content
    assert "examples/ncs-field-recovery" not in content
    assert "Package: <code>repository-overview</code>" not in content
    before = snapshot(tmp_path)
    run_guides(tmp_path, "init")
    run_guides(tmp_path, "update")
    assert snapshot(tmp_path) == before
    assert "up to date" in capsys.readouterr().out


def test_update_adds_changes_and_removes_packages_preserving_notes_and_settings(tmp_path: Path) -> None:
    run_init(tmp_path)
    run_guides(tmp_path, "init")
    directory = tmp_path / DIRECTORY
    guide_path = directory / "guide.md"
    guide_path.write_text("Owner-reviewed rule: ignore test accounts.\n\n" + guide_path.read_text() + "\nCustom footer.\n")
    manifest_path = directory / "blueprint.yml"
    manifest_path.write_text(manifest_path.read_text().replace("deploy: false", "deploy: true", 1) + "\n# Keep my settings.\n")
    manifest = manifest_path.read_bytes()
    run_new(tmp_path, "flight", "events")
    root_path = tmp_path / "motherduck.yml"
    root = yaml.safe_load(root_path.read_text())
    root["include"] = ["flights/**/blueprint.yml", "guides/**/blueprint.yml"]
    root_path.write_text(yaml.safe_dump(root))
    path = tmp_path / "flights/wikipedia-pageviews-ingest/blueprint.yml"
    path.write_text(path.read_text().replace("Wikipedia Pageviews Ingest", "Updated Pageview Ingest"))
    run_guides(tmp_path, "update")
    content = guide_path.read_text()
    assert content.startswith("Owner-reviewed rule")
    assert content.endswith("Custom footer.\n")
    assert "Package: <code>events</code>" in content
    assert "Updated Pageview Ingest" in content
    assert "dives/wikipedia-pageviews/blueprint.yml" not in content
    assert manifest_path.read_bytes() == manifest
    assert Project(tmp_path).validate()


def test_source_only_change_is_reported_without_inventing_context(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_init(tmp_path)
    run_guides(tmp_path, "init")
    capsys.readouterr()
    path = tmp_path / "flights/wikipedia-pageviews-ingest/src/flight.py"
    path.write_text(path.read_text() + "\n# Newly reviewed behavior\n")
    before = (tmp_path / DIRECTORY / "guide.md").read_bytes()
    run_guides(tmp_path, "update")
    assert "changed: flights/wikipedia-pageviews-ingest/src/flight.py" in capsys.readouterr().out
    assert (tmp_path / DIRECTORY / "guide.md").read_bytes() == before


@pytest.mark.parametrize("action", ["init", "update"])
def test_dry_run_writes_nothing_and_update_can_initialize(tmp_path: Path, action: str) -> None:
    run_init(tmp_path)
    before = snapshot(tmp_path)
    assert main(["guides", action, "--root", str(tmp_path), "--dry-run"]) == 0
    assert snapshot(tmp_path) == before
    assert main(["guides", action, "--root", str(tmp_path)]) == 0
    run_new(tmp_path, "role", "analysts")
    before = snapshot(tmp_path)
    assert main(["guides", "update", "--root", str(tmp_path), "--dry-run"]) == 0
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("edit", ["facts", "markers", "state", "source"])
def test_conflicts_fail_without_writing(tmp_path: Path, edit: str) -> None:
    run_init(tmp_path)
    run_guides(tmp_path, "init")
    path = tmp_path / DIRECTORY / "guide.md"
    if edit == "facts":
        path.write_text(path.read_text().replace("## Repository facts", "## My facts"))
    elif edit == "markers":
        path.write_text(path.read_text().replace(BEGIN, ""))
    elif edit == "state":
        (tmp_path / DIRECTORY / STATE).write_text("[]")
    else:
        (path.parent / "other.md").write_text("Other Guide")
        manifest = path.parent / "blueprint.yml"
        manifest.write_text(manifest.read_text().replace("source: guide.md", "source: other.md"))
    before = snapshot(tmp_path)
    assert main(["guides", "update", "--root", str(tmp_path)]) == 1
    assert snapshot(tmp_path) == before


def test_existing_unmanaged_guide_and_duplicate_slug_are_preserved(tmp_path: Path) -> None:
    run_init(tmp_path)
    run_new(tmp_path, "guide", "repository-overview")
    before = snapshot(tmp_path)
    with pytest.raises(ValidationError, match="not a complete generated Guide"):
        run_guides(tmp_path, "update")
    assert snapshot(tmp_path) == before


def test_custom_include_and_invalid_repository_fail_before_writing(tmp_path: Path) -> None:
    run_init(tmp_path)
    manifest = tmp_path / "motherduck.yml"
    root = yaml.safe_load(manifest.read_text())
    root["include"] = ["flights/**/blueprint.yml", "dives/**/blueprint.yml"]
    manifest.write_text(yaml.safe_dump(root))
    before = snapshot(tmp_path)
    with pytest.raises(ValidationError, match="Add guides"):
        run_guides(tmp_path, "init")
    assert snapshot(tmp_path) == before


def test_symlink_destination_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    run_init(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "guides").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError, match="must stay within"):
        run_guides(root, "init")
    assert list(outside.iterdir()) == []


def test_generation_does_not_copy_flight_config_secrets_or_source(tmp_path: Path) -> None:
    run_init(tmp_path)
    manifest = tmp_path / "flights/wikipedia-pageviews-ingest/blueprint.yml"
    source = yaml.safe_load(manifest.read_text())
    flight = next(iter(source["resources"]["flights"].values()))
    flight["config"]["private_setting"] = "do-not-copy-config"
    flight["secrets"] = ["do-not-copy-secret"]
    manifest.write_text(yaml.safe_dump(source))
    run_guides(tmp_path, "init")
    content = (tmp_path / DIRECTORY / "guide.md").read_text()
    assert "do-not-copy" not in content


@pytest.mark.parametrize("args", [["guides"], ["guides", "delete"], ["guides", "init", "unexpected"], ["guides", "init", "--blueprints", "events"]])
def test_cli_rejects_invalid_guide_requests(args: list[str], tmp_path: Path) -> None:
    assert main([*args, "--root", str(tmp_path)]) == 1
