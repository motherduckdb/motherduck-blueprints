from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("prefix", ["", "reusable_"])
def test_cleanup_environment_error_does_not_require_new_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / f".github/workflows/{prefix}cleanup_preview_blueprints.yaml"
    workflow = yaml.safe_load(path.read_text())
    steps = workflow["jobs"]["resolve-environment"]["steps"]
    step = next(step for step in steps if step.get("id") == "preview-target")
    source = step["run"].split("python - <<'PY'\n")[1].split("\nPY")[0]
    assert "md_blueprints" not in source
    (tmp_path / "motherduck.yml").write_text("targets: {preview: {mode: preview}}\n")
    summary = tmp_path / "summary"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    with pytest.raises(SystemExit, match="must declare environment"):
        exec(compile(source, "cleanup_preview_blueprints.yaml", "exec"), {})
    assert "Next: check targets.preview" in summary.read_text()


def test_canonical_template_validates_without_live_deployment() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / ".github/workflows/reusable_deploy_blueprints.yaml"
    jobs = yaml.safe_load(path.read_text())["jobs"]
    assert "if" not in jobs["compute_changes"]
    for name in ("deploy-preview", "deploy-stable", "deploy-release-production"):
        assert "github.repository != 'motherduckdb/blueprints-template' &&" in jobs[name]["if"]


@pytest.mark.parametrize("prefix", ["", "reusable_"])
@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_environment_migration_validates_without_deploying_untrusted_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str, event: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / f".github/workflows/{prefix}deploy_blueprints.yaml").read_text())
    step = next(step for step in workflow["jobs"]["compute_changes"]["steps"] if step.get("id") == "topology")
    source = step["run"].split("python - <<'PY'\n")[1].split("\nPY")[0]
    manifest = yaml.safe_load((root / "motherduck.yml").read_text())
    legacy = {"targets": {"preview": {"mode": "preview"}}}
    if event == "push":
        manifest["targets"]["prod"].pop("environment")
    (tmp_path / "motherduck.yml").write_text(yaml.safe_dump(manifest))
    output = tmp_path / "outputs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVENT_NAME", event)
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: yaml.safe_dump(legacy))

    if event == "push":
        with pytest.raises(SystemExit, match="must declare environment"):
            exec(compile(source, "deploy_blueprints.yaml", "exec"), {})
        assert not output.exists()
        assert "Next: check targets in motherduck.yml" in summary.read_text()
    else:
        exec(compile(source, "deploy_blueprints.yaml", "exec"), {})
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["deployment_enabled"] == "false"
        assert values["environment"] == ""
        assert values["target"] == "preview"


def test_customer_workflows_delegate_with_matching_permissions_and_inputs(tmp_path: Path) -> None:
    from md_blueprints.init import run_init

    run_init(tmp_path)
    root = Path(__file__).resolve().parents[1]
    for path in (tmp_path / '.github/workflows').glob('*.yaml'):
        caller = yaml.safe_load(path.read_text())
        assert len(caller['jobs']) == 1
        job = next(iter(caller['jobs'].values()))
        reference = job['uses'].split('@')[0]
        provider = yaml.safe_load((root / reference.split('motherduck-blueprints/', 1)[1]).read_text())
        assert caller['permissions'] == provider['permissions']
        # PyYAML's YAML 1.1 loader reads the unquoted GitHub `on` key as True.
        assert set(job.get('with', {})) == set((provider[True]['workflow_call'] or {}).get('inputs', {}))
        assert 'secrets' not in job
        assert all('steps' not in value for value in caller['jobs'].values())


def test_reusable_jobs_preserve_environment_secrets_and_verification() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ('deploy_blueprints', 'cleanup_preview_blueprints'):
        workflow = yaml.safe_load((root / f'.github/workflows/reusable_{name}.yaml').read_text())
        for job in workflow['jobs'].values():
            for step in job.get('steps', []):
                command = step.get('with', {}).get('command')
                if command in ('plan', 'deploy', 'cleanup'):
                    assert 'environment' in job
                    assert step['env']['MOTHERDUCK_TOKEN'] == '${{ secrets.MOTHERDUCK_TOKEN }}'
                if command == 'deploy':
                    assert step['with']['verify-after-deploy'] == 'true'


def test_reusable_action_pins_match_the_release() -> None:
    from md_blueprints import __version__

    root = Path(__file__).resolve().parents[1]
    for path in (root / '.github/workflows').glob('reusable_*.yaml'):
        workflow = yaml.safe_load(path.read_text())
        pins = [
            step['uses']
            for job in workflow['jobs'].values()
            for step in job.get('steps', [])
            if step.get('uses', '').startswith('motherduckdb/motherduck-blueprints@')
        ]
        assert pins
        assert set(pins) == {f'motherduckdb/motherduck-blueprints@v{__version__}'}
