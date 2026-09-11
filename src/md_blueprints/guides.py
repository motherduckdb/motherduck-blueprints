"""Refresh a local repository orientation Guide without replacing authored context."""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import cast

import yaml

from .project import Project, RenderedBlueprint, require_within
from .schema import ValidationError


NAME = "repository-overview"
DIRECTORY = Path("guides") / NAME
BEGIN = "<!-- md-blueprints:repository:start -->"
END = "<!-- md-blueprints:repository:end -->"
STATE = ".guide-state.json"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _code(value: object) -> str:
    # Keep manifest text from introducing Markdown headings or managed markers.
    text = " ".join(str(value).split()).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<code>" + text.replace("`", "&#96;") + "</code>"


def _inventory(project: Project) -> tuple[str, dict[str, str]]:
    lines = [
        "## Repository facts", "",
        "These are declarations for the production target, not verified live state. "
        "Check the source and live catalog before relying on a metric or query.", "",
    ]
    sources: dict[str, str] = {}

    def track(path: Path) -> None:
        path = require_within(path, project.root, "Guide input")
        sources[path.relative_to(project.root).as_posix()] = _digest(path.read_bytes())

    track(project.manifest_path)
    raw_by_name = {blueprint.name: blueprint for blueprint in project.blueprints}
    blueprints = sorted(project.render_all("prod"), key=lambda blueprint: blueprint.name)
    for blueprint in blueprints:
        if blueprint.name == NAME:
            continue
        raw = raw_by_name[blueprint.name]
        track(raw.path)
        readme = raw.dir / "README.md"
        if readme.exists():
            track(readme)
        lines.extend([
            f"### {_code(blueprint.title)}", "",
            f"Package: {_code(blueprint.name)}. Manifest: {_code(raw.path.relative_to(project.root))}.", "",
        ])
        if blueprint.description:
            lines.extend([f"Description: {_code(blueprint.description)}", ""])
        for key, contract in sorted(blueprint.inputs.items()):
            lines.append(
                f"- Input {_code(key)} consumes {_code(str(contract['blueprint']) + '.' + str(contract['output']))}."
            )
        for key, contract in sorted(blueprint.outputs.items()):
            lines.append(
                f"- Output {_code(blueprint.name + '.' + key)} publishes share {_code(contract['name'])} "
                f"from database {_code(contract['database'])}."
            )
        _resources(lines, sources, project, blueprint)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", dict(sorted(sources.items()))


def _resources(
    lines: list[str], sources: dict[str, str], project: Project, blueprint: RenderedBlueprint,
) -> None:
    groups = [
        ("Share", blueprint.shares), ("Flight", blueprint.flights), ("Dive", blueprint.dives),
        ("Guide", blueprint.guides), ("Context", blueprint.contexts), ("Role", blueprint.roles),
    ]
    for kind, resources in groups:
        for key, resource in sorted(resources.items()):
            label = resource.get("title", resource.get("name", key))
            details = [f"{kind} {_code(key)}: {_code(label)}"]
            if resource.get("deploy") is False:
                details.append("deployment disabled")
            if kind == "Share":
                details.append(f"database {_code(resource['database'])}")
            if kind == "Flight":
                cron = resource.get("scheduleCron")
                details.append(f"schedule {_code(cron)}" if cron else "no schedule declared")
                if resource.get("manageSchedule") is False:
                    details.append("live schedule is preserved")
            if kind == "Guide":
                details.append(f"topic {_code(resource.get('topic', ''))}")
            for field in ("sourcePath", "requirementsPath"):
                if field in resource:
                    path = require_within(Path(str(resource[field])), project.root, "Guide input")
                    relative = path.relative_to(project.root).as_posix()
                    sources[relative] = _digest(path.read_bytes())
                    details.append(f"{'source' if field == 'sourcePath' else 'requirements'} {_code(relative)}")
            lines.append("- " + ", ".join(details) + ".")
            if kind == "Dive":
                mounts = cast(list[dict[str, object]], resource.get("requiredResources", []))
                for mount in mounts:
                    selector = next(field for field in ("input", "share", "url") if mount.get(field))
                    lines.append(
                        f"  - Mount {_code(mount['alias'])} uses {selector} {_code(mount[selector])}."
                    )


def _safe_path(project: Project, relative: Path) -> Path:
    path = project.root / relative
    require_within(path, project.root, "Generated Guide path")
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != project.root):
        raise ValidationError(f"Generated Guide path must not use symlinks: {relative}")
    return path


def run_guides(root: Path, action: str, *, dry_run: bool = False) -> None:
    if action not in {"init", "update"}:
        raise ValidationError("Usage: md-blueprints guides <init|update> [--dry-run]")
    project = Project(root)
    destination = _safe_path(project, DIRECTORY)
    paths = {name: _safe_path(project, DIRECTORY / name) for name in ("blueprint.yml", "guide.md", "README.md", STATE)}
    existing = destination.exists()
    old_sources: dict[str, str] = {}
    before: dict[str, str] = {}
    if existing:
        if not all(path.is_file() for path in paths.values()):
            raise ValidationError(f"{DIRECTORY} is not a complete generated Guide. Existing files were preserved.")
        before = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
        state = json.loads(before[STATE])
        if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("sources"), dict):
            raise ValidationError(f"Invalid {DIRECTORY / STATE}. Existing files were preserved.")
        old_sources = state["sources"]
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in old_sources.items()):
            raise ValidationError(f"Invalid source hashes in {DIRECTORY / STATE}")
        content = before["guide.md"]
        if content.count(BEGIN) != 1 or content.count(END) != 1:
            raise ValidationError("Generated Guide markers changed. Restore the markers before updating.")
        start, end = content.index(BEGIN) + len(BEGIN), content.index(END)
        if end < start or _digest(content[start:end].encode()) != state.get("generatedHash"):
            raise ValidationError("Generated Guide facts were edited. Move those edits outside the markers before updating.")
        owned = next((bp for bp in project.blueprints if bp.path == paths["blueprint.yml"]), None)
        if owned is None or owned.name != NAME:
            raise ValidationError(f"Include {DIRECTORY / 'blueprint.yml'} in motherduck.yml before updating Guides.")
        for blueprint in project.render_all("prod"):
            if blueprint.name == NAME and str(blueprint.guides.get("overview", {}).get("sourcePath")) != str(paths["guide.md"]):
                raise ValidationError("The generated overview must keep source: guide.md.")
        if action == "init":
            print("Repository Guide already initialized. Run make update-guides to refresh it.")
            return
    elif NAME in project.all_blueprint_names():
        raise ValidationError(f"Blueprint name already exists: {NAME}")

    project.validate()
    facts, sources = _inventory(project)
    block = "\n\n" + facts + "\n"
    if existing:
        content = before["guide.md"]
        after = {**before, "guide.md": content[:start] + block + content[end:]}
    else:
        after = {
            "blueprint.yml": yaml.safe_dump({
                "schemaVersion": 1,
                "name": NAME,
                "title": "Repository overview",
                "description": "Repository orientation and declared data contracts for agents.",
                "resources": {"guides": {"overview": {
                    "title": "${repository.name}: repository overview",
                    "topic": "",
                    "description": "Package map, data contracts, and reviewed repository conventions.",
                    "source": "guide.md", "deploy": False, "access": "user",
                    "changeComment": "Refresh reviewed repository context.",
                    "targets": {"preview": {"deploy": False}, "staging": {"deploy": False}},
                }}},
            }, sort_keys=False),
            "guide.md": (
                "# Repository overview\n\n"
                "## Reviewed context\n\n"
                "Add metric definitions, join rules, tested SQL, and known pitfalls here. "
                "Content outside the generated markers is preserved on update.\n\n"
                + BEGIN + block + END + "\n"
            ),
            "README.md": (
                "# Repository overview Guide\n\n"
                "Run `make update-guides` after changing packages or source files. "
                "Review `git diff` and update the reviewed context in `guide.md`. "
                "Source changes are reported for review, not interpreted as business rules.\n\n"
                "This orientation Guide has no resource references and does not add deployment dependencies. "
                "Keep resource-specific rules and references in dedicated Guides.\n\n"
                "The draft is private and deployment is disabled. After review, enable `deploy` "
                "for production in `blueprint.yml` and use the normal deployment workflow. "
                "The content describes production, so preview and staging deployment stay disabled.\n"
            ),
        }
        # Check discovery before creating even a draft in a custom include layout.
        include = cast(list[str], project.manifest["include"])
        relative = DIRECTORY / "blueprint.yml"
        if not any(relative.match(pattern) or relative.match(pattern.replace("/**/", "/")) for pattern in include):
            raise ValidationError("Add guides/**/blueprint.yml to motherduck.yml include before initializing Guides.")
    after[STATE] = json.dumps({"version": 1, "generatedHash": _digest(block.encode()), "sources": sources}, indent=2) + "\n"

    changed_sources = [path for path in sorted(set(old_sources) | set(sources)) if old_sources.get(path) != sources.get(path)]
    changed = {name: content for name, content in after.items() if content != before.get(name)}
    if not changed:
        print("Repository Guide is up to date.")
        return
    for source in changed_sources:
        status = "removed" if source not in sources else "added" if source not in old_sources else "changed"
        print(f"{status}: {source}")
    if dry_run:
        for name, content in changed.items():
            if name == STATE:
                continue
            relative_name = (DIRECTORY / name).as_posix()
            print("".join(difflib.unified_diff(
                before.get(name, "").splitlines(keepends=True), content.splitlines(keepends=True),
                fromfile=f"a/{relative_name}", tofile=f"b/{relative_name}",
            )), end="")
        print("Dry run. No files written.")
        return
    # Refuse to replace files edited while preparing this refresh.
    for name, original in before.items():
        if paths[name].read_text(encoding="utf-8") != original:
            raise ValidationError(f"{paths[name]} changed during refresh. Run the command again.")
    destination.mkdir(parents=True, exist_ok=existing)
    for name, content in changed.items():
        paths[name].write_text(content, encoding="utf-8")
    print(f"{'Updated' if existing else 'Created'} {DIRECTORY}. Review git diff and run make validate.")
    print("Review changed source files for context updates. No live resources were changed.")
