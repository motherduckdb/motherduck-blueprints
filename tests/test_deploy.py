from __future__ import annotations

from pathlib import Path

import pytest

from md_blueprints.deploy import Deployer, PlanRecord, quote_ident
from md_blueprints.project import CommandError, Project, RenderedBlueprint
from md_blueprints.schema import ValidationError


FIXTURES = Path(__file__).parent / "fixtures"


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


def test_deploy_plan_is_idempotent_for_same_live_state(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project(FIXTURES / "complex")
    deployer = Deployer(project)
    rendered = project.render_all("prod")

    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [f"{name}-id"])
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: [f"{title}-id"])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: f"md:_share/{name}/123")

    first = [record.to_dict() for record in deployer._build_deploy_plan(rendered)]
    second = [record.to_dict() for record in deployer._build_deploy_plan(rendered)]

    assert first == second
    assert {record["action"] for record in first if record["type"] in {"flight", "dive"}} == {"update"}
    assert {record["action"] for record in first if record["type"] == "share"} == {"present"}


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
