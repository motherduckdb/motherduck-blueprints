from __future__ import annotations

import copy
from pathlib import Path

import pytest

from md_blueprints.deploy import Deployer, PlanRecord, quote_ident
from md_blueprints.project import CommandError, Project, RenderedBlueprint
from md_blueprints.schema import ValidationError


FIXTURES = Path(__file__).parent / "fixtures"


def test_cleanup_respects_disabled_target_policy() -> None:
    project = Project(FIXTURES / "simple")
    preview = project.target_config("preview")
    policies = preview["policies"]
    assert isinstance(policies, dict)
    policies["cleanup"] = False

    with pytest.raises(ValidationError, match="cleanup is disabled"):
        Deployer(project).cleanup_plan(target="preview", branch="feature/test", names=None)


def test_cleanup_compares_preview_against_staging_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Project(FIXTURES / "simple")
    targets = project.manifest["targets"]
    assert isinstance(targets, dict)
    targets["staging"] = copy.deepcopy(targets["prod"])
    deployer = Deployer(project)
    captured: dict[str, object] = {}

    monkeypatch.setattr(deployer, "_prepare_live_command", lambda target, operation: None)

    def capture_cleanup(
        rendered: list[RenderedBlueprint],
        rendered_branch_slug: str,
        **kwargs: object,
    ) -> list[PlanRecord]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(deployer, "_build_cleanup_plan", capture_cleanup)

    deployer.cleanup_plan(target="preview", branch="feature/test", names=None)

    assert captured["stable_target"] == "staging"


def test_cleanup_plan_refuses_share_without_branch_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: [])
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/prod/123")
    blueprint = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={
            "prod": {
                "name": "prod_share",
                "database": "prod_database",
                "cleanup": True,
                "dropDatabase": True,
            }
        },
        flights={},
        dives={},
        contexts={},
    )

    records = deployer._build_cleanup_plan([blueprint], "feature_branch")

    assert [record.type for record in records] == ["share"]
    assert records[0].action == "error"
    assert "refusing to drop preview share without branch slug feature_branch" in records[0].notes
    with pytest.raises(ValidationError, match="Plan contains errors"):
        deployer.ensure_plan_succeeds(records)


def test_cleanup_plan_refuses_database_without_branch_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: [])
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/preview/123")
    blueprint = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={
            "prod": {
                "name": "safe_feature_branch_share",
                "database": "prod_database",
                "cleanup": True,
                "dropDatabase": True,
            }
        },
        flights={},
        dives={},
        contexts={},
    )

    records = deployer._build_cleanup_plan([blueprint], "feature_branch")

    assert [(record.type, record.action) for record in records] == [
        ("share", "drop_share"),
        ("database", "error"),
    ]
    assert "refusing to drop preview database without branch slug feature_branch" in records[1].notes
    with pytest.raises(ValidationError, match="Plan contains errors"):
        deployer.ensure_plan_succeeds(records)


def test_cleanup_plan_refuses_flight_and_dive_names_that_match_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: pytest.fail("unsafe Dive lookup"))
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: pytest.fail("unsafe Flight lookup"))
    preview = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={},
        flights={"loader": {"name": "production-loader"}},
        dives={"dashboard": {"title": "Production Dashboard"}},
        contexts={},
    )
    production = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={},
        flights={"loader": {"name": "production-loader"}},
        dives={"dashboard": {"title": "Production Dashboard"}},
        contexts={},
    )

    records = deployer._build_cleanup_plan(
        [preview],
        "prod",
        branch="prod",
        production={"ops": production},
    )

    assert [(record.type, record.action) for record in records] == [
        ("dive", "error"),
        ("flight", "error"),
    ]
    assert all("matches production" in record.notes for record in records)
    with pytest.raises(ValidationError, match="Plan contains errors"):
        deployer.ensure_plan_succeeds(records)


def test_cleanup_plan_accepts_validation_only_production_guide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_guide_ids", lambda title, topic: ["guide-id"])
    preview = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={
            "runbook": {
                "title": "Runbook:feature/docs (Preview)",
                "sourcePath": "runbook.md",
                "deploy": True,
            }
        },
    )
    production = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={"runbook": {"sourcePath": "runbook.md", "deploy": False}},
    )

    records = deployer._build_cleanup_plan(
        [preview],
        "feature_docs",
        branch="feature/docs",
        production={"knowledge": production},
    )

    assert [(record.type, record.action) for record in records] == [("guide", "delete")]


def test_deploy_plan_is_idempotent_for_same_live_state(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project(FIXTURES / "complex")
    deployer = Deployer(project)
    rendered = project.render_all("prod")

    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [f"{name}-id"])
    monkeypatch.setattr(deployer, "_list_dive_states", lambda title: [(f"{title}-id", "ready")])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: f"md:_share/{name}/123")

    first = [record.to_dict() for record in deployer._build_deploy_plan(rendered)]
    second = [record.to_dict() for record in deployer._build_deploy_plan(rendered)]

    assert first == second
    assert {record["action"] for record in first if record["type"] in {"flight", "dive"}} == {"update"}
    assert {record["action"] for record in first if record["type"] == "share"} == {"present"}


def test_dive_plan_reports_status_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project(FIXTURES / "simple")
    deployer = Deployer(project)
    blueprint = project.render_all("preview", branch="feature/status")[0]
    monkeypatch.setattr(
        deployer,
        "_list_dive_states",
        lambda title: [("00000000-0000-0000-0000-000000000002", "ready")],
    )

    record = deployer._build_deploy_plan([blueprint])[0]

    assert record.current_status == "ready"
    assert record.desired_status == "draft"
    assert record.formatted_status() == "ready -> draft"


