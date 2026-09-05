from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


def test_canonical_template_validates_without_live_deployment() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "src/md_blueprints/template_repo/.github/workflows/deploy_blueprints.yaml"
    jobs = yaml.safe_load(path.read_text())["jobs"]
    assert "if" not in jobs["compute_changes"]
    for name in ("deploy-preview", "deploy-stable", "deploy-release-production"):
        assert "github.repository != 'motherduckdb/blueprints-template' &&" in jobs[name]["if"]


@pytest.mark.parametrize("prefix", ["", "src/md_blueprints/template_repo/"])
@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_environment_migration_validates_without_deploying_untrusted_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str, event: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / prefix / ".github/workflows/deploy_blueprints.yaml").read_text())
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
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: yaml.safe_dump(legacy))

    if event == "push":
        with pytest.raises(SystemExit, match="must declare environment"):
            exec(compile(source, "deploy_blueprints.yaml", "exec"), {})
        assert not output.exists()
    else:
        exec(compile(source, "deploy_blueprints.yaml", "exec"), {})
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["deployment_enabled"] == "false"
        assert values["environment"] == ""
        assert values["target"] == "preview"
