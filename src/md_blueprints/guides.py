"""Read-only context discovery for an agent that authors Markdown Guides."""
from __future__ import annotations

import os
import re
from importlib import resources
from pathlib import Path

import yaml

from .assets import source_assets
from .project import Project
from .schema import ValidationError


SKIP_DIRS = {"target", "dbt_packages", "logs", "node_modules", "__pycache__", "dist", "build"}
SOURCE_SUFFIXES = {".md", ".sql", ".py", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml"}
DBT_GROUPS = {"models", "sources", "seeds", "snapshots", "metrics", "semantic_models", "exposures"}
MAX_FILES = 500
MAX_EXCERPT = 24000


def _workflow() -> str:
    name = "template_repo/docs/guides-as-code.md"
    source = source_assets().get(name)
    if source is not None:
        return source.read_text(encoding="utf-8")
    return resources.files("md_blueprints").joinpath(name).read_text(encoding="utf-8")


def _code(value: object) -> str:
    text = " ".join(str(value).split()).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<code>" + text + "</code>"


def _files(root: Path, *, excluded: set[Path] | None = None) -> list[Path]:
    found: list[Path] = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(
            name for name in dirs
            if not name.startswith(".") and name not in SKIP_DIRS
            and not (base / name).is_symlink() and (base / name) not in (excluded or set())
        )
        for name in sorted(files):
            path = base / name
            if (
                not name.startswith(".") and name.lower() not in {"profiles.yml", "profiles.yaml"}
                and path.suffix.lower() in SOURCE_SUFFIXES and not path.is_symlink()
            ):
                found.append(path)
                if len(found) > MAX_FILES:
                    return found
    return found


def _file_index(paths: list[Path], root: Path) -> list[str]:
    lines = [f"- {_code(path.relative_to(root))}" for path in paths[:MAX_FILES]]
    if len(paths) > MAX_FILES:
        lines.append(f"- File index limited to {MAX_FILES} entries. Use rg --files to explore the remaining sources.")
    return lines


def _repository(root: Path) -> list[str]:
    lines = ["## Repository context", "", f"Root: {_code(root)}", ""]
    for name in ("AGENTS.md", "README.md"):
        if (root / name).is_file() and not (root / name).is_symlink():
            lines.append(f"Read {_code(name)}.")
    if not (root / "motherduck.yml").is_file():
        lines.extend(["", "No motherduck.yml. Discover from source and keep Guides as local Markdown.", ""])
        if (root / "dbt_project.yml").is_file():
            return lines
        return lines + _file_index(_files(root), root)

    project = Project(root)
    lines.extend(["", "Blueprints below are production declarations, not verified live state.", ""])
    rendered = {bp.name: bp for bp in project.render_all("prod")}
    for package in project.blueprints:
        blueprint = rendered[package.name]
        lines.extend([f"### {_code(package.name)}", "", f"Manifest: {_code(package.path.relative_to(root))}"])
        if blueprint.description:
            lines.append(f"Description: {_code(blueprint.description)}")
        for name, contract in blueprint.inputs.items():
            lines.append(f"- Input {_code(name)}: {_code(str(contract['blueprint']) + '.' + str(contract['output']))}")
        for name, contract in blueprint.outputs.items():
            lines.append(f"- Output {_code(name)}: share {_code(contract['name'])}, database {_code(contract['database'])}")
        for kind, objects in (
            ("Flight", blueprint.flights), ("Dive", blueprint.dives), ("Guide", blueprint.guides),
            ("Share", blueprint.shares), ("Role", blueprint.roles), ("Context", blueprint.contexts),
        ):
            for key, resource in objects.items():
                label = resource.get("title", resource.get("name", key))
                lines.append(f"- {kind} {_code(key)}: {_code(label)}")
                if "sourcePath" in resource:
                    lines.append(f"  Source: {_code(Path(str(resource['sourcePath'])).relative_to(root))}")
        lines.extend(["", "Read source and existing context:", *_file_index(_files(package.dir), root), ""])
    return lines


def _yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        # Parser exceptions can contain source lines, including sensitive values.
        raise ValidationError(f"Cannot parse YAML: {path}. Fix the YAML before gathering context.") from exc


def _dbt_node(value: object, depth: int = 0) -> dict[str, object]:
    """Keep documentation and relationship hints, omitting arbitrary config/meta."""
    if not isinstance(value, dict) or depth > 4:
        return {}
    fields = {
        "name", "description", "data_type", "database", "schema", "identifier", "alias",
        "model", "type", "expr", "label", "calculation_method", "v", "latest_version",
    }
    result: dict[str, object] = {key: item for key, item in value.items() if key in fields and isinstance(item, (str, int, float, bool))}
    config = value.get("config")
    if isinstance(config, dict):
        result.update({key: item for key, item in config.items() if key in {"database", "schema", "alias", "materialized"} and isinstance(item, str)})
    for key in ("columns", "tables", "versions", "measures", "dimensions", "entities"):
        children = value.get(key)
        if isinstance(children, list):
            result[key] = [_dbt_node(child, depth + 1) for child in children]
    for key in ("tests", "data_tests"):
        tests = value.get(key)
        if not isinstance(tests, list):
            continue
        hints: list[object] = []
        for test in tests:
            if isinstance(test, str):
                hints.append(test)
            elif isinstance(test, dict):
                for name, options in test.items():
                    if not isinstance(name, str):
                        continue
                    args = options.get("arguments", options) if isinstance(options, dict) else {}
                    relationship = {
                        field: item for field, item in args.items()
                        if field in {"to", "field"} and isinstance(item, str)
                    } if isinstance(args, dict) else {}
                    hints.append({name: relationship})
        result[key] = hints
    return result


def _dbt(path: Path) -> list[str]:
    path = path.expanduser().resolve()
    config = path if path.is_file() else path / "dbt_project.yml"
    if config.name != "dbt_project.yml" or not config.is_file() or config.is_symlink():
        raise ValidationError(f"Expected a dbt project directory or dbt_project.yml: {path}")
    root = config.parent
    project = _yaml(config)
    if not isinstance(project, dict):
        raise ValidationError(f"Expected a YAML mapping in {config}")
    excluded: set[Path] = set()
    for key in ("target-path", "packages-install-path", "log-path"):
        if isinstance(project.get(key), str):
            excluded.add((root / project[key]).resolve())
    paths = _files(root, excluded=excluded)
    lines = ["## dbt context", "", f"Project: {_code(root)}", "",
             "YAML excerpts are declared documentation and test hints. Jinja is unresolved, tests have not run, "
             "and relation names are not live-verified. Read the SQL, macros, and doc() blocks before writing Guides.", "",
             *_file_index(paths, root), ""]
    remaining = MAX_EXCERPT
    for source in paths[:MAX_FILES]:
        if source == config or source.suffix.lower() not in {".yml", ".yaml"}:
            continue
        if remaining <= 0:
            lines.append("YAML excerpt limit reached. Read the remaining files from the source index.\n")
            break
        document = _yaml(source)
        if not isinstance(document, dict):
            continue
        excerpt = {
            group: [_dbt_node(node) for node in nodes]
            for group, nodes in document.items() if group in DBT_GROUPS and isinstance(nodes, list)
        }
        if not excerpt:
            continue
        text = yaml.safe_dump(excerpt, sort_keys=False, allow_unicode=True)
        snippet = text[:remaining]
        remaining -= len(snippet)
        fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", snippet)), default=0))
        lines.extend([f"### {_code(source.relative_to(root))}", "", fence + "yaml", snippet.rstrip(), fence, ""])
        if len(text) > len(snippet):
            lines.append("Excerpt shortened. Read the source file for the remaining definitions.\n")
    return lines


def run_guides(root: Path, action: str = "context", *, dbt_path: Path | None = None, dry_run: bool = False) -> None:
    if action not in {"context", "init", "update"}:
        raise ValidationError("Usage: md-blueprints guides [context|init|update] [--dbt PATH]")
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValidationError(f"Repository directory not found: {root}")
    if dbt_path is None and (root / "dbt_project.yml").is_file():
        dbt_path = root
    # Prepare everything before emitting the brief so discovery errors cannot look like success.
    context = _repository(root)
    if dbt_path is not None:
        context.extend(["", *_dbt(dbt_path)])
    print(_workflow().rstrip())
    print(f"\n---\n\nRequested task: {action}. Read-only discovery. No files or live resources were changed.\n")
    print("\n".join(context))
