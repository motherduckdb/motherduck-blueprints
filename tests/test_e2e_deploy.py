"""End-to-end plan, deploy, and verify runs against the fake MotherDuck account."""
from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from e2e_support import FAKE_MOTHERDUCK, FIXTURES, Cli, FakeMotherDuck, edit_yaml, records, write_yaml

BRANCH = "feature/e2e"
PREVIEW_FLIGHT = "wikipedia-pageviews:feature/e2e (Preview)"
PREVIEW_DIVE = "Wikipedia Pageviews:feature/e2e (Preview)"
INGEST = "flights/wikipedia-pageviews-ingest/blueprint.yml"
DASHBOARD = "dives/wikipedia-pageviews/blueprint.yml"


def preview(root: Path, *args: str) -> tuple[str, ...]:
    return ("--root", str(root), "--target", "preview", "--branch", BRANCH, *args)


def flight_target(root: Path, target: str, **values: object) -> None:
    def change(data: dict[str, Any]) -> None:
        data["resources"]["flights"]["pageviews_loader"]["targets"].setdefault(target, {}).update(values)

    edit_yaml(root / INGEST, change)


def write_guide(root: Path, name: str, guide: dict[str, object], content: str = "# Runbook\n") -> Path:
    package = root / "guides" / name
    write_yaml(package / "blueprint.yml", {
        "schemaVersion": 1, "name": name, "title": name.title(),
        "resources": {"guides": {"guide": {"source": "guide.md", **guide}}},
    })
    (package / "guide.md").write_text(content, encoding="utf-8")
    return package


def test_plan_reads_the_account_and_never_writes(starter: Path, md_cli: Cli) -> None:
    text = md_cli.ok("plan", *preview(starter, "--blueprints", "wikipedia-pageviews")).stdout
    assert text.splitlines()[:3] == [
        "#### Deployment Plan",
        "",
        "**Selected:** `wikipedia-pageviews` · **Added by the dependency graph:** `wikipedia-pageviews-ingest`",
    ]
    assert f"| {PREVIEW_FLIGHT} | create |" in text
    assert f"| {PREVIEW_DIVE} | create | no |  | draft |" in text

    plan = records(md_cli.ok("plan", *preview(starter, "--json")))
    assert all(
        set(row) == {"blueprint", "type", "key", "name", "action", "exists", "id", "notes", "current_status",
                     "desired_status"}
        for row in plan.values()
    )
    assert {key: row["action"] for key, row in plan.items()} == {
        ("wikipedia-pageviews-ingest", "flight", "pageviews_loader"): "create",
        ("wikipedia-pageviews-ingest", "share", "pageviews"): "present",
        ("wikipedia-pageviews", "input", "pageviews"): "present",
        ("wikipedia-pageviews", "dive", "pageviews"): "create",
    }
    assert "Selected" not in md_cli.ok("plan", *preview(starter)).stdout
    assert md_cli.fake.queries() and md_cli.fake.mutations() == []


