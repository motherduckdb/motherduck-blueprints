from __future__ import annotations

import difflib
import re
from pathlib import Path

import yaml
from packaging.version import InvalidVersion, Version
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from .maintenance import TOKEN_CALLER, fetch_latest_version
from .project import require_within
from .schema import ValidationError


CLI_PIN = re.compile(r"^(CLI_VERSION\s*:?=\s*)([^\s#]+)", re.MULTILINE)
TOOLING_PIN = re.compile(
    r"^(motherduckdb/motherduck-blueprints(?:/\.github/workflows/[^/@]+\.ya?ml)?)@[^\s]+$"
)
TOKEN_SECRET = "MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}"
# Matches the generated callers so an upgraded repository equals a newly generated one.
TOKEN_COMMENT = "# Passes only this secret. The reusable job reads it from the GitHub Environment its target selects."


def add_token_secrets(text: str) -> tuple[str, int]:
    """Pass MOTHERDUCK_TOKEN to reusable deploy and cleanup jobs that pass no secrets.

    GitHub resolves an environment secret to an empty string in a reusable workflow unless
    the caller passes it. Jobs that already declare `secrets`, including `secrets: inherit`,
    are left unchanged. Flow-style jobs are left for `doctor` to report.
    """
    try:
        document = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise ValidationError(f"Invalid workflow YAML; no secrets were added: {exc}") from exc
    insertions: dict[int, str] = {}
    visited: set[int] = set()

    def visit(node: Node | None) -> None:
        if node is None or id(node) in visited:
            return
        visited.add(id(node))
        if isinstance(node, MappingNode):
            keys = {key.value for key, _ in node.value if isinstance(key, ScalarNode)}
            for key, value in node.value:
                if (
                    isinstance(key, ScalarNode) and key.value == "uses" and not node.flow_style
                    and "secrets" not in keys
                    and isinstance(value, ScalarNode) and TOKEN_CALLER.fullmatch(value.value.strip())
                ):
                    line_end = text.find("\n", value.end_mark.index)
                    line_end = len(text) if line_end == -1 else line_end
                    indent = " " * key.start_mark.column
                    insertions[line_end] = f"\n{indent}{TOKEN_COMMENT}\n{indent}secrets:\n{indent}  {TOKEN_SECRET}"
                visit(value)
        elif isinstance(node, SequenceNode):
            for child in node.value:
                visit(child)

    visit(document)
    for index, insertion in sorted(insertions.items(), reverse=True):
        text = text[:index] + insertion + text[index:]
    return text, len(insertions)


def update_action_pins(text: str, version: str) -> tuple[str, int]:
    """Edit YAML scalar spans so comments, quoting, and customer settings survive."""
    try:
        document = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise ValidationError(f"Invalid workflow YAML; no pins were changed: {exc}") from exc
    edits: dict[int, tuple[int, str]] = {}
    visited: set[int] = set()

    def visit(node: Node | None) -> None:
        if node is None or id(node) in visited:
            return
        visited.add(id(node))
        if isinstance(node, MappingNode):
            for key, value in node.value:
                if (
                    isinstance(key, ScalarNode) and key.value == "uses"
                    and isinstance(value, ScalarNode) and TOOLING_PIN.fullmatch(value.value.strip())
                ):
                    original = text[value.start_mark.index:value.end_mark.index]
                    pin = value.value.strip()
                    reference = pin.rsplit("@", 1)[0]
                    if pin not in original:
                        raise ValidationError("Unsupported multiline action pin; no pins were changed.")
                    edits[value.start_mark.index] = (
                        value.end_mark.index, original.replace(pin, f"{reference}@v{version}", 1)
                    )
                visit(value)
        elif isinstance(node, SequenceNode):
            for child in node.value:
                visit(child)

    visit(document)
    for start, (end, replacement) in sorted(edits.items(), reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, len(edits)


def run_upgrade(root: Path, *, to_version: str = "latest", write: bool = False, offline: bool = False) -> None:
    root = root.expanduser().resolve()
    if to_version == "latest":
        version = fetch_latest_version(
            offline=offline, offline_hint="Pass --to X.Y.Z to choose a release without contacting GitHub.",
        )
        if version is None:
            raise ValidationError(
                "Cannot determine the latest release offline. Pass --to X.Y.Z, or set "
                "MD_BLUEPRINTS_LATEST_VERSION=X.Y.Z, to upgrade without contacting GitHub."
            )
    else:
        version = to_version.removeprefix("v")
    if not version or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValidationError("Choose a stable release with --to X.Y.Z, or use --to latest.")
    makefile = require_within(root / "Makefile", root, "Makefile")
    if not makefile.is_file():
        raise ValidationError("No Makefile found. Run upgrade from your generated customer repository.")
    original = makefile.read_text(encoding="utf-8")
    if len(CLI_PIN.findall(original)) != 1:
        raise ValidationError("Expected one CLI_VERSION pin in Makefile. Run upgrade in a generated customer repository.")
    current = CLI_PIN.findall(original)[0][1]
    try:
        ahead = Version(current) > Version(version)
    except InvalidVersion as exc:
        raise ValidationError(f"Invalid CLI_VERSION pin {current!r}; no pins were changed.") from exc
    if to_version == "latest" and ahead:
        print(f"CLI_VERSION {current} is ahead of the latest release {version}; no pins were changed.")
        return
    updates = [(makefile, original, CLI_PIN.sub(lambda match: match[1] + version, original))]
    action_count = 0
    secret_count = 0
    for path in sorted((root / ".github/workflows").glob("*.y*ml")):
        path = require_within(path, root, "Workflow")
        original = path.read_text(encoding="utf-8")
        updated, count = update_action_pins(original, version)
        action_count += count
        updated, added = add_token_secrets(updated)
        secret_count += added
        updates.append((path, original, updated))
    if not action_count:
        raise ValidationError("No MotherDuck Blueprints action pins found in .github/workflows; nothing was changed.")
    changed = [(path, before, after) for path, before, after in updates if before != after]
    if not changed:
        print(f"Tooling pins are already aligned at {version}.")
        return
    if secret_count:
        print(
            f"Passing MOTHERDUCK_TOKEN to {secret_count} reusable workflow job(s). GitHub gives reusable "
            "workflows an empty environment secret unless the caller passes it.\n"
        )
    for path, before, after in changed:
        relative = path.relative_to(root).as_posix()
        print("".join(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"a/{relative}", tofile=f"b/{relative}",
        )), end="")
    if write:
        for path, _, after in changed:
            path.write_text(after, encoding="utf-8")
        print("\nUpdated tooling pins. Run make validate, review git diff, and open a pull request.")
    else:
        print("\nDry run. Add --write to update the pins together.")
    print(f"Release notes: https://github.com/motherduckdb/motherduck-blueprints/releases/tag/v{version}")
