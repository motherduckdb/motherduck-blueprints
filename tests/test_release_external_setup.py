from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from md_blueprints import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_gates_github_publication_on_verified_template() -> None:
    workflow_text = (REPO_ROOT / ".github/workflows/release.yaml").read_text(encoding="utf-8")
    jobs = yaml.safe_load(workflow_text)["jobs"]
    assert '- "v*.*.*"' in workflow_text
    assert jobs["release-preflight"]["needs"] == "build"
    assert set(jobs["publish-template"]["needs"]) == {"build", "release-preflight"}
    assert set(jobs["finalize-release"]["needs"]) == {"build", "publish-template"}
    assert "publish-pypi" not in jobs
    assert "pypa/gh-action-pypi-publish" not in workflow_text
    build_steps = {step.get("name") for step in jobs["build"]["steps"]}
    assert "Publish GitHub Release" not in build_steps
    assert "Generate dependency SBOM" in build_steps
    assert "Attest release artifacts" in build_steps
    steps = jobs["publish-template"]["steps"]
    generate = next(step for step in steps if step.get("name") == "Generate template repository from release wheel")
    assert "release-artifacts/dist/md_blueprints-*.whl" in generate["run"]
    assert any(step.get("name") == "Verify generated template workflow" for step in steps)
    assert jobs["publish-template"]["environment"] == "motherduck-release"
    assert "release-artifacts/dist/*" in workflow_text
    assert "git merge-base --is-ancestor" in workflow_text


def test_release_external_check_accepts_writable_template_repository(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path)
    assert result.returncode == 0
    assert "Template repository OK: motherduckdb/blueprints-template" in result.stdout
    assert "PyPI" not in result.stdout


def test_release_external_check_requires_template_push_permission(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, template_push=False)
    assert result.returncode == 1
    assert "cannot push" in result.stderr
    assert "approve any pending org request" in result.stderr


def test_release_external_check_requires_template_repository_mode(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, is_template=False)
    assert result.returncode == 1
    assert "not marked as a GitHub template repository" in result.stderr


def test_release_version_check_accepts_only_stable_semantic_tags() -> None:
    stable = subprocess.run(
        [str(REPO_ROOT / "scripts/check-release-version.sh"), f"v{__version__}"],
        cwd=REPO_ROOT, text=True, capture_output=True,
    )
    prerelease = subprocess.run(
        [str(REPO_ROOT / "scripts/check-release-version.sh"), f"v{__version__}-rc.1"],
        cwd=REPO_ROOT, text=True, capture_output=True,
    )
    assert stable.returncode == 0
    assert prerelease.returncode == 1
    assert "must match vMAJOR.MINOR.PATCH" in prerelease.stderr


def test_version_availability_check_accepts_unpublished_version(tmp_path: Path) -> None:
    result = run_version_availability_check(tmp_path)
    assert result.returncode == 0
    assert f"Version available for future release: {__version__}" in result.stdout


@pytest.mark.parametrize("existing, message", [("release", "GitHub Release"), ("tag", "GitHub tag")])
def test_version_availability_rejects_existing_github_distribution(tmp_path: Path, existing: str, message: str) -> None:
    result = run_version_availability_check(tmp_path, existing=existing)
    assert result.returncode == 1
    assert f"already has a {message}" in result.stderr


@pytest.mark.parametrize("error_at", ["release", "tag"])
def test_version_availability_fails_closed_on_github_errors(tmp_path: Path, error_at: str) -> None:
    result = run_version_availability_check(tmp_path, error_at=error_at)
    assert result.returncode == 1
    assert "Could not verify GitHub" in result.stderr


def run_release_external_check(
    tmp_path: Path, *, template_push: bool = True, is_template: bool = True,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text('''#!/usr/bin/env bash
set -euo pipefail
if [ "${GH_TOKEN:-}" != "template-token" ]; then
  echo "missing GH_TOKEN" >&2
  exit 2
fi
if [ "$1" != "api" ] || [ "$2" != "repos/motherduckdb/blueprints-template" ]; then
  echo "unexpected gh invocation: $*" >&2
  exit 2
fi
printf '{"is_template":%s,"permissions":{"push":%s}}' "${GH_IS_TEMPLATE}" "${GH_TEMPLATE_PUSH}"
''', encoding="utf-8")
    gh.chmod(0o755)
    return subprocess.run(
        [str(REPO_ROOT / "scripts/check-release-external-setup.sh")], cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TEMPLATE_PUSH_TOKEN": "template-token",
             "GH_TEMPLATE_PUSH": str(template_push).lower(), "GH_IS_TEMPLATE": str(is_template).lower(),
             "PYPI_JSON_BASE_URL": "http://127.0.0.1:1/unavailable"},
        text=True, capture_output=True,
    )


def run_version_availability_check(
    tmp_path: Path, *, existing: str = "", error_at: str = "",
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text('''#!/usr/bin/env bash
set -euo pipefail
case "$2" in
  */releases/tags/v*) kind=release ;;
  */git/ref/tags/v*) kind=tag ;;
  *) echo "unexpected GitHub endpoint" >&2; exit 2 ;;
esac
if [ "$kind" = "$GH_ERROR_AT" ]; then
  echo 'gh: Service unavailable (HTTP 503)' >&2
  exit 1
fi
if [ "$kind" = "$GH_EXISTING" ]; then
  printf '{}\\n'
else
  echo 'gh: Not Found (HTTP 404)' >&2
  exit 1
fi
''', encoding="utf-8")
    gh.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text("#!/usr/bin/env bash\necho 'Registry access is not part of GitHub releases' >&2\nexit 2\n")
    curl.chmod(0o755)
    return subprocess.run(
        [str(REPO_ROOT / "scripts/check-version-available.sh")], cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "GH_EXISTING": existing, "GH_ERROR_AT": error_at},
        text=True, capture_output=True,
    )