def test_new_unmanaged_dive_plan_reports_motherduck_default(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project(FIXTURES / "simple")
    deployer = Deployer(project)
    blueprint = project.render_all("prod")[0]
    monkeypatch.setattr(deployer, "_list_dive_states", lambda title: [])

    record = deployer._build_deploy_plan([blueprint])[0]

    assert record.formatted_status() == "draft (default)"


def test_dive_deploy_updates_explicit_status(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "simple"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)
    deployer._deploy_dive(
        {
            "title": "Production Dashboard",
            "sourcePath": "src/dive.tsx",
            "description": "",
            "requiredResources": [{"url": "md:_share/example/id", "alias": "example"}],
            "status": "ready",
        },
        {},
        {},
        "prod",
        PlanRecord(
            blueprint="simple-dive",
            type="dive",
            key="example",
            name="Production Dashboard",
            action="update",
            exists=True,
            id="00000000-0000-0000-0000-000000000002",
            current_status="draft",
            desired_status="ready",
        ),
    )

    assert any("MD_UPDATE_DIVE_CONTENT" in call for call in calls)
    assert any("MD_UPDATE_DIVE_STATUS" in call and "'ready'" in call for call in calls)


def test_dive_deploy_preserves_status_when_unmanaged(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "simple"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    deployer._deploy_dive(
        {
            "title": "Production Dashboard",
            "sourcePath": "src/dive.tsx",
            "description": "",
            "requiredResources": [{"url": "md:_share/example/id", "alias": "example"}],
        },
        {},
        {},
        "prod",
        PlanRecord(
            blueprint="simple-dive",
            type="dive",
            key="example",
            name="Production Dashboard",
            action="update",
            exists=True,
            id="00000000-0000-0000-0000-000000000002",
            current_status="endorsed",
            desired_status=None,
        ),
    )

    assert not any("MD_UPDATE_DIVE_STATUS" in call for call in calls)


def test_flight_update_retries_without_schedule_when_existing_flight_is_unscheduled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        if "MD_UPDATE_FLIGHT" in statement and '"schedule_cron"' in statement:
            raise CommandError("MotherDuck SQL failed: Invalid Input Error: Cannot clear schedule: Flight has no schedule")
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    row = deployer._deploy_flight(
        {
            "name": "preview-loader",
            "sourcePath": "src/flight.py",
            "requirementsPath": "src/requirements.txt",
            "scheduleCron": "",
            "runOnDeploy": False,
        },
        "preview",
        PlanRecord(
            blueprint="ops",
            type="flight",
            key="loader",
            name="preview-loader",
            action="update",
            exists=True,
            id="1a4ea2e6-0997-43ea-afe9-78c15c62220e",
        ),
    )

    assert row == "| preview-loader | 1a4ea2e6-0997-43ea-afe9-78c15c62220e | false |"
    assert len(calls) == 2
    assert '"schedule_cron"' in calls[0]
    assert '"schedule_cron"' not in calls[1]


@pytest.mark.parametrize("wait_for_run", [False, "success"])
def test_flight_run_uses_named_motherduck_arguments(
    monkeypatch: pytest.MonkeyPatch, wait_for_run: bool | str,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    waited: list[tuple[str, int]] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return "42" if "MD_RUN_FLIGHT" in statement else ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(
        deployer,
        "_wait_for_flight_run_success",
        lambda fid, number, **kwargs: waited.append((fid, number)),
    )

    deployer._deploy_flight(
        {
            "name": "preview-loader",
            "sourcePath": "src/flight.py",
            "requirementsPath": "src/requirements.txt",
            "scheduleCron": "",
            "runOnDeploy": True,
            "waitForRun": wait_for_run,
            "config": {"article": "DuckDB"},
        },
        "preview",
        PlanRecord(
            blueprint="ops",
            type="flight",
            key="loader",
            name="preview-loader",
            action="update",
            exists=True,
            id="1a4ea2e6-0997-43ea-afe9-78c15c62220e",
        ),
    )

    run_call = next(call for call in calls if "MD_RUN_FLIGHT" in call)
    assert 'MD_RUN_FLIGHT("config" => map(' in run_call
    assert '"flight_id" => \'1a4ea2e6-0997-43ea-afe9-78c15c62220e\'::UUID' in run_call


    assert waited == ([("1a4ea2e6-0997-43ea-afe9-78c15c62220e", 42)] if wait_for_run else [])


def test_flight_deploy_passes_max_runtime_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", fake_sql)

    deployer._deploy_flight(
        {
            "name": "bounded-flight",
            "sourcePath": "src/flight.py",
            "requirementsPath": "src/requirements.txt",
            "scheduleCron": "",
            "maxRuntimeSec": 900,
        },
        "prod",
        PlanRecord("ops", "flight", "loader", "bounded-flight", "update", True, "flight-id"),
    )

    update = next(call for call in calls if "MD_UPDATE_FLIGHT" in call)
    assert '"max_runtime_sec" => 900::UINTEGER' in update
    assert "instance_type" not in update


@pytest.mark.parametrize("action", ["create", "update"])
def test_flight_deploy_passes_declared_instance_type(monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: ["flight-id"])

    deployer._deploy_flight(
        {
            "name": "sized-flight",
            "sourcePath": "src/flight.py",
            "requirementsPath": "src/requirements.txt",
            "scheduleCron": "",
            "instanceType": "F32",
        },
        "prod",
        PlanRecord("ops", "flight", "loader", "sized-flight", action, action == "update", "flight-id"),
    )

    statement = next(call for call in calls if f"MD_{action.upper()}_FLIGHT" in call)
    assert """"instance_type" => 'F32'""" in statement


def sized_flight_deployer(monkeypatch: pytest.MonkeyPatch, version: str) -> tuple[Deployer, list[str]]:
    deployer = Deployer(Project(FIXTURES / "complex"))
    queries: list[str] = []
    def fake_sql(statement: str) -> str:
        queries.append(statement)
        return version
    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr("md_blueprints.deploy.sql_backend", lambda: "motherduck")
    return deployer, queries


def test_instance_type_preflight_rejects_old_duckdb_before_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer, queries = sized_flight_deployer(monkeypatch, "v1.5.5")
    rendered = [RenderedBlueprint("ops", "Ops", "", {}, {"loader": {"name": "sized", "instanceType": "F16"}}, {}, {})]

    with pytest.raises(ValidationError, match=r"instanceType on ops.loader needs DuckDB 1.5.6 or newer, but the motherduck SQL backend runs v1.5.5"):
        deployer._preflight_flight_instance_types(rendered)
    assert queries == ["SELECT library_version FROM pragma_version()"]


@pytest.mark.parametrize("version", ["v1.5.6", "v1.6.0", "v2.0.1"])
def test_instance_type_preflight_accepts_current_duckdb(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    deployer, _ = sized_flight_deployer(monkeypatch, version)
    rendered = [RenderedBlueprint("ops", "Ops", "", {}, {"loader": {"name": "sized", "instanceType": "F16"}}, {}, {})]

    deployer._preflight_flight_instance_types(rendered)


def test_instance_type_preflight_skips_unsized_and_disabled_flights(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer, queries = sized_flight_deployer(monkeypatch, "v1.5.4")
    rendered = [RenderedBlueprint("ops", "Ops", "", {}, {
        "plain": {"name": "plain"},
        "disabled": {"name": "disabled", "instanceType": "F32", "deploy": False},
    }, {}, {})]

    deployer._preflight_flight_instance_types(rendered)
    assert queries == []


def test_dive_deploy_reconciles_governance_status(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(deployer, "_required_resources_sql", lambda *args: "[]")

    deployer._deploy_dive(
        {
            "title": "Revenue",
            "sourcePath": "src/dive.tsx",
            "requiredResources": [],
            "status": "endorsed",
        },
        {},
        {},
        "prod",
        PlanRecord(
            "ops",
            "dive",
            "dashboard",
            "Revenue",
            "update",
            True,
            "dive-id",
            current_status="ready",
            desired_status="endorsed",
        ),
    )

    assert any("MD_UPDATE_DIVE_STATUS" in call and "'endorsed'" in call for call in calls)


def test_share_reconciliation_manages_filter_and_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [("old-role", "role"), ("old-user", "user")],
    )

    deployer._reconcile_share(
        {
            "name": "finance share",
            "includePattern": ["reporting.*", "finance.salaries"],
            "grants": {
                "roles": ["finance"],
                "users": ["analyst@example.com"],
                "mode": "authoritative",
            },
        }
    )

    assert (
        'ALTER SHARE "finance share" SET INCLUDE_PATTERN '
        "'reporting.*, finance.salaries';"
    ) in calls
    assert 'GRANT READ ON SHARE "finance share" TO ROLE "finance";' in calls
    assert 'REVOKE READ ON SHARE "finance share" FROM USER "old-user";' in calls


def test_share_reconciliation_resets_filter_when_null(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    deployer._reconcile_share({"name": "finance share", "includePattern": None})

    assert calls == ['ALTER SHARE "finance share" RESET INCLUDE_PATTERN;']


def test_plan_preflights_role_dependencies_and_share_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    blueprint = RenderedBlueprint(
        name="access",
        title="Access",
        description="",
        shares={
            "finance": {
                "name": "finance",
                "database": "finance",
                "grants": {"roles": ["missing-grantee"]},
            }
        },
        flights={},
        dives={},
        contexts={},
        roles={
            "team": {
                "name": "finance-team",
                "includedRoles": ["missing-parent"],
                "deploy": True,
            }
        },
    )
    monkeypatch.setattr(deployer, "_live_role_names", lambda: {"explorer"})
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/example/id")

    records = deployer._build_deploy_plan([blueprint])

    role_record = next(record for record in records if record.type == "role")
    share_record = next(record for record in records if record.type == "share")
    assert role_record.action == "error"
    assert "missing-parent" in role_record.notes
    assert share_record.action == "error"
    assert "missing-grantee" in share_record.notes


def test_existing_managed_share_plan_reports_update(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    blueprint = RenderedBlueprint(
        name="data",
        title="Data",
        description="",
        shares={
            "finance": {
                "name": "finance",
                "database": "finance",
                "includePattern": None,
            }
        },
        flights={},
        dives={},
        contexts={},
    )
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/example/id")

    record = deployer._build_deploy_plan([blueprint])[0]

    assert record.action == "update"
    assert "reconciled" in record.notes


def test_role_reconciliation_supports_authoritative_memberships(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", fake_sql)

    def rows(statement: str) -> list[tuple[object, ...]]:
        if "SHOW ROLES" in statement:
            return [("analyst", "preset", True, None), ("inherited", "custom", False, None)]
        return [("old@example.com", "old@example.com", False, None)]

    monkeypatch.setattr(deployer, "_query_rows", rows)
    deployer._deploy_role(
        {
            "name": "finance team",
            "includedRoles": ["explorer"],
            "members": ["new@example.com"],
            "mode": "authoritative",
        },
        PlanRecord("access", "role", "finance", "finance team", "update", True, "finance team"),
    )

    assert 'CREATE ROLE IF NOT EXISTS "finance team";' in calls
    assert 'GRANT ROLE "explorer" TO ROLE "finance team";' in calls
    assert 'REVOKE ROLE "analyst" FROM ROLE "finance team";' in calls
    assert 'REVOKE ROLE "finance team" FROM USER "old@example.com";' in calls


def test_role_deployment_orders_managed_inheritance() -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    blueprint = RenderedBlueprint(
        name="access",
        title="Access",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        roles={
            "senior": {
                "name": "senior-analysts",
                "includedRoles": ["analysts"],
                "deploy": True,
            },
            "base": {"name": "analysts", "includedRoles": [], "deploy": True},
        },
    )

    ordered = deployer._role_deployment_order([blueprint])

    assert [str(role["name"]) for _, _, role in ordered] == ["analysts", "senior-analysts"]


def test_rbac_preflight_rejects_admin_only_resources_without_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_query_rows", lambda statement: [("builder",)])
    blueprint = RenderedBlueprint(
        name="access",
        title="Access",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        roles={"finance": {"name": "finance", "deploy": True}},
    )

    with pytest.raises(ValidationError, match="requires the admin role"):
        deployer._preflight_rbac([blueprint])


def test_rbac_preflight_lists_roles_of_the_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    statements: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        statements.append(statement)
        if statement == "SELECT current_user":
            return [('ci "bot"',)]
        # The admin role reaches the deployer through a custom role.
        return [("platform", "custom", True, None), ("admin", "preset", False, None)]

    monkeypatch.setattr(deployer, "_query_rows", rows)
    blueprint = RenderedBlueprint(
        name="docs",
        title="Docs",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={"handbook": {"deploy": True, "access": "organization"}},
    )

    deployer._preflight_rbac([blueprint])

    assert statements == ["SELECT current_user", 'SHOW ROLES TO USER "ci ""bot"""']


def test_guide_deploy_uses_version_metadata_and_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [
            (
                "old content",
                "old-sha",
                "[]",
                "[]",
                "Old title",
                "old-topic",
                "Old description",
                "user",
            )
        ],
    )
    guide_source = tmp_path / "guide.md"
    guide_source.write_text("# Revenue\n", encoding="utf-8")
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
    )

    deployer._deploy_guide(
        blueprint,
        {
            "title": "Revenue definitions",
            "topic": "finance/revenue",
            "description": "Canonical metrics",
            "sourcePath": str(guide_source),
            "access": "organization",
            "references": [],
            "changeComment": "sync definitions",
            "externalId": "abc123",
        },
        "prod",
        PlanRecord("knowledge", "guide", "revenue", "Revenue definitions", "update", True, "guide-id"),
    )

    statement = calls[0]
    assert "MD_UPDATE_GUIDE" in statement
    assert "MD_UPDATE_GUIDE_METADATA" in statement
    assert "MD_SET_GUIDE_ACCESS" in statement
    assert "'sync definitions'" in statement
    assert "'abc123'" in statement


def test_guide_deploy_does_not_append_unchanged_reference_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)
    guide_id = "00000000-0000-0000-0000-000000000042"
    current_references = (
        '[{"type":"guide","url":null,"schema":null,"table":null,"column":null,'
        f'"view":null,"macro":null,"guide_id":"{guide_id}","dive_id":null,'
        '"flight_id":null,"description":null}]'
    )
    desired_references = (
        '[{"type":"guide","url":null,"schema":null,"table":null,"column":null,'
        '"view":null,"macro":null,"uuid":"'
        + guide_id
        + '","description":null}]'
    )
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [
            (
                "# Revenue\n",
                "abc123",
                current_references,
                desired_references,
                "Revenue definitions",
                None,
                None,
                "user",
            )
        ],
    )
    guide_source = tmp_path / "guide.md"
    guide_source.write_text("# Revenue\n", encoding="utf-8")
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
    )

    deployer._deploy_guide(
        blueprint,
        {
            "title": "Revenue definitions",
            "sourcePath": str(guide_source),
            "references": [{"type": "guide", "uuid": guide_id}],
            "externalId": "abc123",
        },
        "prod",
        PlanRecord("knowledge", "guide", "revenue", "Revenue definitions", "update", True, "guide-id"),
    )

    assert calls == []


def test_guide_deploy_appends_version_when_references_are_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [
            (
                "# Revenue\n",
                "abc123",
                '[{"type":"catalog","url":"md:analytics"}]',
                "[]",
                "Revenue definitions",
                None,
                None,
                "user",
            )
        ],
    )
    guide_source = tmp_path / "guide.md"
    guide_source.write_text("# Revenue\n", encoding="utf-8")
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
    )

    deployer._deploy_guide(
        blueprint,
        {
            "title": "Revenue definitions",
            "sourcePath": str(guide_source),
            "references": [],
            "externalId": "abc123",
        },
        "prod",
        PlanRecord("knowledge", "guide", "revenue", "Revenue definitions", "update", True, "guide-id"),
    )

    assert "FROM MD_UPDATE_GUIDE(" in calls[0]
    assert "MD_UPDATE_GUIDE_METADATA" not in calls[0]
    assert "MD_SET_GUIDE_ACCESS" not in calls[0]


def test_guide_resource_reference_uses_explicit_managed_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    guide_id = "00000000-0000-0000-0000-000000000042"
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={
            "canonical": {
                "id": guide_id,
                "sourcePath": "guide.md",
                "deploy": False,
            }
        },
    )
    deployer.rendered_by_name = {"knowledge": blueprint}
    monkeypatch.setattr(
        deployer,
        "_get_guide_rows_by_id",
        lambda resource_id: [(resource_id,)],
    )

    references_sql = deployer._guide_references_sql(
        blueprint,
        [{"type": "guide", "resource": "canonical"}],
    )

    assert f"'{guide_id}'::UUID" in references_sql


