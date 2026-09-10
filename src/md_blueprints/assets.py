"""Resolve assembled wheel assets and authoritative files in editable checkouts."""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path


def source_assets() -> dict[str, Path]:
    package = Path(__file__).resolve().parent
    root = package.parent.parent
    if not (root / "pyproject.toml").is_file() or package != root / "src/md_blueprints":
        return {}
    mapping = json.loads((package / "asset-map.json").read_text())
    return {destination: root / source for destination, source in mapping.items()}


def schema_root() -> Path:
    # Schemas are always materialized files in supported pip installations.
    override = source_assets().get("schemas/v1/blueprint.schema.json")
    if override is not None:
        return override.parent.parent
    return Path(str(resources.files("md_blueprints").joinpath("schemas")))
