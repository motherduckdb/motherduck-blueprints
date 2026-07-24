from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from md_blueprints import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_publishes_action_only_after_template_publish() -> None:
    workflow_text = (REPO_ROOT / ".github/workflows/release.yaml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    assert '- "v*.*.*"' in workflow_text
    assert jobs["release-preflight"]["needs"] == "build"
    assert set(jobs["publish-template"]["needs"]) == {"build", "release-preflight"}
    assert jobs["finalize-release"]["needs"] == "publish-template"
    assert "publish-pypi" not in jobs
    build_steps = {step.get("name") for step in jobs["build"]["steps"]}
    assert "Publish GitHub Release" not in build_steps

    publish_template_steps = jobs["publish-template"]["steps"]
    generate_step = next(step for step in publish_template_steps if step.get("name") == "Generate template repository")
    assert "python -m pip install ." in generate_step["run"]
    assert "dist/" not in generate_step["run"]


def test_release_external_check_accepts_writable_template_repository(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path)

    assert result.returncode == 0
    assert "Template repository OK: motherduckdb/blueprints-template" in result.stdout


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
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    prerelease = subprocess.run(
        [str(REPO_ROOT / "scripts/check-release-version.sh"), f"v{__version__}-rc.1"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert stable.returncode == 0
    assert prerelease.returncode == 1
    assert "must match vMAJOR.MINOR.PATCH" in prerelease.stderr


def run_release_external_check(
    tmp_path: Path,
    *,
    template_push: bool = True,
    is_template: bool = True,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
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
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TEMPLATE_PUSH_TOKEN": "template-token",
        "GH_TEMPLATE_PUSH": "true" if template_push else "false",
        "GH_IS_TEMPLATE": "true" if is_template else "false",
    }
    return subprocess.run(
        [str(REPO_ROOT / "scripts/check-release-external-setup.sh")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
