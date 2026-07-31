from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import yaml

from md_blueprints import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_gates_all_distribution_channels() -> None:
    workflow_text = (REPO_ROOT / ".github/workflows/release.yaml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    assert '- "v*.*.*"' in workflow_text
    assert jobs["release-preflight"]["needs"] == "build"
    assert set(jobs["publish-template"]["needs"]) == {"build", "release-preflight"}
    assert set(jobs["publish-pypi"]["needs"]) == {"build", "release-preflight", "publish-template"}
    assert set(jobs["finalize-release"]["needs"]) == {"build", "publish-template", "publish-pypi"}
    build_steps = {step.get("name") for step in jobs["build"]["steps"]}
    assert "Publish GitHub Release" not in build_steps
    assert "Generate dependency SBOM" in build_steps
    assert "Attest release artifacts" in build_steps

    publish_template_steps = jobs["publish-template"]["steps"]
    generate_step = next(
        step for step in publish_template_steps if step.get("name") == "Generate template repository from release wheel"
    )
    assert "release-artifacts/dist/md_blueprints-*.whl" in generate_step["run"]
    assert any(step.get("name") == "Verify generated template workflow" for step in publish_template_steps)
    assert jobs["publish-template"]["environment"] == "motherduck-release"
    assert jobs["publish-pypi"]["environment"] == "pypi"
    assert "release-artifacts/dist/*" in workflow_text
    assert "git merge-base --is-ancestor" in workflow_text


def test_release_external_check_accepts_writable_template_repository(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, pypi_status=200)

    assert result.returncode == 0
    assert "Template repository OK: motherduckdb/blueprints-template" in result.stdout
    assert "PyPI project OK: md-blueprints" in result.stdout


def test_release_external_check_accepts_pending_pypi_publisher(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, pypi_status=404)

    assert result.returncode == 0
    assert "pending trusted publisher" in result.stdout


def test_release_external_check_requires_template_push_permission(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, pypi_status=200, template_push=False)

    assert result.returncode == 1
    assert "cannot push" in result.stderr
    assert "approve any pending org request" in result.stderr


def test_release_external_check_requires_template_repository_mode(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, pypi_status=200, is_template=False)

    assert result.returncode == 1
    assert "not marked as a GitHub template repository" in result.stderr


def test_release_external_check_can_require_registered_pypi_project(tmp_path: Path) -> None:
    result = run_release_external_check(
        tmp_path,
        pypi_status=404,
        extra_env={"ALLOW_PYPI_PENDING_PUBLISHER": "0"},
    )

    assert result.returncode == 1
    assert "Register a pending trusted publisher" in result.stderr


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


def test_version_availability_check_accepts_unpublished_version(tmp_path: Path) -> None:
    result = run_version_availability_check(tmp_path, github_release_exists=False, pypi_release_exists=False)

    assert result.returncode == 0
    assert f"Version available for future release: {__version__}" in result.stdout


def test_version_availability_check_rejects_existing_github_release(tmp_path: Path) -> None:
    result = run_version_availability_check(tmp_path, github_release_exists=True, pypi_release_exists=False)

    assert result.returncode == 1
    assert "already has a GitHub Release" in result.stderr


def test_version_availability_check_rejects_existing_pypi_release(tmp_path: Path) -> None:
    result = run_version_availability_check(tmp_path, github_release_exists=False, pypi_release_exists=True)

    assert result.returncode == 1
    assert "already published on PyPI" in result.stderr


def run_release_external_check(
    tmp_path: Path,
    *,
    pypi_status: int,
    template_push: bool = True,
    is_template: bool = True,
    extra_env: dict[str, str] | None = None,
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

    with pypi_server(pypi_status) as base_url:
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TEMPLATE_PUSH_TOKEN": "template-token",
            "GH_TEMPLATE_PUSH": "true" if template_push else "false",
            "GH_IS_TEMPLATE": "true" if is_template else "false",
            "PYPI_JSON_BASE_URL": base_url,
        }
        if extra_env is not None:
            env.update(extra_env)
        return subprocess.run(
            [str(REPO_ROOT / "scripts/check-release-external-setup.sh")],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def run_version_availability_check(
    tmp_path: Path,
    *,
    github_release_exists: bool,
    pypi_release_exists: bool,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "version-bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        + ("printf '{}\\n'\n" if github_release_exists else "echo 'gh: Not Found (HTTP 404)' >&2\nexit 1\n"),
        encoding="utf-8",
    )
    gh.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text(
        f"#!/usr/bin/env bash\nprintf '{200 if pypi_release_exists else 404}'\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)

    return subprocess.run(
        [str(REPO_ROOT / "scripts/check-version-available.sh")],
        cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@contextlib.contextmanager
def pypi_server(status: int) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/md-blueprints/json":
                self.send_error(404)
                return
            self.send_response(status)
            self.end_headers()
            if status == 200:
                self.wfile.write(json.dumps({"info": {"name": "md-blueprints"}}).encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
