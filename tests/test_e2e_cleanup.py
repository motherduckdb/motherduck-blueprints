"""End-to-end preview cleanup against the fake MotherDuck account, including its safety refusals."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from md_blueprints.project import branch_slug, legacy_branch_slug
from e2e_support import Cli, edit_yaml, write_yaml

INGEST = "flights/wikipedia-pageviews-ingest/blueprint.yml"


def share(branch: str) -> str:
    return f"wikipedia_pageviews_preview_{branch_slug(branch)}"


def cleanup(root: Path, branch: str, *args: str) -> tuple[str, ...]:
    return ("cleanup", "--root", str(root), "--branch", branch, *args)


def test_cleanup_removes_only_this_branchs_preview_consumers_first(starter: Path, md_cli: Cli) -> None:
    fake = md_cli.fake
    fake.seed(
        shares={share(branch): f"md:_share/{branch_slug(branch)}/1" for branch in ("feature/a", "feature/b")},
        databases=[share("feature/a"), share("feature/b")],
    )
    for branch in ("feature/a", "feature/b"):
        md_cli.ok("deploy", "--root", str(starter), "--target", "preview", "--branch", branch)
    flight_a = fake.ids("flights")["wikipedia-pageviews:feature/a (Preview)"]
    fake.clear_log()

    dry_run = md_cli.ok(*cleanup(starter, "feature/a", "--dry-run")).stdout
    assert dry_run.startswith("#### Cleanup Plan\n")
    plan = md_cli.ok(*cleanup(starter, "feature/a", "--dry-run", "--json")).json()
    assert [(row["type"], row["action"], row["name"]) for row in plan] == [
        ("dive", "delete", "Wikipedia Pageviews:feature/a (Preview)"),
        ("flight", "delete", "wikipedia-pageviews:feature/a (Preview)"),
        ("share", "drop_share", share("feature/a")),
        ("database", "drop_database", share("feature/a")),
    ]
    assert fake.mutations() == []
    assert md_cli.fails(*cleanup(starter, "feature/a", "--json"), code=2).stderr.startswith(
        "Error: cleanup --json requires --dry-run"
    )

    lines = md_cli.ok(*cleanup(starter, "feature/a")).stdout.splitlines()
    assert [line.split(" ", 2)[:2] for line in lines] == [
        ["Deleting", "preview"], ["Deleting", "preview"], ["Dropping", "preview"], ["Dropping", "preview"],
    ]
    assert lines[0].startswith("Deleting preview Dive") and lines[1].startswith("Deleting preview Flight")
    assert lines[2:] == [f"Dropping preview share {share('feature/a')}", f"Dropping preview database {share('feature/a')}"]
    assert f"FROM MD_DELETE_FLIGHT(\"flight_id\" => '{flight_a}'::UUID);" in fake.queries()
    assert set(fake.ids("flights")) == {"wikipedia-pageviews:feature/b (Preview)"}
    assert set(fake.ids("dives")) == {"Wikipedia Pageviews:feature/b (Preview)"}
    assert fake.state()["shares"] == {share("feature/b"): "md:_share/feature_b/1"}
    assert fake.state()["databases"] == [share("feature/b")]

    again = md_cli.ok(*cleanup(starter, "feature/a")).stdout
    assert "No preview Dive found" in again and "No preview Flight found" in again
    assert "No preview share found" in again


def test_cleanup_tolerates_a_concurrent_cleanup_but_reports_other_errors(starter: Path, md_cli: Cli) -> None:
    fake = md_cli.fake
    preview = ("--root", str(starter), "--target", "preview", "--branch", "feature/race")
    md_cli.ok("deploy", *preview)
    fake.seed(failures={"MD_DROP_DATABASE_SHARE": 'Catalog Error: Share with name "x" does not exist!'})
    raced = md_cli.ok(*cleanup(starter, "feature/race"))
    assert f"Skipping preview share {share('feature/race')}; it was already removed by another cleanup run" in raced.stdout

    md_cli.ok("deploy", *preview)
    fake.seed(failures={"MD_DELETE_FLIGHT": "permission denied"})
    assert "permission denied" in md_cli.fails(*cleanup(starter, "feature/race")).stderr


def test_cleanup_policy_and_target_are_checked_before_reading_the_account(starter: Path, md_cli: Cli) -> None:
    assert "cleanup is only supported for preview target" in md_cli.fails(
        *cleanup(starter, "feature/a", "--target", "prod"),
    ).stderr

    def disable(data: dict[str, Any]) -> None:
        data["targets"]["preview"]["policies"]["cleanup"] = False

    edit_yaml(starter / "motherduck.yml", disable)
    assert "cleanup is disabled by the preview target policy" in md_cli.fails(*cleanup(starter, "feature/a")).stderr
    assert md_cli.fake.queries() == []


def write_fixed_name_project(root: Path) -> None:
    write_yaml(root / "motherduck.yml", {
        "schemaVersion": 1, "repository": {"name": "fixed"}, "include": ["projects/*/blueprint.yml"],
        "targets": {"preview": {"mode": "preview", "policies": {"cleanup": True}}, "prod": {"mode": "production"}},
    })
    write_yaml(root / "projects/events/blueprint.yml", {
        "schemaVersion": 1, "name": "events", "title": "Events",
        "resources": {"shares": {"data": {
            "name": "events", "database": "events",
            "targets": {"preview": {"name": "events_dev", "database": "events_dev", "dropDatabase": True}},
        }}},
    })


def test_cleanup_refuses_preview_names_that_do_not_change_with_the_branch(tmp_path: Path, md_cli: Cli) -> None:
    write_fixed_name_project(tmp_path)
    md_cli.fake.seed(shares={"events_dev": "md:_share/events_dev/1"}, databases=["events_dev"])
    # events_dev contains the branch name "dev", but every other branch's preview uses it too.
    plan = md_cli.fails(*cleanup(tmp_path, "dev", "--dry-run", "--json")).json()
    assert [(row["type"], row["action"]) for row in plan] == [("share", "error")]
    assert "does not change with the branch, so other previews share it: events_dev" in plan[0]["notes"]
    assert "Plan contains errors" in md_cli.fails(*cleanup(tmp_path, "dev")).stderr
    assert md_cli.fake.mutations() == []
    assert md_cli.fake.state()["databases"] == ["events_dev"]


def test_cleanup_refuses_a_preview_that_matches_the_staging_target(starter: Path, md_cli: Cli) -> None:
    def add_staging(data: dict[str, Any]) -> None:
        targets = data["targets"]
        targets["preview"]["environment"] = "motherduck-staging"
        targets["staging"] = {**targets["prod"], "environment": "motherduck-staging"}

    def staging_share_like_a_preview(data: dict[str, Any]) -> None:
        data["resources"]["shares"]["pageviews"]["targets"]["staging"]["name"] = share("staging/x")

    edit_yaml(starter / "motherduck.yml", add_staging)
    edit_yaml(starter / INGEST, staging_share_like_a_preview)
    # Validation already refuses the preview, before cleanup reads or deletes anything.
    result = md_cli.fails(*cleanup(starter, "staging/x"))
    assert f"must not match its staging name: {share('staging/x')}" in result.stderr
    assert md_cli.fake.queries() == []


def write_loader_project(root: Path) -> None:
    write_yaml(root / "motherduck.yml", {
        "schemaVersion": 1, "repository": {"name": "slugs"}, "include": ["flights/*/blueprint.yml"],
        "targets": {
            "preview": {"mode": "preview", "policies": {"cleanup": True, "requireBranchSlugInDataResources": True}},
            "prod": {"mode": "production"},
        },
    })
    package = root / "flights/loader"
    write_yaml(package / "blueprint.yml", {
        "schemaVersion": 1, "name": "loader", "title": "Loader",
        "resources": {
            "shares": {"data": {"name": "data", "database": "data_db", "targets": {"preview": {
                "name": "data_${target.branch_slug}", "database": "data_db_${target.branch_slug}", "dropDatabase": True,
            }}}},
            "flights": {"loader": {
                "name": "loader", "source": "src/flight.py", "requirements": "src/requirements.txt",
                "targets": {"preview": {"name": "loader_${target.branch_slug}"}},
            }},
        },
    })
    (package / "src").mkdir()
    (package / "src/flight.py").write_text("print('ok')\n", encoding="utf-8")
    (package / "src/requirements.txt").write_text("", encoding="utf-8")


def test_cleanup_also_removes_previews_named_with_the_legacy_long_branch_slug(tmp_path: Path, md_cli: Cli) -> None:
    write_loader_project(tmp_path)
    fake = md_cli.fake
    branch = "feature/" + "long-branch-name-" * 4
    new, legacy = branch_slug(branch), legacy_branch_slug(branch)
    assert new != legacy
    fake.seed(
        flights={
            "00000000-0000-0000-0000-000000000601": {"name": f"loader_{new}"},
            "00000000-0000-0000-0000-000000000602": {"name": f"loader_{legacy}"},
            "00000000-0000-0000-0000-000000000603": {"name": "loader"},
        },
        shares={f"data_{legacy}": "md:_share/legacy/1", "data": "md:_share/prod/1"},
        databases=[f"data_db_{legacy}", "data_db"],
    )
    plan = md_cli.ok(*cleanup(tmp_path, branch, "--dry-run", "--json")).json()
    actions = {(row["type"], row["action"], row["name"]) for row in plan}
    assert actions == {
        ("flight", "delete", f"loader_{new}"),
        ("flight", "delete", f"loader_{legacy}"),
        ("share", "missing", f"data_{new}"),
        ("database", "drop_database", f"data_db_{new}"),
        ("share", "drop_share", f"data_{legacy}"),
        ("database", "drop_database", f"data_db_{legacy}"),
    }

    md_cli.ok(*cleanup(tmp_path, branch))
    assert fake.ids("flights") == {"loader": "00000000-0000-0000-0000-000000000603"}
    assert fake.state()["shares"] == {"data": "md:_share/prod/1"}
    assert fake.state()["databases"] == ["data_db"]

    # A short branch slug is never truncated, so there is no legacy pass to run.
    fake.clear_log()
    plan = md_cli.ok(*cleanup(tmp_path, "feature/short", "--dry-run", "--json")).json()
    assert {row["name"] for row in plan} == {"loader_feature_short", "data_feature_short", "data_db_feature_short"}
    assert not any("MD_ALL_DATABASES" in query for query in fake.queries())


def test_preview_guides_scoped_by_topic_are_cleaned_up_without_touching_production(
    starter: Path, md_cli: Cli,
) -> None:
    fake = md_cli.fake
    package = starter / "guides/runbook"
    write_yaml(package / "blueprint.yml", {
        "schemaVersion": 1, "name": "runbook", "title": "Runbook",
        "resources": {"guides": {"guide": {
            "title": "Runbook", "topic": "docs", "source": "guide.md", "deploy": True,
            # The title has no branch slug; the topic scopes the preview to the branch.
            "targets": {"preview": {"title": "Runbook (Preview)", "topic": "docs_${target.branch_slug}"}},
        }}},
    })
    (package / "guide.md").write_text("# Runbook\n", encoding="utf-8")
    production_id = "00000000-0000-0000-0000-000000000701"
    other_branch_id = "00000000-0000-0000-0000-000000000702"
    fake.seed(guides={
        production_id: {"title": "Runbook", "topic": "docs", "content": "# Runbook\n"},
        other_branch_id: {"title": "Runbook (Preview)", "topic": "docs_feature_other", "content": "# Runbook\n"},
    })

    md_cli.ok("deploy", "--root", str(starter), "--target", "preview", "--branch", "feature/docs", "--blueprints", "runbook")
    preview_ids = [guide_id for guide_id, guide in fake.state()["guides"].items() if guide["topic"] == "docs_feature_docs"]
    assert len(preview_ids) == 1

    plan = md_cli.ok(*cleanup(starter, "feature/docs", "--blueprints", "runbook", "--dry-run", "--json")).json()
    assert [(row["type"], row["action"], row["id"]) for row in plan] == [("guide", "delete", preview_ids[0])]
    md_cli.ok(*cleanup(starter, "feature/docs", "--blueprints", "runbook"))
    assert list(fake.state()["guides"]) == [production_id, other_branch_id]
