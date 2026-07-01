from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from importlib import resources, util
from pathlib import Path

from . import __version__
from .project import CommandError, Project
from .schema import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS, ValidationError

GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/motherduckdb/motherduck-blueprints/releases/latest"


def emit_lines(lines: list[str], *, output_format: str) -> None:
    if output_format == "github-summary":
        print("## MotherDuck Blueprints Doctor")
        print()
        for line in lines:
            print(f"- {line}")
        return

    for line in lines:
        print(line)


def normalize_version(value: str) -> str:
    return value.strip().removeprefix("v")


def fetch_latest_version(*, offline: bool) -> str | None:
    configured_latest = os.environ.get("MD_BLUEPRINTS_LATEST_VERSION", "").strip()
    if configured_latest:
        return normalize_version(configured_latest)
    if offline:
        return None

    request = urllib.request.Request(
        GITHUB_LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"md-blueprints/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Could not check latest md-blueprints release: {exc}. Use --offline to skip.") from exc

    tag_name = payload.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name.strip():
        raise ValidationError("Could not check latest md-blueprints release: GitHub response did not include tag_name")
    return normalize_version(tag_name)


def run_doctor(
    root: Path,
    *,
    output_format: str = "text",
    check_updates: bool = False,
    offline: bool = False,
) -> None:
    lines = [
        f"md-blueprints version: {__version__}",
        f"supported schema versions: {', '.join(str(version) for version in sorted(SUPPORTED_SCHEMA_VERSIONS))}",
        f"latest packaged schema version: {LATEST_SCHEMA_VERSION}",
        f"project root: {root.resolve()}",
        f"duckdb Python package: {'available' if util.find_spec('duckdb') else 'not installed'}",
    ]

    root_manifest = root / "motherduck.yml"
    if not root_manifest.is_file():
        lines.append("project manifest: missing")
        emit_lines(lines, output_format=output_format)
        return

    try:
        project = Project(root)
    except (ValidationError, CommandError) as exc:
        lines.append(f"validation: failed ({exc})")
        emit_lines(lines, output_format=output_format)
        return

    root_version = project.manifest.get("schemaVersion")
    root_schema_version = root_version if isinstance(root_version, int) and not isinstance(root_version, bool) else -1
    blueprint_versions = sorted(
        version
        for version in {blueprint.raw.get("schemaVersion") for blueprint in project.blueprints}
        if isinstance(version, int) and not isinstance(version, bool)
    )
    lines.extend(
        [
            f"root schemaVersion: {root_version}",
            f"blueprint schemaVersions: {', '.join(str(version) for version in blueprint_versions)}",
            f"blueprints discovered: {len(project.blueprints)}",
            "validation: passed",
        ]
    )

    stale_schema = False
    unsupported = {root_schema_version, *blueprint_versions} - SUPPORTED_SCHEMA_VERSIONS
    if unsupported:
        lines.append(f"unsupported schemaVersions: {', '.join(str(version) for version in sorted(unsupported))}")
        stale_schema = True
    elif root_schema_version != LATEST_SCHEMA_VERSION or any(
        version != LATEST_SCHEMA_VERSION for version in blueprint_versions
    ):
        lines.append("schema status: supported but not latest")
        stale_schema = True
    else:
        lines.append("schema status: latest supported schema")

    lines.append(f"repo schema mirror: {schema_mirror_status(root)}")

    if check_updates:
        latest_version = fetch_latest_version(offline=offline)
        if latest_version is None:
            lines.append("latest md-blueprints: unknown (offline mode)")
        else:
            lines.append(f"latest md-blueprints: {latest_version}")
            if normalize_version(__version__) != latest_version:
                emit_lines(lines, output_format=output_format)
                raise ValidationError(
                    f"md-blueprints {__version__} is not the latest release {latest_version}; bump the action pin"
                )

    emit_lines(lines, output_format=output_format)
    if stale_schema and check_updates:
        raise ValidationError("Project schema is supported but not latest; run md-blueprints migrate --to latest")


def run_check_updates(*, offline: bool = False, output_format: str = "text") -> None:
    lines = [f"installed md-blueprints: {__version__}"]
    latest_version = fetch_latest_version(offline=offline)
    if latest_version is None:
        lines.append("latest md-blueprints: unknown (offline mode)")
        emit_lines(lines, output_format=output_format)
        return

    lines.append(f"latest md-blueprints: {latest_version}")
    emit_lines(lines, output_format=output_format)
    if normalize_version(__version__) != latest_version:
        raise ValidationError(f"md-blueprints {__version__} is not the latest release {latest_version}")


def schema_mirror_status(root: Path) -> str:
    schema_dir = root / "schemas"
    if not schema_dir.is_dir():
        return "not present"

    package_schema_root = resources.files("md_blueprints").joinpath("schemas")
    mismatched: list[str] = []
    for version in sorted(SUPPORTED_SCHEMA_VERSIONS):
        for name in ["motherduck-root.schema.json", "blueprint.schema.json"]:
            local_path = schema_dir / f"v{version}" / name
            if not local_path.is_file():
                mismatched.append(f"v{version}/{name} missing")
                continue
            packaged = package_schema_root.joinpath(f"v{version}", name).read_text(encoding="utf-8").strip()
            local = local_path.read_text(encoding="utf-8").strip()
            if packaged != local:
                mismatched.append(f"v{version}/{name} differs")

    return "in sync with packaged schemas" if not mismatched else "; ".join(mismatched)
