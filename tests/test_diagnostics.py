from pathlib import Path

import pytest

from md_blueprints.diagnostics import report_error, validation_warnings


@pytest.mark.parametrize("message,advice", [
    ("permission denied", "service account's permissions"),
    ("authentication failed", "replace MOTHERDUCK_TOKEN"),
    ("environment must match", "check targets in motherduck.yml"),
])
def test_errors_have_safe_actionable_summaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], message: str, advice: str,
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "private-test-token")
    report_error(ValueError(message + " <script>private-test-token</script>"))
    stderr = capsys.readouterr().err
    assert advice in stderr
    assert "private-test-token" not in stderr + summary.read_text()
    assert "<script>" not in summary.read_text()


@pytest.mark.parametrize("message", [
    "Unknown template reference ${var.environment}",
    "Required file not found: dives/environment-report/src/dive.tsx",
    "[Errno 13] Permission denied: 'dives/report/blueprint.yml'",
    "MotherDuck rejected MOTHERDUCK_TOKEN.\nNext: create a new token. Permission denied.",
])
def test_unrelated_errors_get_no_generic_hint(capsys: pytest.CaptureFixture[str], message: str) -> None:
    report_error(ValueError(message))
    assert capsys.readouterr().err.count("Next:") == message.count("Next:")


def test_short_settings_are_not_redacted(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "private-test-token")
    report_error(ValueError("runOnDeploy must be boolean; got false with private-test-token"))
    stderr = capsys.readouterr().err
    assert "got false" in stderr
    assert "private-test-token" not in stderr


@pytest.mark.parametrize("requirements,warned", [
    ("pytz>=2024.1\n", True),
    ("duckdb==1.5.6\npytz>=2024.1\n", False),
    ("DuckDB[all] >= 1.5  # pinned below\n", False),
    ("-r shared.txt\n", False),
])
def test_validation_warns_when_a_flight_imports_duckdb_without_installing_it(
    tmp_path: Path, requirements: str, warned: bool,
) -> None:
    from md_blueprints.init import run_init
    from md_blueprints.project import Project

    run_init(tmp_path)
    (tmp_path / "flights/wikipedia-pageviews-ingest/src/requirements.txt").write_text(requirements, encoding="utf-8")
    warnings = validation_warnings(Project(tmp_path))
    found = [warning for warning in warnings if "No module named 'duckdb'" in warning]
    assert bool(found) is warned
    if warned:
        assert found[0].startswith("flights/wikipedia-pageviews-ingest/src/requirements.txt:")
        assert found[0].endswith("Add duckdb==1.5.6")
