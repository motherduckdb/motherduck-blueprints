from __future__ import annotations

from pathlib import Path

from md_blueprints import cli


FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_returns_usage_error_without_command() -> None:
    assert cli.main([]) == 2


def test_cli_returns_usage_error_for_unknown_command() -> None:
    assert cli.main(["unknown", "--root", str(FIXTURES / "simple")]) == 2


def test_cli_returns_zero_for_successful_validate() -> None:
    assert cli.main(["validate", "--root", str(FIXTURES / "simple")]) == 0


def test_cli_returns_one_for_validation_error(tmp_path: Path) -> None:
    assert cli.main(["validate", "--root", str(tmp_path / "missing")]) == 1


def test_cli_render_validates_the_selected_target() -> None:
    assert (
        cli.main(
            [
                "render",
                "--root",
                str(FIXTURES / "invalid-preview"),
                "--target",
                "preview",
                "--branch",
                "feature/invalid",
            ]
        )
        == 1
    )


def test_cli_new_project_creates_valid_typed_package(tmp_path: Path) -> None:
    (tmp_path / "motherduck.yml").write_text(
        """schemaVersion: 1
repository: {name: cli-new}
include: ["projects/**/blueprint.yml"]
targets:
  preview: {mode: preview}
  prod: {mode: production}
variables:
  preview_suffix:
    default: _preview_${target.branch_slug}
""",
        encoding="utf-8",
    )

    assert cli.main(["new", "project", "revenue", "--root", str(tmp_path)]) == 0
    assert (tmp_path / "projects/revenue/blueprint.yml").is_file()


def test_cli_new_dive_rejects_missing_source(tmp_path: Path) -> None:
    (tmp_path / "motherduck.yml").write_text(
        """schemaVersion: 1
repository: {name: cli-new}
include: ["dives/**/blueprint.yml"]
targets:
  preview: {mode: preview}
  prod: {mode: production}
""",
        encoding="utf-8",
    )

    assert cli.main(["new", "dive", "dashboard", "--root", str(tmp_path)]) == 1
