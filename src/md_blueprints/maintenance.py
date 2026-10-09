from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from importlib import util
from pathlib import Path

import yaml
from packaging.version import InvalidVersion, Version

from . import __version__
from .assets import schema_root
from .diagnostics import validation_warnings
from .project import CommandError, Project
from .schema import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS, ValidationError

GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/motherduckdb/motherduck-blueprints/releases/latest"
# Reusable workflows that read MOTHERDUCK_TOKEN, which the calling job must pass.
TOKEN_CALLER = re.compile(
    r"^motherduckdb/motherduck-blueprints/\.github/workflows/"
    r"reusable_(?:deploy|cleanup_preview)_blueprints\.ya?ml@[^\s]+$"
)


def workflows_missing_token_secret(workflow_root: Path) -> list[str]:
    """Workflow files whose reusable deploy or cleanup job passes no secrets."""
    missing: list[str] = []
    for path in sorted(workflow_root.glob("*.y*ml")):
        try:
            workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
        if not isinstance(jobs, dict):
            continue
        if any(
            isinstance(job, dict) and isinstance(job.get("uses"), str)
            and TOKEN_CALLER.fullmatch(job["uses"].strip()) and "secrets" not in job
            for job in jobs.values()
        ):
            missing.append(path.name)
    return missing


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


def newer_release_available(latest_version: str) -> bool:
    try:
        installed = Version(normalize_version(__version__))
        latest = Version(normalize_version(latest_version))
    except InvalidVersion as exc:
        raise ValidationError(f"Could not compare md-blueprints versions: {exc}") from exc
    return latest > installed


