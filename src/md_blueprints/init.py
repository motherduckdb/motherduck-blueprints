from __future__ import annotations

from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Protocol

from . import __version__
from .assets import source_assets
from .schema import ValidationError

VERSION_PLACEHOLDER = "__MD_BLUEPRINTS_VERSION__"
ACTION_TAG_PLACEHOLDER = "__MD_BLUEPRINTS_ACTION_TAG__"


class _Traversable(Protocol):
    @property
    def name(self) -> str: ...

    def iterdir(self) -> Iterator[_Traversable]: ...

    def is_dir(self) -> bool: ...

    def read_bytes(self) -> bytes: ...

    def read_text(self, encoding: str | None = None) -> str: ...


def action_tag(version: str = __version__) -> str:
    return f"v{version.removeprefix('v')}"


def render_template_text(text: str) -> str:
    return text.replace(VERSION_PLACEHOLDER, __version__).replace(ACTION_TAG_PLACEHOLDER, action_tag())


def is_text_file(path: str) -> bool:
    return not path.endswith(".png") and not path.endswith(".jpg") and not path.endswith(".jpeg")


def iter_resources(root: _Traversable, prefix: str = "") -> Iterator[tuple[_Traversable, str]]:
    for child in root.iterdir():
        relative = f"{prefix}/{child.name}" if prefix else child.name
        yield child, relative
        if child.is_dir():
            yield from iter_resources(child, relative)


SKIPPED_FILE_GUIDANCE = {
    ".gitignore": "merge the template's ignore entries into yours manually",
    "README.md": "keep your README and link to docs/ for Blueprints usage",
    "AGENTS.md": "merge the Blueprints agent guidance into your AGENTS.md manually",
    "Makefile": "merge the Blueprints targets and CLI_VERSION pin into your Makefile manually",
    "motherduck.yml": "compare include globs and targets with the template",
}


def template_assets() -> dict[str, _Traversable | Path]:
    """Files a generated repository receives, keyed by their path in the repository."""
    template_root = resources.files("md_blueprints").joinpath("template_repo")
    assets: dict[str, _Traversable | Path] = {
        relative: resource for resource, relative in iter_resources(template_root) if not resource.is_dir()
    }
    assets.update({
        name.removeprefix("template_repo/"): path
        for name, path in source_assets().items() if name.startswith("template_repo/")
    })
    return {
        relative: resource
        for relative, resource in assets.items()
        if relative and "/__pycache__/" not in f"/{relative}/" and relative.split("/", 1)[0] != "templates"
    }


PREVIEW_ROOT = ".dive-preview/"


def preview_drift(target: Path) -> list[str]:
    """Local Dive preview support files that are missing or differ from this release's copies."""
    return [
        relative
        for relative, resource in sorted(template_assets().items())
        if relative.startswith(PREVIEW_ROOT)
        and _read_text(target / relative) != render_template_text(resource.read_text(encoding="utf-8"))
    ]


def run_sync_preview(target: Path, *, write: bool = False) -> None:
    """Replace the support files under .dive-preview/ with this release's copies."""
    target = target.expanduser().resolve()
    if not (target / PREVIEW_ROOT).is_dir():
        raise ValidationError(f"{target / PREVIEW_ROOT} not found. Run sync-preview in a generated repository.")
    drift = preview_drift(target)
    if not drift:
        print(f"Local Dive preview already matches md-blueprints {__version__}.")
        return
    assets = template_assets()
    print(f"Local Dive preview files that differ from md-blueprints {__version__}:")
    for relative in drift:
        print(f"  {relative}")
    if not write:
        print("Dry run. Add --write to replace them. Your .env and Dive sources are never touched.")
        return
    # Check every destination first, so an unsafe path stops the sync before any file is written.
    planned = [(relative, safe_destination(target, relative)) for relative in drift]
    for relative, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_template_text(assets[relative].read_text(encoding="utf-8")), encoding="utf-8")
    print(
        f"Updated {len(drift)} file(s). Run make preview-smoke NAME=<blueprint-name> to rebuild a Dive, "
        "review git diff, and commit the files with package-lock.json."
    )


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        return None


def run_init(target: Path, *, force: bool = False) -> None:
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not force:
        raise ValidationError(
            f"{target} is not empty. Pass --force to add only missing template files; existing files are "
            "never overwritten. To review the full template first, run init in an empty directory."
        )
    target.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped: list[str] = []
    planned = [
        (relative, resource, safe_destination(target, relative))
        for relative, resource in sorted(template_assets().items())
    ]
    # Every destination is checked above, so an unsafe path stops init before any file is written.
    for relative, resource, destination in planned:
        if destination.exists() or destination.is_symlink():
            skipped.append(relative)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if is_text_file(relative):
            destination.write_text(render_template_text(resource.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            destination.write_bytes(resource.read_bytes())
        written += 1

    print(f"Initialized MotherDuck Blueprints template in {target} ({written} files).")
    print(f"CLI version pinned in Makefile: {__version__}")
    print(f"Action tag pinned in workflows: {action_tag()}")
    if skipped:
        print(f"Kept {len(skipped)} existing file(s) unchanged:")
        for relative in skipped:
            guidance = SKIPPED_FILE_GUIDANCE.get(relative)
            print(f"  {relative}" + (f" ({guidance})" if guidance else ""))
        print(
            "Compare them with a fresh `md-blueprints init` in an empty directory and merge what you need."
        )


def safe_destination(target: Path, relative: str) -> Path:
    destination = target / relative
    try:
        destination.resolve(strict=False).relative_to(target)
    except ValueError as exc:
        raise ValidationError(f"Refusing to write template path outside {target}: {relative}") from exc
    return destination
