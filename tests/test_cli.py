from __future__ import annotations

from pathlib import Path

import pytest

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


@pytest.mark.parametrize("selection", ["", " ", ", ,"])
def test_cli_rejects_empty_explicit_selection(selection: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["deploy", "--blueprints", selection]) == 1
    assert "must contain at least one blueprint name" in capsys.readouterr().err


def test_doctor_returns_failure_for_invalid_resources(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor", "--root", str(FIXTURES / "invalid-preview"), "--offline"]) == 1
    output = capsys.readouterr().out
    assert "validation: failed" in output
    assert "validation: passed" not in output


def test_doctor_returns_failure_for_missing_manifest(tmp_path: Path) -> None:
    assert cli.main(["doctor", "--root", str(tmp_path), "--offline"]) == 1


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


def test_deploy_rejects_dry_run_before_contacting_motherduck(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("md_blueprints.deploy.Deployer.deploy", lambda *a, **kw: pytest.fail("deploy must not run"))
    assert cli.main(["deploy", "--root", str(FIXTURES / "simple"), "--dry-run"]) == 2
    assert "deploy does not support --dry-run; use `plan` to preview changes" in capsys.readouterr().err


@pytest.mark.parametrize("args,message", [
    (["init", "DIR", "--write"], "init does not support --write"),
    (["init", "DIR", "--json"], "init does not support --json"),
    (["validate", "--dry-run"], "validate does not support --dry-run"),
    (["changed", "--target", "prod"], "changed does not support --target. Run md-blueprints changed --help"),
    (["validate", "unexpected"], "unexpected argument 'unexpected' for validate"),
    (["cleanup", "--json"], "cleanup --json requires --dry-run"),
    (["import", "--blueprints", "x"], "import selects remote UUIDs: use --resource KIND:UUID"),
])
def test_commands_reject_flags_they_do_not_support(
    args: list[str], message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    args = [str(tmp_path / "init-target") if arg == "DIR" else arg for arg in args]
    root = [] if args[0] == "init" else ["--root", str(FIXTURES / "simple")]
    assert cli.main([*args, *root]) == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "init-target").exists()


def test_new_rejects_dry_run_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "motherduck.yml").write_text(
        'schemaVersion: 1\nrepository: {name: cli-new}\ninclude: ["flights/**/blueprint.yml"]\n'
        "targets:\n  preview: {mode: preview}\n  prod: {mode: production}\n",
        encoding="utf-8",
    )
    assert cli.main(["new", "flight", "events", "--root", str(tmp_path), "--dry-run"]) == 2
    assert "new does not support --dry-run" in capsys.readouterr().err
    assert not (tmp_path / "flights").exists()


def test_validate_rejects_unknown_blueprint_selection(capsys: pytest.CaptureFixture[str]) -> None:
    root = str(FIXTURES / "simple")
    assert cli.main(["validate", "--root", root, "--blueprints", "does-not-exist"]) == 1
    assert "Unknown blueprint(s): does-not-exist. Valid names: simple-dive" in capsys.readouterr().err
    assert cli.main(["validate", "--root", root, "--blueprints", "simple-dive"]) == 0


def test_command_help_lists_only_that_commands_options(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["deploy", "--help"]) == 0
    output = capsys.readouterr().out
    assert "--skip-verification" in output and "--blueprints" in output
    assert "--dry-run" not in output and "--dbt" not in output


def test_unknown_command_is_reported_before_project_lookup(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["valdiate", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "unknown command 'valdiate'" in err
    assert "motherduck.yml" not in err


def test_options_before_the_command_remain_supported() -> None:
    assert cli.main(["--root", str(FIXTURES / "simple"), "validate"]) == 0


def test_key_errors_explain_the_missing_value(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def missing(options: object) -> None:
        raise KeyError("database")

    monkeypatch.setitem(cli.HANDLERS, "validate", missing)
    assert cli.main(["validate"]) == 1
    err = capsys.readouterr().err
    assert "Missing required value 'database'" in err
    assert "Error: 'database'" not in err


def test_validate_warns_about_legacy_context_and_undiscovered_packages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    import shutil

    shutil.copytree(FIXTURES / "simple", tmp_path, dirs_exist_ok=True)
    stray = tmp_path / "blueprints/team/nested-dive"
    shutil.copytree(tmp_path / "blueprints/simple-dive", stray)
    assert cli.main(["validate", "--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert "Validation passed" in captured.out
    assert (
        "warning: blueprints/team/nested-dive/blueprint.yml is not matched by the include patterns in "
        'motherduck.yml, so it is not validated or deployed; add "blueprints/**/blueprint.yml" to include'
    ) in captured.err

    assert cli.main(["validate", "--root", str(FIXTURES / "complex")]) == 0
    assert "warning: resources.context is supported for compatibility" in capsys.readouterr().err
