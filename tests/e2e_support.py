"""Helpers for end-to-end tests that drive the installed md-blueprints CLI as a subprocess.

Live commands run against tests/fixtures/fake_motherduck, the same fake runtime that
scripts/mock-test.sh uses. The subprocess environment drops every MotherDuck, GitHub, and CI
variable from the caller, points MOTHERDUCK_HOME at a temporary directory, and loads a network
guard, so no test can reach a real account, a saved login, or the GitHub API.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
FAKE_MOTHERDUCK = FIXTURES / "fake_motherduck"
CLI = Path(sys.executable).parent / "md-blueprints"
TOKEN = "fake-local-only-token"
STARTER = ["wikipedia-pageviews-ingest", "wikipedia-pageviews"]

# Statements that change a MotherDuck account. Reads never match.
MUTATION = re.compile(
    r"MD_CREATE_|MD_UPDATE_|MD_DELETE_|MD_RUN_FLIGHT|MD_DROP_DATABASE_SHARE|MD_SET_GUIDE_ACCESS"
    r"|DROP DATABASE|CREATE ROLE|^\s*(GRANT|REVOKE) |ALTER SHARE",
    flags=re.MULTILINE,
)
_SCRUBBED_PREFIXES = (
    "MOTHERDUCK_", "MD_BLUEPRINTS_", "MD_API_", "GITHUB_", "MOCK_", "TARGET_", "FLIGHT_RUN_", "SHARE_RESOLVE_",
)
_SCRUBBED = {"CI", "DBT", "PYTHONPATH", "RUNNER_TEMP"}


@dataclass
class Result:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    def json(self) -> Any:
        return json.loads(self.stdout)

    def __str__(self) -> str:
        return f"md-blueprints {' '.join(self.args)} -> {self.returncode}\n--- stdout\n{self.stdout}\n--- stderr\n{self.stderr}"


class FakeMotherDuck:
    """The fake account: seed state.json, then read back what md-blueprints sent."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        state_dir.mkdir(parents=True, exist_ok=True)

    def state(self) -> dict[str, Any]:
        path = self.state_dir / "state.json"
        state: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
        return state

    def seed(self, **values: Any) -> None:
        state = self.state()
        state.update(values)
        (self.state_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

    def queries(self) -> list[str]:
        path = self.state_dir / "queries.jsonl"
        if not path.exists():
            return []
        return [str(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]

    def mutations(self) -> list[str]:
        return [query for query in self.queries() if MUTATION.search(query)]

    def clear_log(self) -> None:
        for name in ("queries.log", "queries.jsonl"):
            (self.state_dir / name).unlink(missing_ok=True)

    def ids(self, kind: str) -> dict[str, str]:
        """Map each live Flight name, Dive title, or Guide title to its ID."""
        field = "name" if kind == "flights" else "title"
        return {str(resource[field]): resource_id for resource_id, resource in self.state().get(kind, {}).items()}


class Cli:
    """Run the installed md-blueprints entry point the way a customer or CI job would."""

    def __init__(self, tmp_path: Path, fake: FakeMotherDuck) -> None:
        self.fake = fake
        self.home = tmp_path / "motherduck-home"
        self.home.mkdir(exist_ok=True)

    def env(self, *, token: bool = True, **extra: str) -> dict[str, str]:
        env = {
            key: value for key, value in os.environ.items()
            if key not in _SCRUBBED and not key.upper().startswith(_SCRUBBED_PREFIXES)
        }
        env.update({
            # A separate HOME hides ~/.motherduck, so a real CLI or saved login is never found.
            "HOME": str(self.home),
            "MOTHERDUCK_HOME": str(self.home / ".motherduck"),
            "MD_BLUEPRINTS_SQL_BACKEND": "duckdb",
            "PYTHONPATH": str(FAKE_MOTHERDUCK),
            "PYTHONDONTWRITEBYTECODE": "1",
            "MOCK_DUCKDB_STATE_DIR": str(self.fake.state_dir),
            "SHARE_RESOLVE_ATTEMPTS": "1",
            "SHARE_RESOLVE_SLEEP_SECONDS": "0",
            "FLIGHT_RUN_POLL_ATTEMPTS": "1",
            "FLIGHT_RUN_POLL_SLEEP_SECONDS": "0",
        })
        if token:
            env["MOTHERDUCK_TOKEN"] = TOKEN
        env.update(extra)
        return env

    def run(
        self, *args: str, cwd: Path | None = None, token: bool = True, env: dict[str, str] | None = None,
        **variables: str,
    ) -> Result:
        completed = subprocess.run(
            [str(CLI), *args], cwd=cwd, env=self.env(token=token, **(env or {}), **variables),
            capture_output=True, text=True, check=False, timeout=120,
        )
        return Result(args, completed.returncode, completed.stdout, completed.stderr)

    def ok(
        self, *args: str, cwd: Path | None = None, token: bool = True, env: dict[str, str] | None = None,
        **variables: str,
    ) -> Result:
        result = self.run(*args, cwd=cwd, token=token, env=env, **variables)
        assert result.returncode == 0, str(result)
        return result

    def fails(
        self, *args: str, code: int = 1, cwd: Path | None = None, token: bool = True,
        env: dict[str, str] | None = None, **variables: str,
    ) -> Result:
        result = self.run(*args, cwd=cwd, token=token, env=env, **variables)
        assert result.returncode == code, str(result)
        return result


def git(repo: Path, *args: str) -> str:
    """Run git with no user or system configuration, so signing and hooks never apply."""
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "E2E", "GIT_AUTHOR_EMAIL": "e2e@example.test",
        "GIT_COMMITTER_NAME": "E2E", "GIT_COMMITTER_EMAIL": "e2e@example.test",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True,
    ).stdout.strip()


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def edit_yaml(path: Path, change: Any) -> None:
    """Load a manifest, let `change` mutate it in place, and write it back."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def records(result: Result) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Index `plan --json` or `verify --json` output by (blueprint, type, key)."""
    return {(row["blueprint"], row["type"], row["key"]): row for row in result.json()}


# -- import snapshots ----------------------------------------------------------------------

OWNER = "owner@example.test"
IMPORT_IDS = {kind: str(UUID(int=index)) for index, kind in enumerate(("flight", "dive", "guide"), 1)}


def import_snapshot() -> list[dict[str, Any]]:
    """One live Flight, Dive, and Guide as `md-blueprints import --snapshot` reads them."""
    flight = {
        "kind": "flight",
        "metadata": {
            "flight_id": IMPORT_IDS["flight"], "flight_name": "Existing pipeline", "owner_name": OWNER,
            "current_version": 3, "schedule_cron": "0 * * * *", "schedule_status": "SCHEDULE_STATUS_DISABLED",
            "status": "JOB_STATUS_ACTIVE", "updated_at": "2026-09-06",
        },
        "content": {
            "flight_id": IMPORT_IDS["flight"], "flight_version": 3, "source_code": "print('unchanged')\n",
            "requirements_txt": "requests==2.32.0\n", "config": {"DATABASE": "existing_db", "PASSWORD": "do-not-print"},
            "flight_secret_names": ["vendor-key"], "access_token_name": "runtime-token", "max_runtime_sec": 600,
        },
    }
    dive = {
        "kind": "dive",
        "metadata": {
            "id": IMPORT_IDS["dive"], "title": "Existing dashboard", "description": "Keep this", "owner_name": OWNER,
            "current_version": 4, "status": "endorsed", "updated_at": "2026-09-06",
        },
        "content": {
            "version": 4, "api_version": 1, "content": "export default function Dive() { return null; }\n",
            "required_resources": [{"url": "md:_share/data/original", "alias": "revenue", "resource_type": "share"}],
        },
    }
    guide_meta = {
        "id": IMPORT_IDS["guide"], "title": "Existing definitions", "description": "", "topic": "finance",
        "owner_name": OWNER, "current_version": 5, "version": 5, "access": "organization",
        "content": "# Revenue\n\nOriginal definition.\n", "updated_at": "2026-09-06",
        "references": [{"type": "dive", "dive_id": IMPORT_IDS["dive"], "flight_id": None, "guide_id": None}],
    }
    return [flight, dive, {"kind": "guide", "metadata": guide_meta, "content": guide_meta}]
