from pathlib import Path
import subprocess
import sys

import pytest

from md_blueprints.init import run_init
from md_blueprints.schema import ValidationError
from md_blueprints.upgrade import run_upgrade, update_action_pins


def test_upgrade_preserves_reusable_workflow_paths_and_unrelated_actions() -> None:
    text = (
        "jobs:\n  deploy:\n"
        "    uses: 'motherduckdb/motherduck-blueprints/.github/workflows/reusable_deploy_blueprints.yaml@v0.4.3' # keep\n"
        "  other:\n    uses: another/repo/.github/workflows/deploy.yml@v1\n"
    )
    updated, count = update_action_pins(text, "1.2.3")
    assert count == 1
    assert updated == text.replace("@v0.4.3", "@v1.2.3")


def test_inline_action_pin_and_comment_are_preserved() -> None:
    text = "steps:\n  - {uses: 'motherduckdb/motherduck-blueprints@v0', with: {command: validate}} # keep\n"
    updated, count = update_action_pins(text, "1.2.3")
    assert count == 1
    assert updated == text.replace("@v0", "@v1.2.3")


def test_upgrade_preserves_yaml_anchors() -> None:
    text = "steps:\n  - uses: &blueprints motherduckdb/motherduck-blueprints@v0\n  - uses: *blueprints\n"
    updated, count = update_action_pins(text, "1.2.3")
    assert count == 1
    assert updated == text.replace("@v0", "@v1.2.3")


def test_invalid_workflow_does_not_partially_upgrade(tmp_path: Path) -> None:
    run_init(tmp_path)
    before = (tmp_path / "Makefile").read_bytes()
    (tmp_path / ".github/workflows/broken.yml").write_text("steps: [")
    with pytest.raises(ValidationError, match="Invalid workflow YAML"):
        run_upgrade(tmp_path, to_version="1.2.3", write=True)
    assert (tmp_path / "Makefile").read_bytes() == before


def test_upgrade_previews_then_updates_only_tooling_pins(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_init(tmp_path)
    workflow = tmp_path / ".github/workflows/custom.yml"
    workflow.write_text(
        "steps:\n  - uses: 'motherduckdb/motherduck-blueprints@v0.1.0' # pinned\n"
        "    with:\n      blueprints: revenue\n  - uses: actions/checkout@v7\n"
    )
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    run_upgrade(tmp_path, to_version="1.2.3")
    assert {path: path.read_bytes() for path in before} == before
    assert "+CLI_VERSION := 1.2.3" in capsys.readouterr().out
    run_upgrade(tmp_path, to_version="1.2.3", write=True)
    assert workflow.read_text() == (
        "steps:\n  - uses: 'motherduckdb/motherduck-blueprints@v1.2.3' # pinned\n"
        "    with:\n      blueprints: revenue\n  - uses: actions/checkout@v7\n"
    )
    for path, content in before.items():
        if path.name != "Makefile" and ".github/workflows" not in str(path):
            assert path.read_bytes() == content
    run_upgrade(tmp_path, to_version="1.2.3", write=True)
    assert "already aligned" in capsys.readouterr().out


def test_upgrade_rejects_external_workflow_before_any_write(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    run_init(root)
    outside = tmp_path / "external.yml"
    outside.write_text("steps:\n  - uses: motherduckdb/motherduck-blueprints@v0.1.0\n")
    (root / ".github/workflows/extra.yml").symlink_to(outside)
    original = (root / "Makefile").read_bytes()
    with pytest.raises(ValidationError, match="must stay within"):
        run_upgrade(root, to_version="1.2.3", write=True)
    assert (root / "Makefile").read_bytes() == original


def test_upgrade_resolves_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_init(tmp_path)
    monkeypatch.setattr("md_blueprints.upgrade.fetch_latest_version", lambda **kwargs: "1.2.3")
    run_upgrade(tmp_path, write=True)
    assert "CLI_VERSION := 1.2.3" in (tmp_path / "Makefile").read_text()


def test_latest_does_not_downgrade_an_unreleased_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_init(tmp_path)
    before = (tmp_path / "Makefile").read_bytes()
    monkeypatch.setattr("md_blueprints.upgrade.fetch_latest_version", lambda **kwargs: "0.0.1")
    run_upgrade(tmp_path, write=True)
    assert (tmp_path / "Makefile").read_bytes() == before


def test_customer_make_upgrade_prepares_pins_with_one_command(tmp_path: Path) -> None:
    run_init(tmp_path)
    cli = Path(sys.executable).parent / "md-blueprints"
    result = subprocess.run(
        ["make", f"CLI={cli}", "upgrade", "VERSION=1.2.3"],
        cwd=tmp_path, text=True, capture_output=True, check=True,
    )
    assert "+CLI_VERSION := 1.2.3" in result.stdout
    assert "Updated tooling pins" in result.stdout
    assert "CLI_VERSION := 1.2.3" in (tmp_path / "Makefile").read_text()