def test_preview_deploy_creates_once_then_updates_the_same_resources(starter: Path, md_cli: Cli) -> None:
    fake = md_cli.fake
    first = md_cli.ok("deploy", *preview(starter, "--blueprints", "wikipedia-pageviews"))
    assert first.stdout.startswith(
        "**Selected:** `wikipedia-pageviews` · **Added by the dependency graph:** `wikipedia-pageviews-ingest`\n"
    )
    assert "#### Wikipedia Pageviews" in first.stdout
    assert re.search(r"<summary>Verified \d+ resources across 2 blueprints</summary>", first.stdout)
    assert first.stdout.rstrip().endswith("</details>")
    flight_id = fake.ids("flights")[PREVIEW_FLIGHT]
    dive_id = fake.ids("dives")[PREVIEW_DIVE]
    assert fake.state()["dives"][dive_id]["status"] == "draft"
    run = next(query for query in fake.queries() if "MD_RUN_FLIGHT" in query)
    assert 'MD_RUN_FLIGHT("config" => map(' in run and f"\"flight_id\" => '{flight_id}'::UUID" in run
    # A new preview Dive is created as a draft, and unsized Flights skip the DuckDB version check.
    assert not any("MD_UPDATE_DIVE_STATUS" in query or "pragma_version" in query for query in fake.queries())

    plans = [records(md_cli.ok("plan", *preview(starter, "--json"))) for _ in range(2)]
    assert plans[0] == plans[1]
    flight = plans[0][("wikipedia-pageviews-ingest", "flight", "pageviews_loader")]
    dive = plans[0][("wikipedia-pageviews", "dive", "pageviews")]
    assert (flight["action"], flight["id"], dive["action"], dive["id"]) == ("update", flight_id, "update", dive_id)
    assert not any("bind it with `id`" in row["notes"] for row in plans[0].values())

    fake.clear_log()
    second = md_cli.ok("deploy", *preview(starter, "--blueprints", "wikipedia-pageviews"))
    assert fake.ids("flights") == {PREVIEW_FLIGHT: flight_id}
    assert fake.ids("dives") == {PREVIEW_DIVE: dive_id}
    assert not any("MD_CREATE_" in query for query in fake.queries())
    # The preview Flight was created unscheduled, so clearing its schedule fails and is retried without it.
    updates = [query for query in fake.queries() if "MD_UPDATE_FLIGHT" in query]
    assert len(updates) == 2
    assert "\"schedule_cron\" => ''" in updates[0] and "schedule_cron" not in updates[1]
    assert f"Updating existing flight '{PREVIEW_FLIGHT}' ({flight_id})" in second.stderr
    assert any("MD_LIST_FLIGHT_RUNS" in query for query in fake.queries())

    flight_target(starter, "preview", waitForRun=False)
    fake.clear_log()
    md_cli.ok("deploy", *preview(starter))
    assert any("MD_RUN_FLIGHT" in query for query in fake.queries())
    assert not any("MD_LIST_FLIGHT_RUNS" in query for query in fake.queries())


def test_production_deploy_applies_declared_status_and_verify_is_read_only(starter: Path, md_cli: Cli) -> None:
    fake = md_cli.fake
    output = md_cli.ok("deploy", "--root", str(starter)).stdout
    assert output.startswith("#### Deployment Verification\n")
    flight_id = fake.ids("flights")["wikipedia-pageviews"]
    dive_id = fake.ids("dives")["Wikipedia Pageviews"]
    assert fake.state()["flights"][flight_id]["schedule"] == "17 6 * * *"
    assert fake.state()["dives"][dive_id]["status"] == "ready"
    assert any("MD_UPDATE_DIVE_STATUS" in query and "'ready'" in query for query in fake.queries())
    assert not any("access_token_name" in query for query in fake.queries())

    plan = records(md_cli.ok("plan", "--root", str(starter), "--json"))
    for key in (("wikipedia-pageviews-ingest", "flight", "pageviews_loader"), ("wikipedia-pageviews", "dive", "pageviews")):
        assert "by name; bind it with `id`" in plan[key]["notes"]

    fake.clear_log()
    verified = md_cli.ok("verify", "--root", str(starter))
    assert verified.stdout.startswith("#### Live Verification\n")
    assert {row["action"] for row in md_cli.ok("verify", "--root", str(starter), "--json").json()} == {"verified"}
    assert fake.queries() and fake.mutations() == []


def test_postcheck_failure_fails_the_deploy_and_opt_out_skips_only_the_postcheck(
    starter: Path, md_cli: Cli,
) -> None:
    fake = md_cli.fake
    # The account accepts the status change but never applies it.
    fake.seed(ignore_dive_status=True)
    failed = md_cli.fails("deploy", "--root", str(starter))
    assert "Deployment applied, but verification failed" in failed.stderr
    assert "wikipedia-pageviews.pageviews status is draft, expected ready" in failed.stderr
    assert "No rollback was attempted" in failed.stderr
    assert any("MD_CREATE_DIVE" in query for query in fake.mutations())

    fake.clear_log()
    assert "status is draft, expected ready" in md_cli.fails("verify", "--root", str(starter)).stderr
    assert fake.mutations() == []

    skipped = md_cli.ok("deploy", "--root", str(starter), "--skip-verification")
    assert "Deployment Verification" not in skipped.stdout


