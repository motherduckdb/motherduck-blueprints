from __future__ import annotations

from pathlib import Path

import pytest

import md_blueprints.project as project_module
from md_blueprints.project import Project


FIXTURES = Path(__file__).parent / "fixtures"


def test_changed_blueprints_zero_sha_returns_all_blueprints() -> None:
    project = Project(FIXTURES / "simple")

    assert project.changed_blueprints(base="0" * 40, head="HEAD") == ["simple-dive"]


def test_render_uses_root_target_blueprint_and_blueprint_target_variable_precedence(tmp_path: Path) -> None:
    blueprint_dir = tmp_path / "blueprints" / "precedence"
    source_dir = blueprint_dir / "src"
    source_dir.mkdir(parents=True)
    (source_dir / "dive.tsx").write_text("export default function Dive() { return null; }\n", encoding="utf-8")
    (tmp_path / "motherduck.yml").write_text(
        """
schemaVersion: 1
repository:
  name: precedence
include:
  - blueprints/*/blueprint.yml
variables:
  owner:
    default: root
targets:
  preview:
    mode: preview
    variables:
      owner:
        default: target
  prod:
    mode: production
""".lstrip(),
        encoding="utf-8",
    )
    (blueprint_dir / "blueprint.yml").write_text(
        """
schemaVersion: 1
name: precedence
title: ${var.owner}
variables:
  owner:
    default: blueprint
targets:
  preview:
    variables:
      owner:
        default: blueprint-target
resources:
  dives:
    dashboard:
      title: ${var.owner}
      source: src/dive.tsx
      requiredResources:
        - url: md:_share/example/00000000-0000-0000-0000-000000000000
          alias: example
""".lstrip(),
        encoding="utf-8",
    )

    rendered = Project(tmp_path).render_all("preview", branch="feature/test")

    assert rendered[0].title == "blueprint-target"
    assert rendered[0].dives["dashboard"]["title"] == "blueprint-target"


def test_changed_blueprints_handles_multiple_include_globs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def write_blueprint(root: Path, directory: str, name: str) -> None:
        blueprint_dir = root / directory / name
        source_dir = blueprint_dir / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "dive.tsx").write_text("export default function Dive() { return null; }\n", encoding="utf-8")
        (blueprint_dir / "blueprint.yml").write_text(
            f"""
schemaVersion: 1
name: {name}
title: {name}
resources:
  dives:
    dashboard:
      title: {name}
      source: src/dive.tsx
      requiredResources:
        - url: md:_share/example/00000000-0000-0000-0000-000000000000
          alias: example
""".lstrip(),
            encoding="utf-8",
        )

    (tmp_path / "motherduck.yml").write_text(
        """
schemaVersion: 1
repository:
  name: include-globs
include:
  - blueprints/*/blueprint.yml
  - packages/*/blueprint.yml
targets:
  preview:
    mode: preview
  prod:
    mode: production
""".lstrip(),
        encoding="utf-8",
    )
    write_blueprint(tmp_path, "blueprints", "first")
    write_blueprint(tmp_path, "packages", "second")
    project = Project(tmp_path)

    monkeypatch.setattr(
        project_module,
        "run_command",
        lambda argv: "packages/second/src/dive.tsx\n",
    )
    assert project.changed_blueprints(base="main", head="HEAD") == ["second"]

    monkeypatch.setattr(project_module, "run_command", lambda argv: "docs/readme.md\n")
    assert project.changed_blueprints(base="main", head="HEAD") == []

    monkeypatch.setattr(project_module, "run_command", lambda argv: "schemas/v1/blueprint.schema.json\n")
    assert project.changed_blueprints(base="main", head="HEAD") == ["first", "second"]
