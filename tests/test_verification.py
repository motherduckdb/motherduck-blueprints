from __future__ import annotations

import copy
from pathlib import Path

import pytest

from md_blueprints.deploy import Deployer, PlanRecord
from md_blueprints.project import CommandError, Project, RenderedBlueprint
from md_blueprints.schema import ValidationError


FIXTURE = Path(__file__).parent / "fixtures/simple"


def record(kind: str = "flight", action: str = "update", resource_id: str | None = "original") -> PlanRecord:
    return PlanRecord("example", kind, "resource", "Example", action, True, resource_id)


def deployment(monkeypatch: pytest.MonkeyPatch, before: list[PlanRecord], after: list[PlanRecord]) -> tuple[Deployer, list[str]]:
    deployer = Deployer(Project(FIXTURE))
    rendered = RenderedBlueprint("example", "Example", "", {}, {}, {}, {})
    monkeypatch.setattr(deployer, "_validate_and_render", lambda *args: [rendered])
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda *args: None)
    monkeypatch.setattr(deployer, "_preflight_rbac", lambda *args: None)
    replies = [before, after]
    monkeypatch.setattr(deployer, "_build_deploy_plan", lambda *args: replies.pop(0))
    writes: list[str] = []
    monkeypatch.setattr(deployer, "_deploy_blueprint", lambda *args: writes.append("apply"))
    return deployer, writes


@pytest.mark.parametrize("verify", [True, False])
def test_failed_preflight_blocks_all_writes_even_when_postcheck_disabled(
    monkeypatch: pytest.MonkeyPatch, verify: bool,
) -> None:
    deployer, writes = deployment(monkeypatch, [record(), record(action="error", resource_id="missing")], [])
    with pytest.raises(ValidationError, match="Plan contains errors"):
        deployer.deploy(target="prod", branch=None, names=None, verify=verify)
    assert writes == []


@pytest.mark.parametrize("after,expected_message", [
    ([], "Verification omitted"),
    ([record(resource_id="replacement")], "changed identity"),
    ([record(action="create", resource_id=None)], "not present"),
    ([record(action="error")], "Plan contains errors"),
    ([record(kind="input", action="pending")], "not present"),
])
def test_postcheck_fails_cd_after_wrong_or_missing_state(
    monkeypatch: pytest.MonkeyPatch, after: list[PlanRecord], expected_message: str,
) -> None:
    deployer, writes = deployment(monkeypatch, [record(kind=after[0].type if after else "flight")], after)
    with pytest.raises(CommandError, match=f"Deployment applied, but verification failed:.*{expected_message}"):
        deployer.deploy(target="prod", branch=None, names=None)
    assert writes == ["apply"]


def test_successful_postcheck_writes_customer_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    deployer, writes = deployment(monkeypatch, [record()], [record()])
    deployer.deploy(target="prod", branch=None, names=None)
    assert writes == ["apply"]
    assert "Deployment Verification" in summary.read_text()
    assert "original" in summary.read_text() and "verified" in summary.read_text()


def test_readonly_verify_checks_disabled_bindings_without_mutating_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURE))
    resource: dict[str, object] = {"id": "original", "deploy": False}
    rendered = RenderedBlueprint("example", "Example", "", {}, {"resource": resource}, {}, {})
    original = copy.deepcopy(rendered.to_dict())
    monkeypatch.setattr(deployer, "_validate_and_render", lambda *args: [rendered])
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda *args: None)
    monkeypatch.setattr(deployer, "_preflight_rbac", lambda *args: None)

    def plan(values: list[RenderedBlueprint]) -> list[PlanRecord]:
        assert values[0].flights["resource"]["deploy"] is True
        return [record()]

    monkeypatch.setattr(deployer, "_build_deploy_plan", plan)
    monkeypatch.setattr(deployer, "_deploy_blueprint", lambda *args: pytest.fail("verify must not deploy"))
    assert deployer.verify(target="prod", branch=None, names=None)[0].action == "verified"
    assert rendered.to_dict() == original


@pytest.mark.parametrize("desired", [None, "ready"])
def test_dive_status_drift_fails_verification(monkeypatch: pytest.MonkeyPatch, desired: str | None) -> None:
    before = record(kind="dive")
    before.current_status, before.desired_status = "endorsed", desired
    after = record(kind="dive")
    after.current_status, after.desired_status = "draft", desired
    deployer, _ = deployment(monkeypatch, [before], [after])
    with pytest.raises(CommandError, match="status is draft"):
        deployer.deploy(target="prod", branch=None, names=None)


def test_explicit_opt_out_skips_only_postcheck(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer, writes = deployment(monkeypatch, [record()], [record(action="error")])
    deployer.deploy(target="prod", branch=None, names=None, verify=False)
    assert writes == ["apply"]


def test_created_flight_id_is_captured_and_compared(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURE))
    created = record(action="create", resource_id=None)
    monkeypatch.setattr(deployer, "_sql", lambda statement: "")
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: ["created-id"])
    deployer._deploy_flight(
        {"name": "Example", "sourcePath": "main.py", "requirementsPath": "requirements.txt"},
        "prod", created,
    )
    assert created.id == "created-id"
    monkeypatch.setattr(deployer, "_build_deploy_plan", lambda values: [record(resource_id="different-id")])
    with pytest.raises(ValidationError, match="changed identity"):
        deployer._verify_rendered([], [created])
