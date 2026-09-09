"""MotherDuck's bundled runtime for live SQL, with no shell interpolation."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen

from .project import CommandError


SUPPORTED_VERSION = "v1.5.5-2026-09-35"


def executable() -> str | None:
    found = shutil.which("motherduck")
    if found:
        return found
    installed = Path.home() / ".motherduck/bin/motherduck"
    return str(installed) if installed.is_file() and os.access(installed, os.X_OK) else None


def sql_backend() -> str:
    backend = os.environ.get("MD_BLUEPRINTS_SQL_BACKEND", "auto")
    if backend not in {"auto", "motherduck", "duckdb"}:
        raise CommandError("MD_BLUEPRINTS_SQL_BACKEND must be auto, motherduck, or duckdb")
    return ("motherduck" if executable() else "duckdb") if backend == "auto" else backend


def install_cli() -> None:
    """Use the official installer, which verifies the pinned binary's checksum."""
    found = executable()
    if found:
        result = subprocess.run([found, "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip() == SUPPORTED_VERSION:
            print(f"MotherDuck CLI {SUPPORTED_VERSION} is installed at {found}")
            return
    if os.name == "nt":
        raise CommandError("Install the MotherDuck CLI with the official PowerShell installer on Windows.")
    with tempfile.TemporaryDirectory(prefix="md-blueprints-install-") as directory:
        script = Path(directory) / "install.sh"
        with urlopen("https://install.motherduck.com", timeout=30) as response:
            script.write_bytes(response.read())
        env = {
            **os.environ,
            "MOTHERDUCK_VERSION": SUPPORTED_VERSION,
            "SKIP_DUCKDB_CLI": "1",
            "MOTHERDUCK_NONINTERACTIVE": "1",
        }
        # Installation must not authenticate, query, or reuse deployment credentials.
        for key in ("MOTHERDUCK_TOKEN", "motherduck_token", "SKIP_MOTHERDUCK_CLI", "MD_API_HOST"):
            env.pop(key, None)
        result = subprocess.run(["sh", str(script)], env=env, text=True, check=False)
        if result.returncode:
            raise CommandError("MotherDuck CLI installer failed. See its output above.")
    installed = Path.home() / ".motherduck/bin/motherduck"
    result = subprocess.run([str(installed), "--version"], capture_output=True, text=True, check=False)
    if result.returncode or result.stdout.strip() != SUPPORTED_VERSION:
        raise CommandError(f"MotherDuck CLI installation did not produce {SUPPORTED_VERSION}")
    if executable() != str(installed) and executable() != str(installed.resolve()):
        raise CommandError(f"Another MotherDuck CLI shadows {installed}. Put its directory first on PATH.")


def query_rows(statement: str, *, token: str | None) -> list[tuple[object, ...]]:
    binary = executable()
    if not binary:
        raise CommandError("MotherDuck CLI is required. Run make install-deploy or md-blueprints install-cli.")
    with tempfile.TemporaryDirectory(prefix="md-blueprints-query-") as directory:
        sql_file = Path(directory) / "query.sql"
        sql_file.write_text(statement, encoding="utf-8")
        env = dict(os.environ)
        if token is not None:
            env["MOTHERDUCK_TOKEN"] = token
            env.pop("motherduck_token", None)
            # Token-driven automation must not fall back to a person's saved login.
            env.setdefault("MOTHERDUCK_HOME", str(Path(directory) / "home"))
        if "MOTHERDUCK_HOME" in env and not Path(env["MOTHERDUCK_HOME"]).is_absolute():
            raise CommandError("MOTHERDUCK_HOME must be an absolute path")
        try:
            result = subprocess.run(
                [binary, "query", "--file", str(sql_file), "--output", "json"],
                env=env, capture_output=True, text=True, check=False,
            )
        except OSError as exc:
            raise CommandError("Could not start the MotherDuck CLI. Run make install-deploy.") from exc
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        if token:
            message = message.replace(token, "[redacted]")
        message = message.replace(statement, "[SQL omitted]")
        raise CommandError(f"MotherDuck SQL failed: {message}")
    # The native CLI emits one JSON array per result-producing statement.
    # Consume the whole stream and return its last result. DDL emits no array.
    remaining = result.stdout.strip()
    rows: list[tuple[object, ...]] = []
    decoder = json.JSONDecoder()
    while remaining:
        try:
            data, end = decoder.raw_decode(remaining)
        except json.JSONDecodeError as exc:
            raise CommandError("MotherDuck CLI returned invalid JSON") from exc
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise CommandError("MotherDuck CLI query must return JSON arrays of rows")
        rows = [tuple(row.values()) for row in data]
        remaining = remaining[end:].lstrip()
    return rows
