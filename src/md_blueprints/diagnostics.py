from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

from .deploy import required_databases_export, role_name_problem, strip_required_databases_export
from .project import Project
from .schema import ValidationError

PACKAGE_ROOTS = ("flights", "dives", "guides", "roles", "projects", "blueprints")
SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build"}
ENVIRONMENT_ERROR = re.compile(r"targets\.[\w-]+\.environment\b|github environment|environment must match|declare environment")


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


def misnamed_manifests(project: Project) -> list[str]:
    """Manifests named blueprint.yaml or with different letter case. Only blueprint.yml is discovered on
    case-sensitive filesystems such as Linux CI runners."""
    found: list[str] = []
    for name in PACKAGE_ROOTS:
        base = project.root / name
        if not base.is_dir() or base.is_symlink():
            continue
        for directory, dirs, files in os.walk(base):
            dirs[:] = sorted(item for item in dirs if not item.startswith(".") and item not in SKIP_DIRS)
            found.extend(
                (Path(directory) / item).relative_to(project.root).as_posix()
                for item in files
                if item.lower() in {"blueprint.yml", "blueprint.yaml"} and item != "blueprint.yml"
            )
    return sorted(found)


def role_name_warnings(project: Project) -> list[str]:
    """Role names MotherDuck refuses to create. plan stops on them; validate can say so without a token."""
    warnings: list[str] = []
    for blueprint in project.blueprints:
        roles = blueprint.raw.get("resources")
        roles = roles.get("roles") if isinstance(roles, dict) else None
        for key, role in (roles.items() if isinstance(roles, dict) else []):
            name = role.get("name") if isinstance(role, dict) else None
            if isinstance(name, str) and "${" not in name and (problem := role_name_problem(name)):
                path = blueprint.path.relative_to(project.root).as_posix()
                warnings.append(
                    f"{path}: roles.{key}.name {name!r} {problem}, so plan stops before creating it "
                    "unless the role already exists"
                )
    return warnings


def dive_source_warnings(project: Project) -> list[str]:
    """REQUIRED_DATABASES problems that plan and deploy stop on, or that make the preview differ from MotherDuck."""
    target = next((name for name in project.target_names() if name != "preview"), None)
    if target is None:
        return []
    warnings: list[str] = []
    for blueprint in project.render_all(target):
        for key, dive in blueprint.dives.items():
            if dive.get("deploy") is False:
                continue
            label = f"{dive['sourcePath']}".removeprefix(f"{project.root}/")
            try:
                source = Path(str(dive["sourcePath"])).read_text(encoding="utf-8")
                strip_required_databases_export(source)
                found = required_databases_export(source)
            except (OSError, UnicodeDecodeError):
                continue
            except ValidationError as exc:
                warnings.append(f"{label}: {exc}, so plan and deploy stop before any write for {blueprint.name}.{key}")
                continue
            if found is None or not isinstance(found[2], list):
                continue
            exported = sorted({str(item.get("alias")) for item in found[2] if isinstance(item, dict)})
            resources = dive.get("requiredResources")
            declared = sorted({
                str(item.get("alias")) for item in resources if isinstance(item, dict)
            } if isinstance(resources, list) else set())
            if exported != declared:
                warnings.append(
                    f"{label}: REQUIRED_DATABASES aliases ({', '.join(exported) or 'none'}) differ from "
                    f"requiredResources in {blueprint.name}.dives.{key} ({', '.join(declared) or 'none'}), so the "
                    "local preview and the deployed Dive see different databases; use the same aliases in both"
                )
    return warnings


def validation_warnings(project: Project) -> list[str]:
    """Non-fatal findings shared by validate and doctor."""
    warnings: list[str] = role_name_warnings(project) + dive_source_warnings(project)
    legacy = legacy_context_blueprints(project)
    if legacy:
        warnings.append(
            "resources.context is supported for compatibility; prefer resources.guides in: " + ", ".join(legacy)
        )
    for relative in misnamed_manifests(project):
        warnings.append(
            f"{relative} is not read: Blueprints reads only files named exactly blueprint.yml, so this package "
            "is not validated or deployed in CI; rename the file to blueprint.yml"
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
    # Add a hint only when the error carries none and clearly matches its cause. A bare word such as
    # "environment" in a path or variable name, or a local file permission error, gets no hint.
    has_next = "next:" in lower
    local_file_error = "[errno" in lower
    if not has_next and ENVIRONMENT_ERROR.search(lower):
        message += (
            "\nNext: check targets in motherduck.yml. The environment name must match GitHub Settings > "
            "Environments and the workflow job's environment. Set deployment.identity to the service account "
            "and deployment.tokenEnvVar to MOTHERDUCK_TOKEN."
        )
    if has_next or local_file_error:
        pass
    elif any(text in lower for text in ("permission denied", "access denied", "insufficient privilege", "not authorized")):
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
