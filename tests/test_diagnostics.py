from pathlib import Path

import pytest

from md_blueprints.diagnostics import report_error


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
