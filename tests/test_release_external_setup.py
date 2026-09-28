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
    assert set(jobs["finalize-release"]["needs"]) == {"build", "release-preflight", "publish-template"}
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
    assert "md-blueprints validate" in generate["run"]
    assert generate["run"].index("md-blueprints init") < generate["run"].index("md-blueprints validate")


@pytest.mark.parametrize("tag, latest, latest_in_major", [
    ("v1.1.0", "true", "true"),
    ("v0.8.0", "false", "true"),
    ("v0.6.1", "false", "false"),
])
def test_older_release_lines_do_not_move_template_main_or_floating_tag(
    tmp_path: Path, tag: str, latest: str, latest_in_major: str,
) -> None:
    jobs = yaml.safe_load((REPO_ROOT / ".github/workflows/release.yaml").read_text(encoding="utf-8"))["jobs"]
    order = next(step for step in jobs["release-preflight"]["steps"] if step.get("id") == "order")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for existing in ("v0", "v0.6.0", "v0.7.0", "v0.7.0-rc1", "v1", "v1.0.0", tag):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", existing],
            cwd=tmp_path, check=True,
        )
        subprocess.run(["git", "tag", existing], cwd=tmp_path, check=True)
    output = tmp_path / "outputs"
    subprocess.run(
        ["bash", "-c", order["run"]], cwd=tmp_path, check=True, capture_output=True,
        env={**os.environ, "GITHUB_REF_NAME": tag, "GITHUB_OUTPUT": str(output)},
    )
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values == {"latest": latest, "latest-in-major": latest_in_major}
    assert jobs["release-preflight"]["outputs"]["latest"] == "${{ steps.order.outputs.latest }}"

    template = next(step for step in jobs["publish-template"]["steps"] if step.get("id") == "template")
    assert 'if [ "$LATEST" = "true" ]; then\n  git push origin HEAD:main' in template["run"]
    verify = next(step for step in jobs["publish-template"]["steps"] if step.get("name") == "Verify generated template workflow")
    assert verify["if"] == "needs.release-preflight.outputs.latest == 'true'"
    floating = next(step for step in jobs["finalize-release"]["steps"] if step.get("name") == "Update floating major tag")
    assert floating["if"] == "needs.release-preflight.outputs.latest-in-major == 'true'"
    assert '--latest="$LATEST"' in (REPO_ROOT / ".github/workflows/release.yaml").read_text(encoding="utf-8")


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


def test_release_version_check_accepts_only_stable_semantic_tags(tmp_path: Path) -> None:
    notes = release_notes(tmp_path, f"v{__version__}")
    stable = run_release_version_check(f"v{__version__}", notes)
    prerelease = run_release_version_check(f"v{__version__}-rc.1", notes)
    assert stable.returncode == 0
    assert prerelease.returncode == 1
    assert "must match vMAJOR.MINOR.PATCH" in prerelease.stderr



@pytest.mark.parametrize("full_diff", [
    "**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.0.1...v0.0.2",
    "**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.0.1...v{version}.1",
    "No full diff line",
])
def test_release_version_check_rejects_stale_release_notes(tmp_path: Path, full_diff: str) -> None:
    notes = tmp_path / "RELEASE_NOTES.md"
    notes.write_text("## Highlights\n\n- Something.\n\n" + full_diff.format(version=__version__) + "\n")
    result = run_release_version_check(f"v{__version__}", notes)
    assert result.returncode == 1
    assert f"must end with ...v{__version__}" in result.stderr


def test_release_version_check_requires_release_notes_for_tags(tmp_path: Path) -> None:
    result = run_release_version_check(f"v{__version__}", tmp_path / "missing.md")
    assert result.returncode == 1
    assert "is required to publish" in result.stderr


def test_release_version_check_ignores_notes_without_a_tag(tmp_path: Path) -> None:
    result = run_release_version_check("", tmp_path / "missing.md")
    assert result.returncode == 0
    assert f"Release version OK: {__version__}" in result.stdout


def test_release_workflow_pins_ci_artifact_actions_and_keeps_token_out_of_urls() -> None:
    release = (REPO_ROOT / ".github/workflows/release.yaml").read_text(encoding="utf-8")
    ci = (REPO_ROOT / ".github/workflows/ci.yaml").read_text(encoding="utf-8")
    upload = next(line.split("uses: ", 1)[1] for line in ci.splitlines() if "actions/upload-artifact@" in line)
    uploads = {line.split("uses: ", 1)[1] for line in release.splitlines() if "actions/upload-artifact@" in line}
    downloads = {line.split("uses: ", 1)[1] for line in release.splitlines() if "actions/download-artifact@" in line}
    assert uploads == {upload}
    assert downloads == {"actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131 # v7.0.0"}
    assert "x-access-token:${TEMPLATE_PUSH_TOKEN}@" not in release
    assert 'GIT_CONFIG_KEY_0="http.https://github.com/.extraheader"' in release
    assert 'echo "::add-mask::${auth}"' in release


def release_notes(tmp_path: Path, tag: str) -> Path:
    notes = tmp_path / "RELEASE_NOTES.md"
    notes.write_text(f"## Highlights\n\n**Full diff:** https://example.com/compare/v0.0.1...{tag}\n")
    return notes


def run_release_version_check(tag: str, notes: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO_ROOT / "scripts/check-release-version.sh"), *([tag] if tag else [])],
        cwd=REPO_ROOT, env={**os.environ, "RELEASE_NOTES_FILE": str(notes)}, text=True, capture_output=True,
    )

def test_version_availability_check_accepts_unpublished_version(tmp_path: Path) -> None:
    result = run_version_availability_check(tmp_path)
    assert result.returncode == 0
    assert f"Version available for future release: {__version__}" in result.stdout


@pytest.mark.parametrize("existing, message", [("release", "GitHub Release"), ("tag", "GitHub tag")])
def test_version_availability_rejects_existing_github_distribution(tmp_path: Path, existing: str, message: str) -> None:
    result = run_version_availability_check(tmp_path, existing=existing)
    assert result.returncode == 1
    assert f"already has a {message}" in result.stderr


def test_version_availability_accepts_the_tagged_release_commit(tmp_path: Path) -> None:
    sha = "a" * 40
    result = run_version_availability_check(tmp_path, existing="release", tagged_sha=sha, sha=sha)
    assert result.returncode == 0
    assert f"is the v{__version__} release" in result.stdout


def test_version_availability_rejects_a_tag_on_another_commit(tmp_path: Path) -> None:
    result = run_version_availability_check(tmp_path, existing="tag", tagged_sha="b" * 40, sha="a" * 40)
    assert result.returncode == 1
    assert "already has a GitHub tag" in result.stderr


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
    tmp_path: Path, *, existing: str = "", error_at: str = "", tagged_sha: str = "", sha: str = "",
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text('''#!/usr/bin/env bash
set -euo pipefail
case "$2" in
  */commits/v*)
    if [ -n "$GH_TAGGED_SHA" ]; then printf '%s\\n' "$GH_TAGGED_SHA"; exit 0; fi
    echo 'gh: No commit found for SHA (HTTP 422)' >&2
    exit 1
    ;;
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
        env={
            **os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "GH_EXISTING": existing, "GH_ERROR_AT": error_at,
            "GH_TAGGED_SHA": tagged_sha, "GITHUB_SHA": sha or "0" * 40,
        },
        text=True, capture_output=True,
    )
