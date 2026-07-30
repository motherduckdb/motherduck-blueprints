from __future__ import annotations

from pathlib import Path

import pytest
from packaging.version import Version

from md_blueprints import __version__
from md_blueprints.maintenance import run_check_updates, run_doctor
from md_blueprints.schema import ValidationError


FIXTURES = Path(__file__).parent / "fixtures"


def test_check_updates_accepts_installed_version_ahead_of_latest(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    earlier = "0.0.0"
    monkeypatch.setenv("MD_BLUEPRINTS_LATEST_VERSION", earlier)

    run_check_updates()

    assert f"latest md-blueprints: {earlier}" in capsys.readouterr().out


def test_check_updates_rejects_newer_release(monkeypatch: pytest.MonkeyPatch) -> None:
    installed = Version(__version__)
    newer = f"{installed.major}.{installed.minor + 1}.0"
    monkeypatch.setenv("MD_BLUEPRINTS_LATEST_VERSION", newer)

    with pytest.raises(ValidationError, match=f"older than release {newer}"):
        run_check_updates()


def test_doctor_reports_ahead_version_without_requesting_upgrade(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    earlier = "0.0.0"
    monkeypatch.setenv("MD_BLUEPRINTS_LATEST_VERSION", earlier)

    run_doctor(FIXTURES / "simple", check_updates=True)

    output = capsys.readouterr().out
    assert f"latest md-blueprints: {earlier}" in output
    assert "version status: ahead of latest release" in output