def fetch_latest_version(*, offline: bool, offline_hint: str = "Use --offline to skip.") -> str | None:
    """Return the latest release, or None when offline and MD_BLUEPRINTS_LATEST_VERSION is unset.

    Offline mode never opens a network connection.
    """
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
        raise ValidationError(f"Could not check latest md-blueprints release: {exc}. {offline_hint}") from exc

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
        raise ValidationError(f"motherduck.yml not found in {root}")

    try:
        project = Project(root)
        project.validate()
    except (ValidationError, CommandError) as exc:
        lines.append(f"validation: failed ({exc})")
        emit_lines(lines, output_format=output_format)
        raise

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
    for warning in validation_warnings(project):
        lines.append(f"warning: {warning}")

    for warning in project.deployment_warnings():
        lines.append(f"warning: {warning}")

    authoritative = authoritative_resources(project)
    if authoritative:
        lines.append(
            "warning: mode: authoritative revokes role members, included roles, or share grants that are not "
            "declared in Blueprints, including grants managed elsewhere such as the MotherDuck Terraform "
            "provider's motherduck_role_grant or motherduck_share_grant. Use mode: additive unless Blueprints "
            "is the only owner: " + ", ".join(authoritative)
        )

    workflow_root = root / ".github" / "workflows"
    if (workflow_root / "deploy_blueprints.yaml").is_file() and not any(
        (workflow_root / name).is_file() for name in ("prepare_guide_context.yaml", "prepare_guide_context.yml")
    ):
        lines.append(
            "info: .github/workflows/prepare_guide_context.yaml is not present. Generated templates include it from "
            "v0.7.0 to prepare Guide context in CI as an artifact for an agent runner. To adopt it, copy it from a "
            "template generated with md-blueprints init in an empty directory"
        )

    missing_token = workflows_missing_token_secret(workflow_root)
    if missing_token:
        lines.append(
            "warning: " + ", ".join(missing_token) + " call the reusable deploy or cleanup workflow without passing "
            "MOTHERDUCK_TOKEN. GitHub gives the reusable job an empty string instead of the environment secret, so "
            "previews, deploys, and cleanup fail. Run make upgrade, or add `secrets: MOTHERDUCK_TOKEN: "
            "${{ secrets.MOTHERDUCK_TOKEN }}` to the calling job"
        )

    workflow = root / ".github" / "workflows" / "deploy_blueprints.yaml"
    if workflow.is_file():
        workflow_text = workflow.read_text(encoding="utf-8")
        reusable_deploy = (
            "motherduckdb/motherduck-blueprints/.github/workflows/reusable_deploy_blueprints.yaml@"
            in workflow_text
        )
        if "md-blueprints-environment-model: v1" not in workflow_text:
            lines.append(
                "warning: deploy workflow does not use target-declared GitHub Environments; the repository-level "
                "MOTHERDUCK_TOKEN workflow is deprecated"
            )
        if (
            project.has_target("staging") and not reusable_deploy
            and 'target = "staging" if staging_enabled else "prod"' not in workflow_text
        ):
            lines.append(
                "warning: staging is configured but the default-branch workflow does not select staging"
            )
        if (
            project.has_target("staging") and not reusable_deploy
            and "github.event_name == 'release'" not in workflow_text
        ):
            lines.append(
                "warning: staging is configured but production is not deployed from a published GitHub Release"
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
    pin_status, pin_mismatch = tooling_pin_status(root)
    lines.append(f"tooling pins: {pin_status}")

    if check_updates:
        latest_version = fetch_latest_version(offline=offline)
        if latest_version is None:
            lines.append("latest md-blueprints: unknown (offline mode)")
        else:
            lines.append(f"latest md-blueprints: {latest_version}")
            if newer_release_available(latest_version):
                emit_lines(lines, output_format=output_format)
                raise ValidationError(
                    f"md-blueprints {__version__} is older than release {latest_version}; bump the action pin"
                )
            if Version(normalize_version(__version__)) > Version(latest_version):
                lines.append("version status: ahead of latest release")

    emit_lines(lines, output_format=output_format)
    if pin_mismatch and check_updates:
        raise ValidationError("Generated repository action and CLI pins are not aligned; update both to the same release")
    if stale_schema and check_updates:
        raise ValidationError("Project schema is supported but not latest; run md-blueprints migrate --to latest")


def authoritative_resources(project: Project) -> list[str]:
    """Roles and share grants rendered with mode: authoritative for any target."""
    found: set[str] = set()
    for target in project.target_names():
        branch = "feature/doctor" if target == "preview" else None
        for blueprint in project.render_all(target, branch=branch):
            for key, role in blueprint.roles.items():
                if role.get("mode") == "authoritative" and role.get("deploy", True):
                    found.add(f"{blueprint.name} roles.{key}")
            for key, share in blueprint.shares.items():
                grants = share.get("grants")
                if isinstance(grants, dict) and grants.get("mode") == "authoritative":
                    found.add(f"{blueprint.name} shares.{key}.grants")
    return sorted(found)


def run_check_updates(*, offline: bool = False, output_format: str = "text") -> None:
    lines = [f"installed md-blueprints: {__version__}"]
    latest_version = fetch_latest_version(offline=offline)
    if latest_version is None:
        lines.append("latest md-blueprints: unknown (offline mode)")
        emit_lines(lines, output_format=output_format)
        return

    lines.append(f"latest md-blueprints: {latest_version}")
    emit_lines(lines, output_format=output_format)
    if newer_release_available(latest_version):
        raise ValidationError(f"md-blueprints {__version__} is older than release {latest_version}")


def schema_mirror_status(root: Path) -> str:
    schema_dir = root / "schemas"
    if not schema_dir.is_dir():
        return "not present"

    package_schema_root = schema_root()
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


def tooling_pin_status(root: Path) -> tuple[str, bool]:
    makefile = root / "Makefile"
    if not makefile.is_file():
        return "not present", False

    match = re.search(r"^CLI_VERSION\s*:?=\s*([^\s#]+)", makefile.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        return "managed by the local checkout", False

    cli_version = match.group(1)
    workflow_root = root / ".github" / "workflows"
    action_versions: set[str] = set()
    if workflow_root.is_dir():
        for workflow in workflow_root.glob("*.y*ml"):
            action_versions.update(
                re.findall(
                    r"motherduckdb/motherduck-blueprints(?:/\.github/workflows/[^/@\s]+\.ya?ml)?@(v[^\s\"',}]+)",
                    workflow.read_text(encoding="utf-8"),
                )
            )

    expected_action = f"v{cli_version}"
    mismatch = cli_version != __version__ or action_versions != {expected_action}
    if mismatch:
        rendered = ", ".join(sorted(action_versions)) or "none"
        return (
            f"mismatch (installed {__version__}, Makefile {cli_version}, workflows {rendered})",
            True,
        )
    return f"aligned at {cli_version}", False
