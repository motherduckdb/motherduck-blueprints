from __future__ import annotations

import io
import subprocess
import os
import json
import sys
from pathlib import Path
from typing import Any

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
    monkeypatch.setattr(subprocess, "Popen", fake_popen(calls, b"", 0))
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
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", fake_popen(calls, b"plan output\n", returncode))
    with pytest.raises(SystemExit) as result:
        exec(compile(source, "action.yml", "exec"), {})

    assert result.value.code == returncode
    assert (tmp_path / "stdout").read_text() == "plan output\n"
    assert len(calls) == 1
    assert calls[0] == [
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


def fake_popen(calls: list[list[str]], stdout: bytes, returncode: int) -> Any:
    class FakePopen:
        def __init__(self, argv: list[str], **kwargs: Any) -> None:
            calls.append(argv)
            assert not kwargs.get("shell")
            assert kwargs["stdout"] is subprocess.PIPE
            assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"
            self.stdout = io.BufferedReader(io.BytesIO(stdout))
            self.returncode = returncode

        def __enter__(self) -> FakePopen:
            return self

        def __exit__(self, *args: object) -> None:
            self.stdout.close()

    return FakePopen


def action_step(step_id: str) -> dict[str, Any]:
    action = yaml.safe_load((Path(__file__).resolve().parents[1] / "action.yml").read_text())
    step: dict[str, Any] = next(step for step in action["runs"]["steps"] if step.get("id") == step_id)
    return step


@pytest.mark.parametrize("returncode", [0, 3])
def test_action_streams_output_before_exit_and_captures_it(tmp_path: Path, returncode: int) -> None:
    step = action_step("run")
    release = tmp_path / "release"
    binary = tmp_path / "md-blueprints"
    # The fake CLI does not flush, so live output also proves PYTHONUNBUFFERED is passed through.
    binary.write_text(
        f"#!{sys.executable}\nimport sys, time\nfrom pathlib import Path\n"
        "sys.stdout.write('planning started\\n')\n"
        f"deadline = time.time() + 20\nwhile not Path({str(release)!r}).exists():\n"
        "    if time.time() > deadline:\n        sys.exit(99)\n    time.sleep(0.05)\n"
        f"sys.stdout.write('plan finished\\n')\nsys.exit({returncode})\n"
    )
    binary.chmod(0o755)
    output = tmp_path / "github-output"
    env = {
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(output),
        "MD_BLUEPRINTS_COMMAND": "plan", "MD_BLUEPRINTS_ARGS": "", "MD_BLUEPRINTS_DBT": "",
        "MD_BLUEPRINTS_ROOT": "", "MD_BLUEPRINTS_TARGET": "prod", "MD_BLUEPRINTS_BRANCH": "",
        "MD_BLUEPRINTS_BLUEPRINTS": "", "MD_BLUEPRINTS_BIN": "",
    }
    env.pop("PYTHONUNBUFFERED", None)
    process = subprocess.Popen(["bash", "-c", step["run"]], env=env, stdout=subprocess.PIPE, text=True)
    assert process.stdout is not None
    try:
        assert process.stdout.readline() == "planning started\n"
    finally:
        release.touch()
    rest = process.stdout.read()
    assert process.wait(timeout=30) == returncode
    assert rest == "plan finished\n"
    values = output.read_text()
    stdout_file = Path(values.split("stdout-file=", 1)[1].splitlines()[0])
    assert stdout_file.read_text() == "planning started\nplan finished\n"
    assert "planning started\nplan finished\n" in values.split("stdout<<", 1)[1]


def test_action_installs_into_isolated_environment() -> None:
    step = action_step("install")
    script = step["run"]
    pip_lines = [line.strip() for line in script.splitlines() if "pip install" in line]
    assert pip_lines and all(line.startswith('"$venv_python" -m pip install') for line in pip_lines)
    assert 'python -m venv "$venv"' in script
    assert '"${RUNNER_TEMP}/md-blueprints-action/' in script
    assert 'ln -sf "${venv_bin}/${name}" "${link_dir}/${name}"' in script
    assert 'echo "$link_dir" >> "$GITHUB_PATH"' in script
    action = yaml.safe_load((Path(__file__).resolve().parents[1] / "action.yml").read_text())
    assert action["outputs"]["python"]["value"] == "${{ steps.install.outputs.python }}"
    run_env = action_step("run")["env"]
    assert run_env["MD_BLUEPRINTS_BIN"] == "${{ steps.install.outputs.bin }}"