def test_guide_plan_rejects_missing_unselected_reference_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    producer = RenderedBlueprint(
        name="producer",
        title="Producer",
        description="",
        shares={},
        flights={"loader": {"name": "historical-loader"}},
        dives={},
        contexts={},
    )
    consumer = RenderedBlueprint(
        name="consumer",
        title="Consumer",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={
            "runbook": {
                "title": "Runbook",
                "sourcePath": "runbook.md",
                "deploy": True,
                "references": [
                    {
                        "type": "flight",
                        "blueprint": "producer",
                        "resource": "loader",
                    }
                ],
            }
        },
    )
    deployer.rendered_by_name = {"producer": producer}
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])

    records = deployer._build_deploy_plan([consumer])

    guide_record = next(record for record in records if record.type == "guide")
    assert guide_record.action == "error"
    assert "expected exactly one" in guide_record.notes


def test_cleanup_flight_delete_uses_named_motherduck_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    deployer._apply_cleanup_plan(
        [
            PlanRecord(
                blueprint="ops",
                type="flight",
                key="loader",
                name="preview-loader",
                action="delete",
                exists=True,
                id="1a4ea2e6-0997-43ea-afe9-78c15c62220e",
            )
        ]
    )

    assert calls == ['FROM MD_DELETE_FLIGHT("flight_id" => \'1a4ea2e6-0997-43ea-afe9-78c15c62220e\'::UUID);']


