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
