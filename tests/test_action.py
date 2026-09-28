from __future__ import annotations

import subprocess
import os
import json
import sys
from pathlib import Path
from typing import TextIO, cast

import pytest
import yaml


def test_action_defaults_to_validation() -> None:
    action = yaml.safe_load((Path(__file__).resolve().parents[1] / "action.yml").read_text())
    assert action["inputs"]["command"]["default"] == "validate"
    assert action["inputs"]["command"]["required"] is False
    assert action["inputs"]["verify-after-deploy"]["default"] == "true"


@pytest.mark.parametrize("value,flag", [("true", "--verify"), ("false", "--skip-verification"), ("invalid", None)])
def test_action_controls_postcheck_without_changing_deploy_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str, flag: str | None,
) -> None:
    action = yaml.safe_load((Path(__file__).resolve().parents[1] / "action.yml").read_text())
    step = next(step for step in action["runs"]["steps"] if step.get("id") == "run")
    source = step["run"].split("python - <<'PY'\n")[1].split("\nPY\n")[0]
    monkeypatch.setenv("MD_BLUEPRINTS_STDOUT_FILE", str(tmp_path / "stdout"))
    for key in ("ROOT", "TARGET", "BRANCH", "BLUEPRINTS", "ARGS", "DBT"):
        monkeypatch.setenv(f"MD_BLUEPRINTS_{key}", "")
    monkeypatch.setenv("MD_BLUEPRINTS_COMMAND", "deploy")
    monkeypatch.setenv("MD_BLUEPRINTS_VERIFY_AFTER_DEPLOY", value)
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(SystemExit) as result:
        exec(compile(source, "action.yml", "exec"), {})
    if flag:
        assert result.value.code == 0
        assert calls == [["md-blueprints", "deploy", flag]]
    else:
        assert calls == [] and "must be true or false" in str(result.value)


@pytest.mark.parametrize("returncode", [0, 1])
def test_action_passes_named_inputs_literally_and_preserves_exit_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, returncode: int,
) -> None:
    action = yaml.safe_load((Path(__file__).resolve().parents[1] / "action.yml").read_text())
    step = next(step for step in action["runs"]["steps"] if step.get("id") == "run")
    source = step["run"].split("python - <<'PY'\n")[1].split("\nPY\n")[0]
    monkeypatch.setenv("MD_BLUEPRINTS_STDOUT_FILE", str(tmp_path / "stdout"))
    values = {
        "COMMAND": "plan",
        "ARGS": "--target prod --json",
        "TARGET": "preview",
        "ROOT": "customer analytics",
        "BRANCH": 'feature/customer-"quote"-$(literal)',
        "BLUEPRINTS": "orders,revenue",
        "DBT": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(f"MD_BLUEPRINTS_{key}", value)
    received: list[str] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        received.extend(argv)
        assert not kwargs.get("shell")
        cast(TextIO, kwargs["stdout"]).write("plan output\n")
        return subprocess.CompletedProcess(argv, returncode, stdout="plan output\n")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(SystemExit) as result:
        exec(compile(source, "action.yml", "exec"), {})

    assert result.value.code == returncode
    assert received == [
        "md-blueprints", "plan", "--target", "prod", "--json",
        "--root=customer analytics", "--target=preview",
        '--branch=feature/customer-"quote"-$(literal)', "--blueprints=orders,revenue",
    ]
    assert capsys.readouterr().out == "plan output\n"


@pytest.mark.parametrize("returncode", [0, 7])
def test_guide_action_writes_context_file_without_logging_it(tmp_path: Path, returncode: int) -> None:
    root = Path(__file__).resolve().parents[1]
    action = yaml.safe_load((root / "action.yml").read_text())
    step = next(step for step in action["runs"]["steps"] if step.get("id") == "run")
    binary = tmp_path / "md-blueprints"
    prefix = "::error::this is context, not a workflow command\n"
    payload = prefix + "context\n" * 160000
    binary.write_text(
        f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
        "Path(os.environ['TEST_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
        f"sys.stdout.write({prefix!r} + 'context\\n' * 160000)\nsys.exit({returncode})\n"
    )
    binary.chmod(0o755)
    output = tmp_path / "github-output"
    args_file = tmp_path / "argv.json"
    dbt = 'warehouse dbt/"quoted" $(literal)'
    env = {
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(output), "TEST_ARGS": str(args_file),
        "MD_BLUEPRINTS_COMMAND": "guides", "MD_BLUEPRINTS_ARGS": "", "MD_BLUEPRINTS_DBT": dbt,
        "MD_BLUEPRINTS_ROOT": "analytics repo", "MD_BLUEPRINTS_TARGET": "",
        "MD_BLUEPRINTS_BRANCH": "", "MD_BLUEPRINTS_BLUEPRINTS": "",
    }
    result = subprocess.run(["bash", "-c", step["run"]], env=env, text=True, capture_output=True)
    assert result.returncode == returncode
    assert result.stdout == ""
    assert "this is context" not in result.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert set(values) == {"stdout-file"}
    path = Path(values["stdout-file"])
    assert path.name == "guide-context.md"
    assert path.stat().st_size > 1024 * 1024
    assert path.read_text() == payload
    assert json.loads(args_file.read_text()) == ["guides", "--root=analytics repo", f"--dbt={dbt}"]
