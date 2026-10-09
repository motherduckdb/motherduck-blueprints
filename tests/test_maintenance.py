from __future__ import annotations

from pathlib import Path

import pytest
from packaging.version import Version

from md_blueprints import __version__
from md_blueprints.init import run_init
from md_blueprints.maintenance import run_check_updates, run_doctor, tooling_pin_status
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


def test_generated_repository_tooling_pins_are_aligned(tmp_path: Path) -> None:
    run_init(tmp_path)

    assert tooling_pin_status(tmp_path) == (f"aligned at {__version__}", False)


def test_doctor_rejects_action_and_cli_pin_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_init(tmp_path)
    workflow = tmp_path / ".github/workflows/deploy_blueprints.yaml"
    workflow.write_text(workflow.read_text(encoding="utf-8").replace(f"@v{__version__}", "@v0.0.0"), encoding="utf-8")
    monkeypatch.setenv("MD_BLUEPRINTS_LATEST_VERSION", __version__)

    with pytest.raises(ValidationError, match="action and CLI pins are not aligned"):
        run_doctor(tmp_path, check_updates=True)


def test_doctor_warns_about_legacy_repository_secret_workflow(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_init(tmp_path)
    workflow = tmp_path / ".github/workflows/deploy_blueprints.yaml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("# md-blueprints-environment-model: v1\n", ""),
        encoding="utf-8",
    )

    run_doctor(tmp_path)

    assert "repository-level MOTHERDUCK_TOKEN workflow is deprecated" in capsys.readouterr().out


def test_doctor_warns_when_target_environment_metadata_is_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_doctor(FIXTURES / "medium")

    output = capsys.readouterr().out
    assert "target 'preview' does not declare a GitHub Environment" in output
    assert "target 'prod' does not document deployment.identity" in output


def test_doctor_warns_about_noncanonical_environment_secret_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_doctor(FIXTURES / "simple")

    assert "generated GitHub Environment workflows require the canonical secret name" in capsys.readouterr().out


def test_doctor_warns_about_staging_workflow_routing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_init(tmp_path)
    manifest = tmp_path / "motherduck.yml"
    manifest_text = manifest.read_text(encoding="utf-8")
    manifest_text = manifest_text.replace(
        "environment: motherduck-production",
        "environment: motherduck-staging",
        1,
    ).replace(
        "identity: GitHub Actions production service account",
        "identity: GitHub Actions staging service account",
        1,
    )
    manifest_text = manifest_text.replace(
        "  prod:\n",
        """  staging:
    mode: production
    environment: motherduck-staging
    deployment:
      tokenEnvVar: MOTHERDUCK_TOKEN
      identity: GitHub Actions staging service account

  prod:
""",
    )
    manifest.write_text(manifest_text, encoding="utf-8")
    run_doctor(tmp_path)
    healthy_output = capsys.readouterr().out
    assert "default-branch workflow does not select staging" not in healthy_output
    assert "production is not deployed from a published GitHub Release" not in healthy_output
    workflow = tmp_path / ".github/workflows/deploy_blueprints.yaml"
    workflow.write_text(
        (Path(__file__).resolve().parents[1] / ".github/workflows/deploy_blueprints.yaml").read_text(encoding="utf-8")
        .replace('target = "staging" if staging_enabled else "prod"', 'target = "prod"')
        .replace("github.event_name == 'release'", "github.event_name == 'disabled-release'"),
        encoding="utf-8",
    )

    run_doctor(tmp_path)

    output = capsys.readouterr().out
    assert "default-branch workflow does not select staging" in output
    assert "production is not deployed from a published GitHub Release" in output


def test_doctor_warns_about_authoritative_roles_and_share_grants(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    from md_blueprints.scaffold import run_new

    run_init(tmp_path)
    role = run_new(tmp_path, "role", "analysts") / "blueprint.yml"
    role.write_text(role.read_text().replace("mode: additive", "mode: authoritative"))
    producer = tmp_path / "flights/wikipedia-pageviews-ingest/blueprint.yml"
    producer.write_text(producer.read_text().replace(
        "      cleanup: true\n",
        "      cleanup: true\n      grants:\n        roles: [analysts]\n        mode: authoritative\n", 1,
    ))

    run_doctor(tmp_path)

    output = capsys.readouterr().out
    assert "motherduck_role_grant or motherduck_share_grant" in output
    assert "wikipedia-pageviews-ingest shares." in output
    # The scaffolded role is disabled, so it cannot revoke anything yet.
    assert "analysts roles.role" not in output
    role.write_text(role.read_text().replace("deploy: false", "deploy: true"))
    run_doctor(tmp_path)
    assert "analysts roles.role" in capsys.readouterr().out


def test_doctor_points_existing_repositories_to_guide_context_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    run_init(tmp_path)
    run_doctor(tmp_path)
    assert "prepare_guide_context.yaml is not present" not in capsys.readouterr().out
    (tmp_path / ".github/workflows/prepare_guide_context.yaml").unlink()
    run_doctor(tmp_path)
    assert "info: .github/workflows/prepare_guide_context.yaml is not present" in capsys.readouterr().out


def test_doctor_warns_when_reusable_callers_do_not_pass_the_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    run_init(tmp_path)
    run_doctor(tmp_path)
    assert "without passing MOTHERDUCK_TOKEN" not in capsys.readouterr().out
    # Callers generated before 0.7.8 passed no secrets.
    workflows = tmp_path / ".github/workflows"
    for name in ("deploy_blueprints.yaml", "cleanup_preview_blueprints.yaml"):
        path = workflows / name
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "    secrets:\n      MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}\n", ""
            ),
            encoding="utf-8",
        )
    run_doctor(tmp_path)
    assert (
        "warning: cleanup_preview_blueprints.yaml, deploy_blueprints.yaml call the reusable deploy or cleanup "
        "workflow without passing MOTHERDUCK_TOKEN"
    ) in capsys.readouterr().out
    path = workflows / "deploy_blueprints.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("    with:\n", "    secrets: inherit\n    with:\n", 1),
        encoding="utf-8",
    )
    run_doctor(tmp_path)
    assert "warning: cleanup_preview_blueprints.yaml call" in capsys.readouterr().out


def test_offline_update_checks_never_open_a_connection(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import urllib.request

    monkeypatch.delenv("MD_BLUEPRINTS_LATEST_VERSION", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network used offline"))
    run_check_updates(offline=True)
    run_doctor(FIXTURES / "simple", check_updates=True, offline=True)
    assert "latest md-blueprints: unknown (offline mode)" in capsys.readouterr().out
