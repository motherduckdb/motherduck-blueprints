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
