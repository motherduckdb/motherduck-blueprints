from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


def test_action_defaults_to_validation() -> None:
    action = yaml.safe_load((Path(__file__).resolve().parents[1] / "action.yml").read_text())
    assert action["inputs"]["command"]["default"] == "validate"
    assert action["inputs"]["command"]["required"] is False


@pytest.mark.parametrize("returncode", [0, 1])
def test_action_passes_named_inputs_literally_and_preserves_exit_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], returncode: int,
) -> None:
    action = yaml.safe_load((Path(__file__).resolve().parents[1] / "action.yml").read_text())
    step = next(step for step in action["runs"]["steps"] if step.get("id") == "run")
    source = step["run"].split("python - <<'PY' | tee \"$stdout_file\"\n")[1].split("\nPY\n")[0]
    values = {
        "COMMAND": "plan",
        "ARGS": "--target prod --json",
        "TARGET": "preview",
        "ROOT": "customer analytics",
        "BRANCH": 'feature/customer-"quote"-$(literal)',
        "BLUEPRINTS": "orders,revenue",
    }
    for key, value in values.items():
        monkeypatch.setenv(f"MD_BLUEPRINTS_{key}", value)
    received: list[str] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        received.extend(argv)
        assert not kwargs.get("shell")
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
