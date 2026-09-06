from pathlib import Path

import pytest

from md_blueprints.cli import main
from md_blueprints.diagnostics import report_error
from md_blueprints.init import run_init
from md_blueprints.deploy import Deployer


def test_missing_token_reports_exact_environment_in_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_init(tmp_path)
    summary = tmp_path / "summary.md"
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main(["deploy", "--root", str(tmp_path)]) == 1
    text = summary.read_text()
    assert "motherduck-production" in text
    assert "Next:" in text
    assert "service-account read/write token" in text


def test_missing_upstream_data_reaches_action_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_init(tmp_path)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "fake-journey-token")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(Deployer, "_find_share_url", lambda self, name: "")
    monkeypatch.setattr(Deployer, "_list_dive_states", lambda self, name: [])
    assert main(["plan", "--root", str(tmp_path), "--target", "prod", "--blueprints", "wikipedia-pageviews"]) == 1
    assert "deploy producer &#x27;wikipedia-pageviews-ingest&#x27; to the same target first" in summary.read_text()


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
