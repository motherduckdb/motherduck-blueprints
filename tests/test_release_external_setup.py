from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_external_check_accepts_existing_pypi_project(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, pypi_status=200)

    assert result.returncode == 0
    assert "Template repository OK: motherduckdb/blueprints-template" in result.stdout
    assert "PyPI project OK: md-blueprints" in result.stdout


def test_release_external_check_accepts_pending_pypi_publisher(tmp_path: Path) -> None:
    result = run_release_external_check(tmp_path, pypi_status=404)

    assert result.returncode == 0
    assert "PyPI project 'md-blueprints' is not registered yet" in result.stdout
    assert "pending trusted publisher" in result.stdout


def test_release_external_check_can_require_registered_pypi_project(tmp_path: Path) -> None:
    result = run_release_external_check(
        tmp_path,
        pypi_status=404,
        extra_env={"ALLOW_PYPI_PENDING_PUBLISHER": "0"},
    )

    assert result.returncode == 1
    assert "Register a pending trusted publisher" in result.stderr


def run_release_external_check(
    tmp_path: Path,
    *,
    pypi_status: int,
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
printf '{"is_template":true}'
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)

    with pypi_server(pypi_status) as base_url:
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TEMPLATE_PUSH_TOKEN": "template-token",
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
