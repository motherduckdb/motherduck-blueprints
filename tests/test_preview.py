from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("template", ["Makefile", "src/md_blueprints/template_repo/Makefile"])
@pytest.mark.parametrize("command", ["preview", "preview-smoke"])
def test_preview_keeps_existing_source_when_selection_fails(tmp_path: Path, template: str, command: str) -> None:
    repository = Path(__file__).resolve().parents[1]
    shutil.copyfile(repository / template, tmp_path / "Makefile")
    source = tmp_path / ".dive-preview/src/dive.tsx"
    source.parent.mkdir(parents=True)
    original = "export default function ExistingDive() { return null; }\n"
    source.write_text(original, encoding="utf-8")

    result = subprocess.run(
        ["make", "-o", "false", "CLI=false", command, "missing-blueprint"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert source.read_text(encoding="utf-8") == original
    assert "npm" not in result.stdout


def test_template_help_groups_targets_and_plan_passes_its_selection(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    shutil.copyfile(repository / "src/md_blueprints/template_repo/Makefile", tmp_path / "Makefile")

    def make(*args: str) -> str:
        return subprocess.run(
            ["make", "-o", "cli", "NO_COLOR=1", *args], cwd=tmp_path, capture_output=True, text=True, check=True,
        ).stdout

    listing = make("help")
    assert "\nCheck against MotherDuck (read-only, needs the target's MOTHERDUCK_TOKEN)\n  plan " in listing
    assert listing.index("\nSet up\n") < listing.index("\nCreate packages\n") < listing.index("\nMaintain\n")
    assert "##" not in listing

    assert '.venv/bin/md-blueprints plan  --branch "feature/x" --blueprints "sales"' in make(
        "-n", "plan", "BRANCH=feature/x", "NAME=sales"
    )
    assert '.venv/bin/md-blueprints verify --target "staging"' in make("-n", "verify", "TARGET=staging")
    assert make("-n", "plan").rstrip().endswith("md-blueprints plan")