def test_cleanup_ignores_resources_already_removed_by_concurrent_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))

    def missing_share(statement: str) -> str:
        raise CommandError('MotherDuck SQL failed: Share with name "preview_share" does not exist!')

    monkeypatch.setattr(deployer, "_sql", missing_share)

    deployer._apply_cleanup_plan(
        [
            PlanRecord(
                blueprint="ops",
                type="share",
                key="data",
                name="preview_share",
                action="drop_share",
                exists=True,
                id="md:_share/example/id",
            )
        ]
    )

    assert "already removed by another cleanup run" in capsys.readouterr().out


def test_cleanup_still_surfaces_unrelated_delete_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))

    def permission_error(statement: str) -> str:
        raise CommandError("MotherDuck SQL failed: permission denied")

    monkeypatch.setattr(deployer, "_sql", permission_error)

    with pytest.raises(CommandError, match="permission denied"):
        deployer._delete_if_present("FROM delete_resource()", "preview resource")


def test_sql_identifier_quoting_rejects_unsafe_database_names() -> None:
    assert quote_ident("preview_database_1") == '"preview_database_1"'

    with pytest.raises(ValidationError, match="Unsafe SQL identifier"):
        quote_ident("prod; DROP DATABASE prod")


def test_plan_formatter_escapes_markdown_cells() -> None:
    from md_blueprints.deploy import PlanFormatter

    output = PlanFormatter.format(
        [
            PlanRecord(
                blueprint="bp|name",
                type="flight",
                key="loader",
                name="name with\nnewline",
                action="create",
                exists=False,
                id=None,
                notes="safe",
            )
        ],
        title="Plan",
    )

    assert "bp\\|name" in output
    assert "name with newline" in output



