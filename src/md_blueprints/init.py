from __future__ import annotations

from collections.abc import Iterator
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from . import __version__
from .schema import ValidationError

VERSION_PLACEHOLDER = "__MD_BLUEPRINTS_VERSION__"
ACTION_TAG_PLACEHOLDER = "__MD_BLUEPRINTS_ACTION_TAG__"


def action_major_tag(version: str = __version__) -> str:
    major = version.split(".", maxsplit=1)[0].removeprefix("v")
    return f"v{major}"


def render_template_text(text: str) -> str:
    return text.replace(VERSION_PLACEHOLDER, __version__).replace(ACTION_TAG_PLACEHOLDER, action_major_tag())


def is_text_file(path: str) -> bool:
    return not path.endswith(".png") and not path.endswith(".jpg") and not path.endswith(".jpeg")


def iter_resources(root: Traversable, prefix: str = "") -> Iterator[tuple[Traversable, str]]:
    for child in root.iterdir():
        relative = f"{prefix}/{child.name}" if prefix else child.name
        yield child, relative
        if child.is_dir():
            yield from iter_resources(child, relative)


def run_init(target: Path, *, force: bool = False) -> None:
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not force:
        raise ValidationError(f"{target} is not empty; pass --force to overwrite template files")
    target.mkdir(parents=True, exist_ok=True)

    template_root = resources.files("md_blueprints").joinpath("template_repo")
    written = 0
    for resource, relative in iter_resources(template_root):
        if not relative or "/__pycache__/" in f"/{relative}/":
            continue
        destination = target / relative
        if resource.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        if is_text_file(relative):
            destination.write_text(render_template_text(resource.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            destination.write_bytes(resource.read_bytes())
        written += 1

    print(f"Initialized MotherDuck Blueprints template in {target} ({written} files).")
    print(f"CLI version pinned in Makefile: {__version__}")
    print(f"Action tag pinned in workflows: {action_major_tag()}")
