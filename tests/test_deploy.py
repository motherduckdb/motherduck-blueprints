from __future__ import annotations

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


def test_flight_run_uses_named_motherduck_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    deployer._deploy_flight(
        {
            "name": "preview-loader",
            "sourcePath": "src/flight.py",
            "requirementsPath": "src/requirements.txt",
            "scheduleCron": "",
            "runOnDeploy": True,
            "waitForRun": False,
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
    monkeypatch.setattr(deployer, "_query_rows", lambda statement: [("old content", "old-sha")])
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