def test_plan_formatter_separates_selected_and_added_packages() -> None:
    from md_blueprints.deploy import PlanFormatter

    records = [
        PlanRecord(name, "dive", "dashboard", name, "create", False, None)
        for name in ("ingest", "listings", "ingest")
    ]

    output = PlanFormatter.format(records, title="Plan", requested=["listings"])
    assert output.splitlines()[:3] == [
        "#### Plan",
        "",
        "**Selected:** `listings` · **Added by the dependency graph:** `ingest`",
    ]
    assert PlanFormatter.selection(["ingest", "listings"], ["ingest", "listings"]) == (
        "**Selected:** `ingest`, `listings`"
    )
    assert "Selected" not in PlanFormatter.format(records, title="Plan")

@pytest.mark.parametrize('status', ['SUCCEEDED', 'RUN_STATUS_SUCCEEDED'])
def test_wait_tracks_the_submitted_run_not_the_latest(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    queries: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        queries.append(statement)
        assert 'MD_LIST_FLIGHT_RUNS' in statement
        return [(43, 'FAILED'), (42, status)]

    monkeypatch.setattr(deployer, '_query_rows', rows)
    deployer._wait_for_flight_run_success('00000000-0000-0000-0000-000000000001', 42)
    assert len(queries) == 1


@pytest.mark.parametrize('status', ['FAILED', 'CANCELLED', 'RUN_STATUS_FAILED', 'RUN_STATUS_CANCELLED'])
@pytest.mark.parametrize('record', ['{"line":"test log","line_number":1}', '{"logs":"test log"}'])
def test_wait_recognizes_current_and_legacy_failure_statuses(
    monkeypatch: pytest.MonkeyPatch, status: str, record: str,
) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    queries: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        queries.append(statement)
        if 'MD_GET_FLIGHT_LOGS' in statement:
            assert 'run_number := 42' in statement
            return [(record,)]
        return [(43, 'SUCCEEDED'), (42, status)]

    monkeypatch.setattr(deployer, '_query_rows', rows)
    with pytest.raises(CommandError, match='Flight run 42 ended with .*test log'):
        deployer._wait_for_flight_run_success('00000000-0000-0000-0000-000000000001', 42)
    assert len(queries) == 2


def test_wait_follows_pagination_for_exact_run(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    queries: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        queries.append(statement)
        if '\"offset\" := 0' in statement:
            return [(number, 'SUCCEEDED') for number in range(200, 100, -1)]
        assert '\"offset\" := 100' in statement
        return [(42, 'FAILED')]

    monkeypatch.setattr(deployer, '_query_rows', rows)
    assert deployer._flight_run_status('00000000-0000-0000-0000-000000000001', 42) == 'FAILED'
    assert len(queries) == 2


def test_log_read_failure_does_not_hide_failed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    monkeypatch.setattr(deployer, '_flight_run_status', lambda *args: 'FAILED')

    def rows(statement: str) -> list[tuple[object, ...]]:
        raise CommandError('log service unavailable')

    monkeypatch.setattr(deployer, '_query_rows', rows)
    with pytest.raises(CommandError, match='Flight run 42 ended with FAILED.*Logs unavailable'):
        deployer._wait_for_flight_run_success('00000000-0000-0000-0000-000000000001', 42)


def test_single_line_required_databases_strip_matches_legacy_regex() -> None:
    import re

    from md_blueprints.deploy import strip_required_databases_export

    sources = [
        'export const REQUIRED_DATABASES = [{ alias: "a", path: "md:a" }];\nexport default 1;\n',
        'export const REQUIRED_DATABASES = [] // local\nexport default 1;\n',
        'export default 1;\nexport const REQUIRED_DATABASES = [];',
        '  export const REQUIRED_DATABASES = [];\nexport default 1;\n',
    ]
    for source in sources:
        legacy = re.sub(r"export const REQUIRED_DATABASES[^\n]*\n", "", source)
        assert strip_required_databases_export(source) == legacy


def test_multi_line_required_databases_export_is_removed_whole() -> None:
    from md_blueprints.deploy import strip_required_databases_export

    component = "export default function Dive() { return null; }\n"
    source = (
        "import { useSQLQuery } from '@motherduck/react-sql-query';\n"
        "export const REQUIRED_DATABASES = [\n"
        "  // mounted for local preview\n"
        "  { type: 'share', path: 'md:_share/a/1', alias: 'a' },\n"
        "] as const;\n" + component
    )

    assert strip_required_databases_export(source) == (
        "import { useSQLQuery } from '@motherduck/react-sql-query';\n" + component
    )


def test_dive_content_sql_keeps_server_side_strip_for_single_line(tmp_path: Path) -> None:
    single = tmp_path / "single.tsx"
    single.write_text('export const REQUIRED_DATABASES = [];\nexport default 1;\n', encoding="utf-8")
    multi = tmp_path / "multi.tsx"
    multi.write_text('export const REQUIRED_DATABASES = [\n  { alias: "a" },\n];\nexport default 1;\n', encoding="utf-8")

    assert "regexp_replace" in Deployer._dive_content_sql(str(single))
    assert "regexp_replace" in Deployer._dive_content_sql(str(tmp_path / "missing.tsx"))
    assert Deployer._dive_content_sql(str(multi)) == "('export default 1;\n')"


def test_flight_wait_follows_max_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLIGHT_RUN_POLL_ATTEMPTS", raising=False)

    assert Deployer._flight_run_poll_attempts(10, None) == 60
    assert Deployer._flight_run_poll_attempts(10, 60) == 60
    assert Deployer._flight_run_poll_attempts(10, 3600) == 372
    monkeypatch.setenv("FLIGHT_RUN_POLL_ATTEMPTS", "3")
    assert Deployer._flight_run_poll_attempts(10, 3600) == 3


def test_flight_wait_timeout_explains_state_and_next_step(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setenv("FLIGHT_RUN_POLL_ATTEMPTS", "2")
    monkeypatch.setenv("FLIGHT_RUN_POLL_SLEEP_SECONDS", "0")
    monkeypatch.setattr(deployer, "_flight_run_status", lambda *args: "RUNNING")

    with pytest.raises(CommandError) as exc:
        deployer._wait_for_flight_run_success(
            "00000000-0000-0000-0000-000000000001", 7, max_runtime_sec=30, name="loader",
        )

    message = str(exc.value)
    assert "Flight 'loader'" in message
    assert "Already applied:" in message
    assert "was not cancelled" in message
    assert "Next:" in message
    assert "maxRuntimeSec" in message


def test_flight_deploy_passes_max_runtime_to_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    waited: list[dict[str, object]] = []
    monkeypatch.setattr(deployer, "_sql", lambda statement: "5" if "MD_RUN_FLIGHT" in statement else "")
    monkeypatch.setattr(
        deployer, "_wait_for_flight_run_success", lambda fid, number, **kwargs: waited.append(kwargs),
    )

    deployer._deploy_flight(
        {
            "name": "loader",
            "sourcePath": "src/flight.py",
            "requirementsPath": "src/requirements.txt",
            "maxRuntimeSec": 1800,
            "runOnDeploy": True,
            "waitForRun": "success",
        },
        "prod",
        PlanRecord("ops", "flight", "loader", "loader", "update", True, "flight-id"),
    )

    assert waited == [{"max_runtime_sec": 1800, "name": "loader"}]


def test_cleanup_drops_database_names_that_need_quoting(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    deployer._apply_cleanup_plan(
        [PlanRecord("ops", "database", "data", 'my-db_feature_x "v2"', "drop_database", True, None)]
    )

    assert calls == ['DROP DATABASE IF EXISTS "my-db_feature_x ""v2""";']


def test_cleanup_requires_branch_slug_as_whole_token(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: pytest.fail("unsafe share lookup"))
    blueprint = RenderedBlueprint(
        name="ops", title="Ops", description="",
        shares={"data": {"name": "domain_data", "database": "domain_data"}},
        flights={}, dives={}, contexts={},
    )

    records = deployer._build_cleanup_plan([blueprint], "main", branch="main")

    assert [(record.type, record.action) for record in records] == [("share", "error")]
    assert "without branch slug main" in records[0].notes


def test_cleanup_compares_against_every_stable_target(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: pytest.fail("unsafe share lookup"))

    def shares(name: str) -> RenderedBlueprint:
        return RenderedBlueprint(
            name="ops", title="Ops", description="",
            shares={"data": {"name": name, "database": name}},
            flights={}, dives={}, contexts={},
        )

    records = deployer._build_cleanup_plan(
        [shares("data_feature_x")],
        "feature_x",
        branch="feature/x",
        production={"ops": shares("data_staging")},
        stable_target="staging",
        stable_renders={"staging": {"ops": shares("data_staging")}, "prod": {"ops": shares("data_feature_x")}},
    )

    assert records[0].action == "error"
    assert "matches production: data_feature_x" in records[0].notes


def test_cleanup_plan_renders_all_stable_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project(FIXTURES / "simple")
    targets = project.manifest["targets"]
    assert isinstance(targets, dict)
    targets["staging"] = copy.deepcopy(targets["prod"])
    deployer = Deployer(project)
    captured: dict[str, object] = {}
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda target, operation: None)
    monkeypatch.setattr(
        deployer, "_build_cleanup_plan", lambda rendered, slug, **kwargs: captured.update(kwargs) or [],
    )

    deployer.cleanup_plan(target="preview", branch="feature/test", names=None)

    stable_renders = captured["stable_renders"]
    assert isinstance(stable_renders, dict)
    assert set(stable_renders) == {"staging", "prod"}


def test_name_matched_resources_get_binding_note_outside_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project(FIXTURES / "complex")
    deployer = Deployer(project)
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [f"{name}-id"])
    monkeypatch.setattr(deployer, "_list_dive_states", lambda title: [(f"{title}-id", "ready")])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: f"md:_share/{name}/123")

    deployer.target = "prod"
    records = deployer._build_deploy_plan(project.render_all("prod"))
    matched = [record for record in records if record.type in {"flight", "dive"}]
    assert matched and all("by name; bind it with `id`" in record.notes for record in matched)

    deployer.target = "preview"
    preview = deployer._build_deploy_plan(project.render_all("preview", branch="feature/x"))
    assert not any("bind it with `id`" in record.notes for record in preview)


def test_guide_name_match_note(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    deployer.target = "prod"
    monkeypatch.setattr(deployer, "_list_guide_ids", lambda title, topic: ["guide-id"])
    blueprint = RenderedBlueprint(
        name="docs", title="Docs", description="", shares={}, flights={}, dives={}, contexts={},
        guides={"runbook": {"title": "Runbook", "sourcePath": "runbook.md", "deploy": True}},
    )

    record = deployer._guide_plan_record(blueprint, "runbook", blueprint.guides["runbook"])

    assert (record.action, record.id) == ("update", "guide-id")
    assert "matched existing Guide 'Runbook' by name" in record.notes


def test_authoritative_share_grants_list_revocations_at_plan_time(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    blueprint = RenderedBlueprint(
        name="data", title="Data", description="",
        shares={
            "finance": {
                "name": "finance",
                "database": "finance",
                "grants": {"roles": ["analyst"], "users": [], "mode": "authoritative"},
            }
        },
        flights={}, dives={}, contexts={},
    )
    monkeypatch.setattr(deployer, "_live_role_names", lambda: {"analyst"})
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/finance/1")
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [("analyst", "role"), ("terraform-role", "role"), ("ops@example.com", "user")],
    )

    record = deployer._build_deploy_plan([blueprint])[0]

    assert record.action == "update"
    assert "including grants created outside Blueprints (for example by Terraform" in record.notes
    assert "will revoke: role terraform-role, user ops@example.com" in record.notes


def test_authoritative_role_lists_revocations_and_tolerates_read_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    role: dict[str, object] = {
        "name": "team", "includedRoles": ["explorer"], "members": ["a@example.com"], "mode": "authoritative",
    }

    def rows(statement: str) -> list[tuple[object, ...]]:
        if "SHOW ROLES" in statement:
            return [("explorer", "preset", True, None), ("legacy", "custom", True, None)]
        return [("a@example.com",), ("b@example.com",)]

    monkeypatch.setattr(deployer, "_query_rows", rows)
    assert "will revoke: role legacy, user b@example.com" in deployer._authoritative_role_note(role, True)
    assert "nothing to revoke today (new role)" in deployer._authoritative_role_note(role, False)

    def failing(statement: str) -> list[tuple[object, ...]]:
        raise CommandError("permission denied")

    monkeypatch.setattr(deployer, "_query_rows", failing)
    assert "could not be read at plan time" in deployer._authoritative_role_note(role, True)


def test_context_plan_note_is_a_deprecation() -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    blueprint = RenderedBlueprint(
        name="notes", title="Notes", description="", shares={}, flights={}, dives={},
        contexts={"notes": {"sourcePath": "notes.md", "deploy": False}},
    )

    record = deployer._build_deploy_plan([blueprint])[0]

    assert record.action == "validated_only"
    assert "deprecated" in record.notes and "resources.guides" in record.notes
    assert "not available yet" not in record.notes


def write_slug_cleanup_project(root: Path) -> Project:
    package = root / "flights" / "loader"
    (package / "src").mkdir(parents=True)
    (package / "src" / "flight.py").write_text("print('ok')\n", encoding="utf-8")
    (package / "src" / "requirements.txt").write_text("", encoding="utf-8")
    (root / "motherduck.yml").write_text(
        """
schemaVersion: 1
repository:
  name: slugs
include:
  - flights/*/blueprint.yml
targets:
  preview:
    mode: preview
    policies:
      cleanup: true
      requireBranchSlugInDataResources: true
  prod:
    mode: production
""".lstrip(),
        encoding="utf-8",
    )
    (package / "blueprint.yml").write_text(
        """
schemaVersion: 1
name: loader
title: Loader
resources:
  shares:
    data:
      name: data
      database: data_db
      targets:
        preview:
          name: data_${target.branch_slug}
          database: data_db_${target.branch_slug}
          dropDatabase: true
  flights:
    loader:
      name: loader
      source: src/flight.py
      requirements: src/requirements.txt
      targets:
        preview:
          name: loader_${target.branch_slug}
""".lstrip(),
        encoding="utf-8",
    )
    return Project(root)


def slug_cleanup_deployer(project: Project, monkeypatch: pytest.MonkeyPatch, existing: set[str]) -> tuple[Deployer, list[str]]:
    deployer = Deployer(project)
    reads: list[str] = []
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda target, operation: None)

    def flights(name: str) -> list[str]:
        reads.append(name)
        return [f"{name}-id"] if name in existing else []

    def share(name: str) -> str:
        reads.append(name)
        return f"md:_share/{name}/1" if name in existing else ""

    def rows(statement: str) -> list[tuple[object, ...]]:
        assert statement.startswith("SELECT alias FROM MD_ALL_DATABASES()")
        return [("db",)] if any(f"'{name}'" in statement for name in existing) else []

    monkeypatch.setattr(deployer, "_list_flight_ids", flights)
    monkeypatch.setattr(deployer, "_find_share_url", share)
    monkeypatch.setattr(deployer, "_query_rows", rows)
    return deployer, reads


def test_cleanup_also_removes_resources_named_with_legacy_truncated_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from md_blueprints.project import branch_slug, legacy_branch_slug

    branch = "feature/" + "long-branch-name-" * 4
    new, legacy = branch_slug(branch), legacy_branch_slug(branch)
    assert new != legacy
    project = write_slug_cleanup_project(tmp_path)
    deployer, _ = slug_cleanup_deployer(
        project, monkeypatch, {f"loader_{new}", f"loader_{legacy}", f"data_{legacy}", f"data_db_{legacy}"},
    )

    records = deployer.cleanup_plan(target="preview", branch=branch, names=None)
    deployer.ensure_plan_succeeds(records)

    actions = {(record.type, record.action, record.name) for record in records}
    assert ("flight", "delete", f"loader_{new}") in actions
    assert ("flight", "delete", f"loader_{legacy}") in actions
    assert ("share", "drop_share", f"data_{legacy}") in actions
    assert ("database", "drop_database", f"data_db_{legacy}") in actions
    # Missing legacy resources add nothing; the current pass still reports its own state.
    assert ("share", "missing", f"data_{new}") in actions
    assert not any(record.name.endswith(legacy) and record.action == "missing" for record in records)
    assert project.render_all("preview", branch=branch)[0].flights["loader"]["name"] == f"loader_{new}"


def test_cleanup_skips_legacy_pass_for_short_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = write_slug_cleanup_project(tmp_path)
    deployer, reads = slug_cleanup_deployer(project, monkeypatch, set())

    records = deployer.cleanup_plan(target="preview", branch="feature/short", names=None)

    assert reads == ["loader_feature_short", "data_feature_short"]
    assert len(records) == 3


def test_legacy_cleanup_pass_drops_unsafe_and_missing_records() -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    current = [PlanRecord("ops", "flight", "loader", "loader_new", "delete", True, "a")]
    legacy = [
        PlanRecord("ops", "flight", "loader", "loader_new", "delete", True, "a"),
        PlanRecord("ops", "share", "data", "data_legacy", "error", None, None, "matches production"),
        PlanRecord("ops", "share", "data", "data_legacy", "missing", False, None),
    ]

    assert deployer._legacy_cleanup_records(current, legacy) == []
