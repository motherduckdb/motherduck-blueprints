"""End-to-end tests for the commands that work on a repository without MotherDuck."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from packaging.version import Version

from md_blueprints import __version__
from e2e_support import FIXTURES, STARTER, Cli, commit_all, edit_yaml, git, snapshot


def test_init_writes_a_valid_repository_and_never_overwrites_customer_files(
    tmp_path: Path, md_cli: Cli,
) -> None:
    root = tmp_path / "customer"
    result = md_cli.ok("init", str(root))
    assert f"CLI version pinned in Makefile: {__version__}" in result.stdout
    for path in ("motherduck.yml", "Makefile", "AGENTS.md", ".github/workflows/deploy_blueprints.yaml"):
        assert (root / path).is_file(), path
    assert md_cli.ok("validate", "--root", str(root)).stdout == "Validation passed for 2 blueprint(s).\n"

    before = snapshot(root)
    refused = md_cli.fails("init", str(root))
    assert "is not empty. Pass --force to add only missing template files" in refused.stderr
    assert snapshot(root) == before

    (root / "README.md").write_text("my readme\n", encoding="utf-8")
    (root / ".gitignore").write_text("secrets/\n", encoding="utf-8")
    (root / "motherduck.yml").unlink()
    forced = md_cli.ok("init", str(root), "--force")
    assert (root / "README.md").read_text(encoding="utf-8") == "my readme\n"
    assert (root / ".gitignore").read_text(encoding="utf-8") == "secrets/\n"
    assert (root / "motherduck.yml").is_file()
    assert "Kept 46 existing file(s) unchanged:" in forced.stdout
    assert "  .gitignore (merge the template's ignore entries into yours manually)" in forced.stdout
    assert "  README.md" in forced.stdout


def test_usage_errors_exit_2_before_any_live_access(starter: Path, md_cli: Cli) -> None:
    assert md_cli.ok("--version").stdout.strip() == __version__
    assert "usage: md-blueprints" in md_cli.fails(code=2).stderr
    assert "unknown command 'valdiate'" in md_cli.fails("valdiate", "--root", str(starter), code=2).stderr

    dry_run = md_cli.fails("deploy", "--root", str(starter), "--dry-run", code=2)
    assert "deploy does not support --dry-run; use `plan` to preview changes" in dry_run.stderr
    assert md_cli.fake.queries() == []


def test_validate_exit_codes_and_errors(tmp_path: Path, starter: Path, md_cli: Cli) -> None:
    md_cli.ok("validate", "--root", str(FIXTURES / "simple"))
    assert "must include branch slug" in md_cli.fails("validate", "--root", str(FIXTURES / "invalid-preview")).stderr
    assert "motherduck.yml" in md_cli.fails("validate", "--root", str(tmp_path / "missing")).stderr
    rendered = md_cli.fails(
        "render", "--root", str(FIXTURES / "invalid-preview"), "--target", "preview", "--branch", "feature/invalid",
    )
    assert "must include branch slug" in rendered.stderr

    def add_unknown_field(data: dict[str, object]) -> None:
        data["refreshWindow"] = "daily"

    edit_yaml(starter / "dives/wikipedia-pageviews/blueprint.yml", add_unknown_field)
    assert "Unknown field 'refreshWindow'" in md_cli.fails("validate", "--root", str(starter)).stderr


def test_scaffolded_packages_validate_and_render_together(starter: Path, md_cli: Cli) -> None:
    root = ("--root", str(starter))
    md_cli.ok("new", "flight", "events-ingest", *root)
    md_cli.ok("new", "dive", "events-dashboard", "--input", "events-ingest.data", *root)
    md_cli.ok("new", "dive", "external-dashboard", "--url", "md:_share/example/id", *root)
    md_cli.ok("new", "guide", "analytics-guide", *root)
    md_cli.ok("new", "role", "analytics-team", *root)
    md_cli.ok("new", "project", "daily-metrics", *root)

    created = [
        "flights/events-ingest/src/flight.py", "dives/events-dashboard/src/dive.tsx",
        "dives/external-dashboard/src/dive.tsx", "guides/analytics-guide/guide.md",
        "roles/analytics-team/blueprint.yml", "projects/daily-metrics/src/dive.tsx",
    ]
    for path in created:
        assert (starter / path).is_file(), path
        assert "__BLUEPRINT_" not in (starter / path).read_text(encoding="utf-8")
    assert (starter / "projects/daily-metrics/README.md").read_text(encoding="utf-8").startswith("# Daily Metrics\n")
    assert md_cli.ok("validate", *root).stdout == "Validation passed for 8 blueprint(s).\n"

    preview = md_cli.ok(
        "render", *root, "--target", "preview", "--branch", "feature/events", "--blueprints", "events-dashboard",
    ).json()
    assert [blueprint["name"] for blueprint in preview] == ["events-ingest", "events-dashboard"]
    assert preview[1]["inputs"]["data"]["name"] == preview[0]["shares"]["data"]["name"]
    assert "feature_events" in preview[0]["shares"]["data"]["name"]
    prod = md_cli.ok("render", *root, "--target", "prod", "--blueprints", "analytics-team").json()
    assert prod[0]["roles"]["role"]["deploy"] is False

    missing_source = md_cli.fails("new", "dive", "dashboard", *root)
    assert "exactly one" in missing_source.stderr
    assert not (starter / "dives/dashboard").exists()


def test_changed_lists_packages_touched_between_real_commits(starter: Path, md_cli: Cli) -> None:
    git(starter, "init", "-q", "-b", "main")
    base = commit_all(starter, "starter")

    def changed(*args: str) -> list[str]:
        return list(md_cli.ok("changed", "--root", str(starter), "--json", *args).json())

    assert changed("--base", base, "--head", "HEAD") == []
    (starter / "dives/wikipedia-pageviews/src/dive.tsx").write_text("export default 1;\n", encoding="utf-8")
    dive_change = commit_all(starter, "edit dive")
    assert changed("--base", base, "--head", dive_change) == ["wikipedia-pageviews"]

    (starter / "docs/notes.md").write_text("Only docs changed.\n", encoding="utf-8")
    docs_change = commit_all(starter, "docs")
    assert changed("--base", dive_change, "--head", docs_change) == []

    (starter / "flights/wikipedia-pageviews-ingest/src/flight.py").write_text("print('x')\n", encoding="utf-8")
    flight_change = commit_all(starter, "edit flight")
    assert changed("--base", docs_change) == ["wikipedia-pageviews-ingest"]

    (starter / "schemas/v1/note.txt").write_text("shared schema change\n", encoding="utf-8")
    schema_change = commit_all(starter, "schemas")
    assert changed("--base", flight_change, "--head", schema_change) == STARTER
    assert changed("--base", "0" * 40) == STARTER
    assert changed("--all") == STARTER
    text = md_cli.ok("changed", "--root", str(starter), "--base", base).stdout
    assert text.splitlines() == ["wikipedia-pageviews-ingest", "wikipedia-pageviews"]


def test_changed_maps_repository_paths_when_motherduck_yml_is_in_a_subdirectory(
    tmp_path: Path, md_cli: Cli,
) -> None:
    repo = tmp_path / "monorepo"
    md_cli.ok("init", str(repo / "analytics"))
    (repo / "other/flights/wikipedia-pageviews-ingest").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    base = commit_all(repo, "starter")

    def changed_after(*paths: str) -> list[str]:
        head = git(repo, "rev-parse", "HEAD")
        for path in paths:
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(target.read_text(encoding="utf-8") + "\n# changed\n" if target.exists() else "new\n")
        commit_all(repo, f"change {paths}")
        return list(md_cli.ok("changed", "--root", str(repo / "analytics"), "--base", head, "--json").json())

    assert changed_after("analytics/flights/wikipedia-pageviews-ingest/blueprint.yml") == ["wikipedia-pageviews-ingest"]
    assert changed_after("analytics/motherduck.yml") == STARTER
    # Workflows live at the repository root even when motherduck.yml does not.
    assert changed_after(".github/workflows/deploy_blueprints.yaml") == STARTER
    assert changed_after("other/flights/wikipedia-pageviews-ingest/blueprint.yml", "motherduck.yml") == []
    assert md_cli.ok("changed", "--root", str(repo / "analytics"), "--base", base, "--json").json() == STARTER


def test_render_scopes_preview_resources_to_the_branch(starter: Path, md_cli: Cli) -> None:
    preview = md_cli.ok(
        "render", "--root", str(starter), "--target", "preview", "--branch", "feature/Render-Test",
        "--blueprints", "wikipedia-pageviews",
    ).json()
    producer, consumer = preview
    assert [producer["name"], consumer["name"]] == STARTER
    share = producer["shares"]["pageviews"]
    assert share["name"] == share["database"] == "wikipedia_pageviews_preview_feature_render_test"
    flight = producer["flights"]["pageviews_loader"]
    assert flight["name"] == "wikipedia-pageviews:feature/Render-Test (Preview)"
    assert flight["scheduleCron"] == ""
    assert consumer["dives"]["pageviews"]["status"] == "draft"

    prod = md_cli.ok("render", "--root", str(starter), "--blueprints", "wikipedia-pageviews-ingest").json()
    assert [blueprint["name"] for blueprint in prod] == STARTER
    assert prod[0]["flights"]["pageviews_loader"]["scheduleCron"] == "17 6 * * *"
    assert prod[1]["dives"]["pageviews"]["status"] == "ready"
    assert md_cli.ok("render", "--root", str(starter), "--blueprints", "wikipedia-pageviews").json()[0]["name"] == (
        "wikipedia-pageviews"
    )


def test_doctor_migrate_and_update_checks_run_offline(tmp_path: Path, starter: Path, md_cli: Cli) -> None:
    root = ("--root", str(starter))
    doctor = md_cli.ok("doctor", *root, "--offline")
    assert "validation: passed" in doctor.stdout
    assert "blueprints discovered: 2" in doctor.stdout
    invalid = md_cli.fails("doctor", "--root", str(FIXTURES / "invalid-preview"), "--offline")
    assert "validation: failed" in invalid.stdout and "validation: passed" not in invalid.stdout
    assert "project manifest: missing" in md_cli.fails("doctor", "--root", str(tmp_path), "--offline").stdout

    ahead = md_cli.ok("doctor", *root, "--check-updates", MD_BLUEPRINTS_LATEST_VERSION="0.0.0")
    assert "version status: ahead of latest release" in ahead.stdout
    assert "latest md-blueprints: 0.0.0" in md_cli.ok("check-updates", MD_BLUEPRINTS_LATEST_VERSION="0.0.0").stdout
    installed = Version(__version__)
    newer = f"{installed.major}.{installed.minor + 1}.0"
    assert f"older than release {newer}" in md_cli.fails("check-updates", MD_BLUEPRINTS_LATEST_VERSION=newer).stderr
    assert "unknown (offline mode)" in md_cli.ok("check-updates", "--offline").stdout

    before = snapshot(starter)
    assert "No migration needed" in md_cli.ok("migrate", *root, "--to", "latest").stdout
    mismatch = md_cli.fails("migrate", *root, "--from", "2")
    assert "--from 2 does not match project schemaVersion set: 1" in mismatch.stderr
    assert snapshot(starter) == before


def test_upgrade_previews_then_moves_every_tooling_pin_together(starter: Path, md_cli: Cli) -> None:
    root = ("--root", str(starter))
    workflow = starter / ".github/workflows/deploy_blueprints.yaml"
    before = snapshot(starter)

    preview = md_cli.ok("upgrade", *root, MD_BLUEPRINTS_LATEST_VERSION="1.2.3")
    assert "+CLI_VERSION := 1.2.3" in preview.stdout
    assert snapshot(starter) == before

    md_cli.ok("upgrade", *root, "--write", MD_BLUEPRINTS_LATEST_VERSION="1.2.3")
    assert "CLI_VERSION := 1.2.3" in (starter / "Makefile").read_text(encoding="utf-8")
    assert "@v1.2.3" in workflow.read_text(encoding="utf-8")
    assert f"@v{__version__}" not in workflow.read_text(encoding="utf-8")
    assert "already aligned" in md_cli.ok("upgrade", *root, "--write", MD_BLUEPRINTS_LATEST_VERSION="1.2.3").stdout
    doctor = md_cli.ok("doctor", *root, "--offline")
    assert f"tooling pins: mismatch (installed {__version__}, Makefile 1.2.3, workflows v1.2.3)" in doctor.stdout

    # "latest" never downgrades a repository pinned ahead of the newest release.
    pinned = snapshot(starter)
    md_cli.ok("upgrade", *root, "--write", MD_BLUEPRINTS_LATEST_VERSION="0.0.1")
    assert snapshot(starter) == pinned
    offline = md_cli.fails("upgrade", *root, "--offline")
    assert "Cannot determine the latest release offline. Pass --to X.Y.Z" in offline.stderr
    md_cli.ok("upgrade", *root, "--offline", "--to", "1.2.4", "--write")
    assert "CLI_VERSION := 1.2.4" in (starter / "Makefile").read_text(encoding="utf-8")


def test_guides_prints_context_without_changing_the_repository(starter: Path, md_cli: Cli) -> None:
    md_cli.ok("new", "guide", "repository-overview", "--root", str(starter))
    before = snapshot(starter)
    for action in ("context", "init", "update"):
        output = md_cli.ok("guides", action, "--root", str(starter)).stdout
        assert "flights/wikipedia-pageviews-ingest/src/flight.py" in output
        assert "guides/repository-overview/guide.md" in output
        assert "No files or live resources were changed" in output
    assert snapshot(starter) == before


@pytest.mark.parametrize("fixture", ["simple", "medium", "complex"])
def test_fixture_repositories_validate(md_cli: Cli, fixture: str) -> None:
    md_cli.ok("validate", "--root", str(FIXTURES / fixture))


def test_validate_reads_a_copied_example_only_once_activated(starter: Path, md_cli: Cli) -> None:
    assert json.loads(md_cli.ok("changed", "--root", str(starter), "--all", "--json").stdout) == STARTER
    shutil.copytree(starter / "examples/ncs-field-recovery", starter / "projects/ncs-field-recovery")
    md_cli.ok("validate", "--root", str(starter))
    assert "ncs-field-recovery" in md_cli.ok("changed", "--root", str(starter), "--all").stdout
    assert yaml.safe_load((starter / "projects/ncs-field-recovery/blueprint.yml").read_text())["name"] == (
        "ncs-field-recovery"
    )
