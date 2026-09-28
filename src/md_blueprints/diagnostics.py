from __future__ import annotations

import html
import os
import sys
from pathlib import Path

from .project import Project

PACKAGE_ROOTS = ("flights", "dives", "guides", "roles", "projects", "blueprints")
SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build"}


def legacy_context_blueprints(project: Project) -> list[str]:
    names = []
    for blueprint in project.blueprints:
        resources_node = blueprint.raw.get("resources")
        if isinstance(resources_node, dict) and resources_node.get("context"):
            names.append(blueprint.name)
    return names


def undiscovered_manifests(project: Project) -> list[str]:
    """blueprint.yml files below package roots that motherduck.yml include globs do not match."""
    include = project.manifest.get("include")
    roots = set(PACKAGE_ROOTS)
    for pattern in include if isinstance(include, list) else []:
        parts = Path(str(pattern)).parts
        if len(parts) > 1 and not any(char in parts[0] for char in "*?["):
            roots.add(parts[0])
    discovered = {blueprint.path.resolve() for blueprint in project.blueprints}
    found: list[str] = []
    for name in sorted(roots):
        base = project.root / name
        if not base.is_dir() or base.is_symlink():
            continue
        for directory, dirs, files in os.walk(base):
            dirs[:] = sorted(item for item in dirs if not item.startswith(".") and item not in SKIP_DIRS)
            path = Path(directory) / "blueprint.yml"
            if "blueprint.yml" in files and not path.is_symlink() and path.resolve() not in discovered:
                found.append(path.relative_to(project.root).as_posix())
    return sorted(found)


def validation_warnings(project: Project) -> list[str]:
    """Non-fatal findings shared by validate and doctor."""
    warnings: list[str] = []
    legacy = legacy_context_blueprints(project)
    if legacy:
        warnings.append(
            "resources.context is supported for compatibility; prefer resources.guides in: " + ", ".join(legacy)
        )
    for relative in undiscovered_manifests(project):
        top = relative.split("/", 1)[0]
        warnings.append(
            f"{relative} is not matched by the include patterns in motherduck.yml, so it is not validated or "
            f'deployed; add "{top}/**/blueprint.yml" to include'
        )
    return warnings


def report_error(error: Exception) -> None:
    message = str(error)
    for key, value in os.environ.items():
        if value and any(part in key.upper() for part in ("TOKEN", "PASSWORD", "SECRET", "API_KEY")):
            message = message.replace(value, "[redacted]")
    lower = message.lower()
    if "environment" in lower and "next:" not in lower:
        message += (
            "\nNext: check targets in motherduck.yml. The environment name must match GitHub Settings > "
            "Environments and the workflow job's environment. Set deployment.identity to the service account "
            "and deployment.tokenEnvVar to MOTHERDUCK_TOKEN."
        )
    if any(text in lower for text in ("permission denied", "access denied", "insufficient privilege", "not authorized")):
        message += (
            "\nNext: check the service account's permissions on the required databases. "
            "For custom roles or organization-wide Guides, use an admin deployment identity."
        )
    elif any(text in lower for text in ("invalid token", "expired token", "authentication failed", "unauthorized")):
        message += (
            "\nNext: replace MOTHERDUCK_TOKEN in the job's GitHub Environment with a valid "
            "service-account read/write token, then rerun the failed job."
        )
    print(f"Error: {message}", file=sys.stderr)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with Path(summary).open("a", encoding="utf-8") as handle:
                handle.write(f"### Blueprints needs attention\n\n<pre>{html.escape(message)}</pre>\n\n")
        except OSError:
            print("Could not write the GitHub Actions summary; see the error above.", file=sys.stderr)