def _duplicate_flights(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    return ["--target", "preview", "--branch", "feature/mock-test"], {"MOCK_DUPLICATE_FLIGHTS": "true"}, [
        "duplicate Flight name; expected 0 or 1",
    ]


def _missing_admin(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    write_guide(root, "handbook", {"title": "Handbook", "deploy": True, "access": "organization"})
    write_yaml(root / "roles/analysts/blueprint.yml", {
        "schemaVersion": 1, "name": "analysts", "title": "Analysts",
        "resources": {"roles": {"team": {"name": "analysts", "deploy": True}}},
    })
    fake.seed(user_roles=["builder"])
    return [], {}, [
        "requires the admin role (analysts manages roles; handbook publishes organization Guides)",
        "the deployment identity has: builder",
    ]


def _old_duckdb(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    flight_target(root, "prod", instanceType="F16")
    fake.seed(duckdb_version="v1.5.5")
    return [], {}, ["needs DuckDB 1.5.6 or newer, but the duckdb SQL backend runs v1.5.5"]


def _missing_upstream_output(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    return ["--blueprints", "wikipedia-pageviews"], {"MOCK_SHARE_MISSING": "true"}, [
        "deploy producer 'wikipedia-pageviews-ingest' to the same target first",
    ]


def _missing_roles(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    write_yaml(root / "roles/finance-team/blueprint.yml", {
        "schemaVersion": 1, "name": "finance-team", "title": "Finance Team",
        "resources": {"roles": {"team": {"name": "finance-team", "includedRoles": ["missing-parent"], "deploy": True}}},
    })

    def grant(data: dict[str, Any]) -> None:
        data["resources"]["shares"]["pageviews"]["grants"] = {"roles": ["missing-grantee"]}

    edit_yaml(root / INGEST, grant)
    return [], {}, [
        "included role(s) do not exist and are not selected for deployment: missing-parent",
        "grant role(s) do not exist and are not selected for deployment: missing-grantee",
        # MotherDuck refuses hyphens in new role names; plan says so before any write.
        "MotherDuck cannot create role 'finance-team'",
        "rename it, for example to 'finance_team'",
    ]


def _expired_access_token(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    flight_target(root, "prod", accessTokenName="flights")
    fake.seed(access_tokens=[["flights", "expired", "2026-10-01 00:00:00+00"], ["ci", "never", None]])
    return [], {}, ["access token 'flights' expired at 2026-10-01 00:00:00+00"]


def _unknown_access_token(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    flight_target(root, "prod", accessTokenName="flihgts")
    fake.seed(access_tokens=[["flights", "never", None]])
    return [], {}, ["accessTokenName 'flihgts' is not an access token of the deployment identity"]


def _dynamic_dive_mounts(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    source = root / "dives/wikipedia-pageviews/src/dive.tsx"
    text = source.read_text(encoding="utf-8")
    export = next(line for line in text.splitlines() if line.startswith("export const REQUIRED_DATABASES"))
    source.write_text(text.replace(export, "export const REQUIRED_DATABASES = [\n  { alias: ALIAS },\n];"), encoding="utf-8")
    return [], {}, ["REQUIRED_DATABASES must be a static array"]


def _branch_without_slug(root: Path, fake: FakeMotherDuck) -> tuple[list[str], dict[str, str], list[str]]:
    def fixed_preview_share(data: dict[str, Any]) -> None:
        data["resources"]["shares"]["pageviews"]["targets"]["preview"].update(
            name="wikipedia_pageviews_feature_mock_test", database="wikipedia_pageviews_feature_mock_test",
        )

    edit_yaml(root / INGEST, fixed_preview_share)
    return ["--target", "preview", "--branch", "feature/actual"], {}, ["must include branch slug feature_actual"]


@pytest.mark.parametrize("setup", [
    _duplicate_flights, _missing_admin, _old_duckdb, _missing_upstream_output, _missing_roles, _dynamic_dive_mounts,
    _branch_without_slug, _expired_access_token, _unknown_access_token,
])
@pytest.mark.parametrize("verify", ["--verify", "--skip-verification"])
def test_preflight_failures_block_every_write_even_without_the_postcheck(
    starter: Path, md_cli: Cli,
    setup: Callable[[Path, FakeMotherDuck], tuple[list[str], dict[str, str], list[str]]], verify: str,
) -> None:
    args, env, messages = setup(starter, md_cli.fake)
    result = md_cli.fails("deploy", "--root", str(starter), *args, verify, env=env)
    for message in messages:
        assert message in result.stderr
    assert md_cli.fake.mutations() == []
    assert md_cli.fake.state().get("flights", {}) == {}


def test_access_token_that_expires_soon_warns_once_and_deploys(starter: Path, md_cli: Cli) -> None:
    flight_target(starter, "prod", accessTokenName="flights")
    md_cli.fake.seed(access_tokens=[["flights", "soon", "2026-10-20 00:00:00+00"]])
    result = md_cli.ok("deploy", "--root", str(starter))
    assert result.stderr.count("access token 'flights' used by Flight wikipedia-pageviews-ingest.pageviews_loader") == 1
    assert any('"access_token_name" => \'flights\'' in query for query in md_cli.fake.queries())

    # verify is read-only: a token that has since expired does not fail it, while plan stops.
    md_cli.fake.seed(access_tokens=[["flights", "expired", "2026-10-20 00:00:00+00"]])
    md_cli.ok("verify", "--root", str(starter))
    assert "expired at 2026-10-20" in md_cli.fails("plan", "--root", str(starter)).stderr


def test_missing_producer_output_is_pending_only_while_a_selected_flight_will_produce_it(
    tmp_path: Path, starter: Path, md_cli: Cli,
) -> None:
    missing = {"MOCK_SHARE_MISSING": "true"}
    plan = records(md_cli.ok("plan", *preview(starter, "--json", "--blueprints", "wikipedia-pageviews"), env=missing))
    assert plan[("wikipedia-pageviews-ingest", "share", "pageviews")]["action"] == "pending"
    assert plan[("wikipedia-pageviews", "input", "pageviews")]["action"] == "pending"

    flight_target(starter, "preview", runOnDeploy=False)
    plan = records(md_cli.fails("plan", *preview(starter, "--json", "--blueprints", "wikipedia-pageviews"), env=missing))
    for key in (("wikipedia-pageviews-ingest", "share", "pageviews"), ("wikipedia-pageviews", "input", "pageviews")):
        assert plan[key]["action"] == "error" and "runOnDeploy" in plan[key]["notes"]

    summary = tmp_path / "summary.md"
    consumer_only = md_cli.fails(
        "plan", "--root", str(starter), "--blueprints", "wikipedia-pageviews", GITHUB_STEP_SUMMARY=str(summary), env=missing,
    )
    assert "required production output wikipedia-pageviews-ingest.pageviews is not available" in consumer_only.stdout
    assert "deploy producer &#x27;wikipedia-pageviews-ingest&#x27; to the same target first" in summary.read_text()


def test_live_commands_require_the_selected_targets_token(tmp_path: Path, starter: Path, md_cli: Cli) -> None:
    summary = tmp_path / "summary.md"
    missing = md_cli.fails("plan", *preview(starter), token=False, GITHUB_STEP_SUMMARY=str(summary))
    assert "MOTHERDUCK_TOKEN is required to plan target preview" in missing.stderr
    assert "motherduck-production" in summary.read_text() and "Next:" in summary.read_text()
    assert "service-account read/write token" in summary.read_text()
    assert "MOTHERDUCK_TOKEN is required to deploy target prod" in md_cli.fails(
        "deploy", "--root", str(starter), token=False,
    ).stderr
    assert md_cli.fake.queries() == []

    # The simple fixture's preview target reads its token from TARGET_MD_TOKEN.
    simple = ("--root", str(FIXTURES / "simple"), "--target", "preview", "--branch", "feature/token")
    assert "TARGET_MD_TOKEN is required to plan target preview" in md_cli.fails("plan", *simple).stderr
    assert "| Simple Dive:feature/token (Preview) | create |" in md_cli.ok(
        "plan", *simple, token=False, TARGET_MD_TOKEN="target-token",
    ).stdout


def test_native_cli_backend_receives_the_target_token(md_cli: Cli) -> None:
    simple = ("--root", str(FIXTURES / "simple"), "--target", "preview", "--branch", "feature/token")
    path = f"{FAKE_MOTHERDUCK}{os.pathsep}{os.environ['PATH']}"
    result = md_cli.ok(
        "plan", *simple, token=False, TARGET_MD_TOKEN="target-token", MD_BLUEPRINTS_SQL_BACKEND="motherduck", PATH=path,
    )
    assert "| Simple Dive:feature/token (Preview) | create |" in result.stdout
    missing_cli = md_cli.fails("plan", *simple, token=False, TARGET_MD_TOKEN="target-token", MD_BLUEPRINTS_SQL_BACKEND="motherduck",
                               PATH="/usr/bin:/bin")
    assert "make install-deploy" in missing_cli.stderr


def test_dive_status_is_managed_only_when_declared(tmp_path: Path, md_cli: Cli) -> None:
    root = tmp_path / "simple"
    shutil.copytree(FIXTURES / "simple", root)
    fake = md_cli.fake
    assert "| Simple Dive | create | no |  | draft (default) |" in md_cli.ok("plan", "--root", str(root)).stdout

    fake.seed(dives={
        "00000000-0000-0000-0000-000000000501": {"title": "Simple Dive", "status": "endorsed"},
        "00000000-0000-0000-0000-000000000502": {"title": "Simple Dive:feature/status (Preview)", "status": "ready"},
    })
    preview_plan = md_cli.ok(
        "plan", "--root", str(root), "--target", "preview", "--branch", "feature/status", token=False,
        TARGET_MD_TOKEN="target-token",
    )
    assert "| ready -> draft |" in preview_plan.stdout

    md_cli.ok("deploy", "--root", str(root), "--blueprints", "simple-dive")
    assert any("MD_UPDATE_DIVE_CONTENT" in query for query in fake.queries())
    assert not any("MD_UPDATE_DIVE_STATUS" in query for query in fake.queries())
    assert fake.state()["dives"]["00000000-0000-0000-0000-000000000501"]["status"] == "endorsed"

    def endorse(data: dict[str, Any]) -> None:
        data["resources"]["dives"]["example"]["status"] = "endorsed"
        data["resources"]["dives"]["example"]["title"] = "Simple Dive v2"

    edit_yaml(root / "blueprints/simple-dive/blueprint.yml", endorse)
    plan = records(md_cli.ok("plan", "--root", str(root), "--json"))
    assert plan[("simple-dive", "dive", "example")]["notes"] == "endorsing requires an organization admin"
    md_cli.ok("deploy", "--root", str(root))
    created = fake.ids("dives")["Simple Dive v2"]
    assert fake.state()["dives"][created]["status"] == "endorsed"


def test_flight_runtime_and_instance_size_reach_motherduck(starter: Path, md_cli: Cli) -> None:
    fake = md_cli.fake
    fake.seed(duckdb_version="v1.6.0")
    flight_target(starter, "prod", maxRuntimeSec=900, instanceType="F32")
    md_cli.ok("deploy", "--root", str(starter))
    create = next(query for query in fake.queries() if "MD_CREATE_FLIGHT" in query)
    assert '"max_runtime_sec" => 900::UINTEGER' in create and "\"instance_type\" => 'F32'" in create
    assert any("pragma_version()" in query for query in fake.queries())

    fake.clear_log()
    md_cli.ok("deploy", "--root", str(starter))
    update = next(query for query in fake.queries() if "MD_UPDATE_FLIGHT" in query)
    assert '"max_runtime_sec" => 900::UINTEGER' in update and "\"instance_type\" => 'F32'" in update

    # A disabled Flight is never sized, so an older runtime does not block the rest of the deploy.
    fake.seed(duckdb_version="v1.5.4")
    fake.clear_log()
    flight_target(starter, "prod", deploy=False)
    md_cli.ok("deploy", "--root", str(starter))
    assert not any("pragma_version()" in query or "MD_UPDATE_FLIGHT" in query for query in fake.queries())


def test_roles_and_share_grants_reconcile_with_authoritative_revocations(starter: Path, md_cli: Cli) -> None:
    fake = md_cli.fake
    write_yaml(starter / "roles/finance-team/blueprint.yml", {
        "schemaVersion": 1, "name": "finance-team", "title": "Finance Team",
        "resources": {"roles": {"team": {
            "name": "finance_team", "includedRoles": ["explorer"], "members": ["new@example.com"],
            "mode": "authoritative", "deploy": True,
        }}},
    })
    write_yaml(starter / "roles/senior-analysts/blueprint.yml", {
        "schemaVersion": 1, "name": "senior-analysts", "title": "Senior Analysts",
        "resources": {"roles": {"team": {
            "name": "senior_analysts", "includedRoles": ["finance_team"], "mode": "authoritative", "deploy": True,
        }}},
    })

    def manage_share(data: dict[str, Any]) -> None:
        data["resources"]["shares"]["pageviews"].update(
            includePattern=["reporting.*"], grants={"roles": ["finance_team"], "mode": "authoritative"},
        )

    edit_yaml(starter / INGEST, manage_share)
    fake.seed(
        current_user='ci "bot"',
        roles={"explorer": {}, "legacy": {}, "finance_team": {"included": ["legacy"], "users": ["old@example.com"]}},
        share_grantees={"wikipedia_pageviews": [["terraform-role", "role"], ["ops@example.com", "user"]]},
    )

    plan_result = md_cli.ok("plan", "--root", str(starter), "--json")
    plan = records(plan_result)
    # Member names are checked against GET /v1/users; when that cannot be read, planning continues.
    assert "could not list organization users" in plan_result.stderr
    assert 'SHOW ROLES TO USER "ci ""bot"""' in fake.queries()
    role = plan[("finance-team", "role", "team")]
    assert role["action"] == "update" and "will revoke: role legacy, user old@example.com" in role["notes"]
    assert "nothing to revoke today (new role)" in plan[("senior-analysts", "role", "team")]["notes"]
    share = plan[("wikipedia-pageviews-ingest", "share", "pageviews")]
    assert share["action"] == "update"
    assert "include pattern changes from unfiltered to [reporting.*]" in share["notes"]
    assert "will grant: role finance_team" in share["notes"]
    assert "including grants created outside Blueprints (for example by Terraform" in share["notes"]
    assert "will revoke: role terraform-role, user ops@example.com" in share["notes"]

    fake.clear_log()
    md_cli.ok("deploy", "--root", str(starter))
    queries = fake.queries()
    expected = [
        'CREATE ROLE IF NOT EXISTS "finance_team";',
        'GRANT ROLE "explorer" TO ROLE "finance_team";',
        'GRANT ROLE "finance_team" TO USER "new@example.com";',
        'REVOKE ROLE "legacy" FROM ROLE "finance_team";',
        'REVOKE ROLE "finance_team" FROM USER "old@example.com";',
        'CREATE ROLE IF NOT EXISTS "senior_analysts";',
        'GRANT ROLE "finance_team" TO ROLE "senior_analysts";',
    ]
    assert [query for query in queries if query in expected] == expected
    assert queries.index(expected[-1]) < next(i for i, query in enumerate(queries) if "MD_CREATE_FLIGHT" in query)
    for statement in (
        "ALTER SHARE \"wikipedia_pageviews\" SET INCLUDE_PATTERN 'reporting.*';",
        'GRANT READ ON SHARE "wikipedia_pageviews" TO ROLE "finance_team";',
        'REVOKE READ ON SHARE "wikipedia_pageviews" FROM ROLE "terraform-role";',
        'REVOKE READ ON SHARE "wikipedia_pageviews" FROM USER "ops@example.com";',
    ):
        assert statement in queries
    assert fake.state()["share_grantees"]["wikipedia_pageviews"] == [["finance_team", "role"]]

    # A share that already matches plans as present and is not altered again.
    share = records(md_cli.ok("plan", "--root", str(starter), "--json"))[("wikipedia-pageviews-ingest", "share", "pageviews")]
    assert share["action"] == "present" and "include pattern and grants already match" in share["notes"]
    fake.clear_log()
    md_cli.ok("deploy", "--root", str(starter))
    assert not any(query.startswith("ALTER SHARE") or "ON SHARE" in query for query in fake.queries())

    def reset_filter(data: dict[str, Any]) -> None:
        data["resources"]["shares"]["pageviews"]["includePattern"] = None

    edit_yaml(starter / INGEST, reset_filter)
    fake.seed(failures={"SHOW ROLES TO ROLE": "permission denied"})
    note = records(md_cli.ok("plan", "--root", str(starter), "--json"))[("finance-team", "role", "team")]["notes"]
    assert "current grants could not be read at plan time" in note
    fake.seed(failures={})
    fake.clear_log()
    md_cli.ok("deploy", "--root", str(starter))
    assert 'ALTER SHARE "wikipedia_pageviews" RESET INCLUDE_PATTERN;' in fake.queries()


def test_guides_publish_once_and_append_versions_only_for_changes(starter: Path, md_cli: Cli) -> None:
    fake = md_cli.fake
    package = write_guide(starter, "runbook", {
        "title": "Runbook", "topic": "operations", "deploy": True, "access": "organization",
        "description": "Read before paging the on-call engineer.",
    })
    deploy = ("deploy", "--root", str(starter), "--blueprints", "runbook")
    md_cli.ok(*deploy)
    create = next(query for query in fake.queries() if "MD_CREATE_GUIDE" in query)
    assert "\"access\" := 'organization'" in create and "\"topic\" := 'operations'" in create
    guide_id = fake.ids("guides")["Runbook"]
    assert fake.state()["guides"][guide_id]["content"] == "# Runbook\n"

    plan = records(md_cli.ok("plan", "--root", str(starter), "--blueprints", "runbook", "--json"))
    assert (plan[("runbook", "guide", "guide")]["action"], plan[("runbook", "guide", "guide")]["id"]) == ("update", guide_id)
    assert "matched existing Guide 'Runbook' by name" in plan[("runbook", "guide", "guide")]["notes"]

    def guide_writes() -> list[str]:
        return [query for query in fake.mutations() if "GUIDE" in query]

    fake.clear_log()
    md_cli.ok(*deploy)
    assert guide_writes() == []

    (package / "guide.md").write_text("# Runbook\n\nPage the on-call engineer.\n", encoding="utf-8")
    fake.clear_log()
    md_cli.ok(*deploy, GITHUB_SHA="abc123")
    [update] = guide_writes()
    assert 'FROM MD_UPDATE_GUIDE("id" :=' in update and "'abc123'" in update
    assert "MD_UPDATE_GUIDE_METADATA" not in update and "MD_SET_GUIDE_ACCESS" not in update
    assert fake.state()["guides"][guide_id]["content"].endswith("Page the on-call engineer.\n")

    def describe(data: dict[str, Any]) -> None:
        data["resources"]["guides"]["guide"].update(description="Read during incidents.", access="user")

    edit_yaml(package / "blueprint.yml", describe)
    fake.clear_log()
    md_cli.ok(*deploy, GITHUB_SHA="abc123")
    [update] = guide_writes()
    assert "MD_UPDATE_GUIDE(" not in update
    assert "MD_UPDATE_GUIDE_METADATA" in update and "\"description\" := 'Read during incidents.'" in update
    assert "\"access\" := 'user'" in update
    assert fake.ids("guides") == {"Runbook": guide_id}


def test_multi_line_mount_export_is_removed_before_upload(starter: Path, md_cli: Cli) -> None:
    source = starter / "dives/wikipedia-pageviews/src/dive.tsx"
    text = source.read_text(encoding="utf-8")
    export = next(line for line in text.splitlines() if line.startswith("export const REQUIRED_DATABASES"))
    source.write_text(text.replace(export, (
        "export const REQUIRED_DATABASES: Array<{ alias: string; shareName: string }> = [\n"
        "  // mounted for local preview only\n"
        '  { alias: "wikipedia_pageviews", shareName: "wikipedia_pageviews" },\n'
        "];"
    )), encoding="utf-8")
    md_cli.ok("deploy", *preview(starter))
    create = next(query for query in md_cli.fake.queries() if "MD_CREATE_DIVE" in query)
    assert "REQUIRED_DATABASES" not in create and "mounted for local preview" not in create
    assert "useSQLQuery" in create
