from __future__ import annotations

from pathlib import Path

import pytest

import md_blueprints.project as project_module
from md_blueprints.deploy import Deployer
from md_blueprints.project import Project
from md_blueprints.schema import ValidationError


FIXTURES = Path(__file__).parent / "fixtures"


def write_root_manifest(root: Path, include: str = "blueprints/*/blueprint.yml") -> None:
    (root / "motherduck.yml").write_text(
        f"""
schemaVersion: 1
repository:
  name: path-safety
include:
  - {include}
targets:
  preview:
    mode: preview
    policies:
      cleanup: true
      requireBranchSlugInDataResources: true
  prod:
    mode: production
""".lstrip(),
        encoding="utf-8",
    )


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


def test_include_pattern_cannot_escape_project_root(tmp_path: Path) -> None:
    write_root_manifest(tmp_path, "../*/blueprint.yml")

    with pytest.raises(ValidationError, match="must stay within the project root"):
        Project(tmp_path)


def test_resource_source_cannot_escape_blueprint_package(tmp_path: Path) -> None:
    blueprint_dir = tmp_path / "blueprints" / "unsafe"
    blueprint_dir.mkdir(parents=True)
    (tmp_path / "outside.tsx").write_text("export default function Dive() { return null; }\n", encoding="utf-8")
    write_root_manifest(tmp_path)
    (blueprint_dir / "blueprint.yml").write_text(
        """
schemaVersion: 1
name: unsafe
title: Unsafe
resources:
  dives:
    dashboard:
      title: Unsafe:${target.branch} (Preview)
      source: ../../outside.tsx
      requiredResources:
        - url: md:_share/example/00000000-0000-0000-0000-000000000000
          alias: example
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="Dive source.*must stay within"):
        Project(tmp_path).render_all("preview", branch="feature/test")


def test_duplicate_blueprint_names_are_rejected(tmp_path: Path) -> None:
    write_root_manifest(tmp_path)
    for directory in ("first", "second"):
        blueprint_dir = tmp_path / "blueprints" / directory
        blueprint_dir.mkdir(parents=True)
        (blueprint_dir / "blueprint.yml").write_text(
            """
schemaVersion: 1
name: duplicate
title: Duplicate
resources: {}
""".lstrip(),
            encoding="utf-8",
        )

    with pytest.raises(ValidationError, match="Duplicate blueprint name 'duplicate'"):
        Project(tmp_path)


def test_live_preview_validates_the_requested_branch(tmp_path: Path) -> None:
    blueprint_dir = tmp_path / "blueprints" / "branch-check"
    blueprint_dir.mkdir(parents=True)
    write_root_manifest(tmp_path)
    (blueprint_dir / "blueprint.yml").write_text(
        """
schemaVersion: 1
name: branch-check
title: Branch Check
resources:
  shares:
    data:
      name: data_prod
      database: data_prod
      cleanup: true
      dropDatabase: true
      targets:
        preview:
          name: data_feature_mock_test
          database: data_feature_mock_test
""".lstrip(),
        encoding="utf-8",
    )
    project = Project(tmp_path)
    assert project.validate(targets=["preview"])

    with pytest.raises(ValidationError, match="must include branch slug feature_actual"):
        Deployer(project)._validate_and_render("preview", "feature/actual", None)


def test_preview_resource_identifier_cannot_match_production(tmp_path: Path) -> None:
    blueprint_dir = tmp_path / "blueprints" / "shared-name"
    source_dir = blueprint_dir / "src"
    source_dir.mkdir(parents=True)
    (source_dir / "dive.tsx").write_text("export default function Dive() { return null; }\n", encoding="utf-8")
    write_root_manifest(tmp_path)
    (blueprint_dir / "blueprint.yml").write_text(
        """
schemaVersion: 1
name: shared-name
title: Shared Name
resources:
  dives:
    dashboard:
      title: production dashboard
      source: src/dive.tsx
      requiredResources:
        - url: md:_share/example/00000000-0000-0000-0000-000000000000
          alias: example
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="must not match its production title"):
        Project(tmp_path).validate(targets=["preview"], branch="prod")
