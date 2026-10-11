from __future__ import annotations

from pathlib import Path

import pytest

from md_blueprints.project import Project
from md_blueprints.schema import ValidationError


def write_graph_project(root: Path) -> Project:
    (root / "motherduck.yml").write_text(
        """schemaVersion: 1
repository:
  name: graph
include:
  - flights/**/blueprint.yml
  - dives/**/blueprint.yml
  - projects/**/blueprint.yml
targets:
  preview:
    mode: preview
    policies:
      cleanup: true
      disableSchedules: true
      requireBranchSlugInDataResources: true
  prod:
    mode: production
variables:
  preview_suffix:
    default: _preview_${target.branch_slug}
""",
        encoding="utf-8",
    )
    producer = root / "flights" / "producer"
    (producer / "src").mkdir(parents=True)
    (producer / "src/flight.py").write_text("print('ok')\n", encoding="utf-8")
    (producer / "src/requirements.txt").write_text("duckdb>=1.1\n", encoding="utf-8")
    (producer / "blueprint.yml").write_text(
        """schemaVersion: 1
name: producer
title: Producer
outputs:
  data:
    share: data
resources:
  shares:
    data:
      name: data
      database: data
      targets:
        preview:
          name: data${var.preview_suffix}
          database: data${var.preview_suffix}
  flights:
    loader:
      name: producer
      source: src/flight.py
      requirements: src/requirements.txt
      runOnDeploy: true
      targets:
        preview:
          name: producer:${target.branch} (Preview)
""",
        encoding="utf-8",
    )
    consumer = root / "dives" / "consumer"
    (consumer / "src").mkdir(parents=True)
    (consumer / "src/dive.tsx").write_text("export default function Dive() { return null; }\n", encoding="utf-8")
    (consumer / "blueprint.yml").write_text(
        """schemaVersion: 1
name: consumer
title: Consumer
description: Reads ${inputs.source.database}
inputs:
  source:
    blueprint: producer
    output: data
resources:
  dives:
    dashboard:
      title: Consumer
      source: src/dive.tsx
      requiredResources:
        - input: source
          alias: source_data
      targets:
        preview:
          title: Consumer:${target.branch} (Preview)
""",
        encoding="utf-8",
    )
    return Project(root)


def test_target_selection_expands_dependency_graph(tmp_path: Path) -> None:
    project = write_graph_project(tmp_path)

    assert project.deployment_blueprint_names("preview", ["consumer"]) == ["producer", "consumer"]
    assert project.deployment_blueprint_names("preview", ["producer"]) == ["producer", "consumer"]
    assert project.deployment_blueprint_names("prod", ["producer"]) == ["producer", "consumer"]
    assert project.deployment_blueprint_names("prod", ["consumer"]) == ["consumer"]


def write_fan_out_project(root: Path) -> Project:
    """ingest and lookup feed sibling consumers; enriched reads both and feeds report."""
    (root / "motherduck.yml").write_text(
        """schemaVersion: 1
repository:
  name: fan-out
include:
  - projects/**/blueprint.yml
targets:
  preview:
    mode: preview
    policies:
      cleanup: true
      disableSchedules: true
      requireBranchSlugInDataResources: true
  prod:
    mode: production
variables:
  preview_suffix:
    default: _preview_${target.branch_slug}
""",
        encoding="utf-8",
    )
    packages: dict[str, tuple[list[str], bool]] = {
        "ingest": ([], True),
        "lookup": ([], True),
        "listings": (["ingest"], False),
        "fraud": (["ingest"], False),
        "enriched": (["ingest", "lookup"], True),
        "report": (["enriched"], False),
        "audit": (["lookup"], False),
    }
    for name, (inputs, produces) in packages.items():
        lines = ["schemaVersion: 1", f"name: {name}", f"title: {name.title()}"]
        if inputs:
            lines.append("inputs:")
            for producer in inputs:
                lines += [f"  {producer}:", f"    blueprint: {producer}", "    output: data"]
        if produces:
            lines += [
                "outputs:", "  data:", "    share: data",
                "resources:", "  shares:", "    data:",
                f"      name: {name}", f"      database: {name}",
                "      targets:", "        preview:",
                f"          name: {name}${{var.preview_suffix}}",
                f"          database: {name}${{var.preview_suffix}}",
            ]
        else:
            lines.append("resources: {}")
        package = root / "projects" / name
        package.mkdir(parents=True)
        (package / "blueprint.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Project(root)


@pytest.mark.parametrize("target, changed, expected", [
    # A changed consumer previews with its producer, not with the producer's other consumers.
    ("preview", ["listings"], ["ingest", "listings"]),
    # A changed producer previews every consumer, plus the other producers those consumers read.
    ("preview", ["ingest"], ["ingest", "fraud", "listings", "lookup", "enriched", "report"]),
    ("preview", ["enriched"], ["ingest", "lookup", "enriched", "report"]),
    ("preview", ["listings", "audit"], ["ingest", "listings", "lookup", "audit"]),
    # Stable targets expand downstream only.
    ("prod", ["listings"], ["listings"]),
    ("prod", ["ingest"], ["ingest", "fraud", "listings", "enriched", "report"]),
])
def test_preview_selection_skips_unchanged_sibling_consumers(
    tmp_path: Path, target: str, changed: list[str], expected: list[str],
) -> None:
    project = write_fan_out_project(tmp_path)
    project.validate(targets=[target], branch="feature/one-dive")

    assert project.deployment_blueprint_names(target, changed) == expected


def test_input_metadata_uses_target_rendered_producer_output(tmp_path: Path) -> None:
    project = write_graph_project(tmp_path)

    consumer = project.render_all("preview", branch="feature/contracts", names=["consumer"])[0]

    assert consumer.inputs["source"] == {
        "share": "data",
        "name": "data_preview_feature_contracts",
        "database": "data_preview_feature_contracts",
        "access": "ORGANIZATION",
        "visibility": "DISCOVERABLE",
        "blueprint": "producer",
        "output": "data",
    }
    assert consumer.description == "Reads data_preview_feature_contracts"


def test_duplicate_dive_required_resource_alias_is_rejected(tmp_path: Path) -> None:
    project = write_graph_project(tmp_path)
    manifest = project.root / "dives/consumer/blueprint.yml"
    source = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        source.replace(
            "        - input: source\n          alias: source_data\n",
            "        - input: source\n"
            "          alias: source_data\n"
            "        - url: md:_share/example/id\n"
            "          alias: source_data\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="duplicate alias 'source_data'"):
        Project(tmp_path).validate(targets=["prod"])


def test_dependency_cycle_is_rejected_with_chain(tmp_path: Path) -> None:
    (tmp_path / "motherduck.yml").write_text(
        """schemaVersion: 1
repository: {name: cycle}
include: ["projects/**/blueprint.yml"]
targets:
  preview: {mode: preview}
  prod: {mode: production}
""",
        encoding="utf-8",
    )
    for name, dependency in (("one", "two"), ("two", "one")):
        package = tmp_path / "projects" / name
        package.mkdir(parents=True)
        (package / "blueprint.yml").write_text(
            f"""schemaVersion: 1
name: {name}
title: {name}
inputs:
  data:
    blueprint: {dependency}
    output: data
outputs:
  data:
    share: data
resources:
  shares:
    data:
      name: {name}
      database: {name}
""",
            encoding="utf-8",
        )

    with pytest.raises(ValidationError, match=r"dependency cycle: (one -> two -> one|two -> one -> two)"):
        Project(tmp_path)


def test_typed_root_rejects_mismatched_resource_group(tmp_path: Path) -> None:
    (tmp_path / "motherduck.yml").write_text(
        """schemaVersion: 1
repository: {name: typed}
include: ["dives/**/blueprint.yml"]
targets:
  preview: {mode: preview}
  prod: {mode: production}
""",
        encoding="utf-8",
    )
    package = tmp_path / "dives" / "wrong"
    package.mkdir(parents=True)
    (package / "blueprint.yml").write_text(
        """schemaVersion: 1
name: wrong
title: Wrong
resources:
  shares:
    data:
      name: data
      database: data
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="cannot declare resource group.*shares"):
        Project(tmp_path)


def test_deployed_guide_cannot_reference_validation_only_guide_without_id(
    tmp_path: Path,
) -> None:
    write_graph_project(tmp_path)
    package = tmp_path / "projects" / "knowledge"
    package.mkdir(parents=True)
    (package / "base.md").write_text("# Base\n", encoding="utf-8")
    (package / "runbook.md").write_text("# Runbook\n", encoding="utf-8")
    (package / "blueprint.yml").write_text(
        """schemaVersion: 1
name: knowledge
title: Knowledge
resources:
  guides:
    base:
      source: base.md
    runbook:
      title: Runbook
      source: runbook.md
      deploy: true
      references:
        - type: guide
          resource: base
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="validation-only Guide knowledge.base"):
        Project(tmp_path).validate(targets=["prod"])


def write_guide_package(root: Path, name: str, guides: str) -> None:
    package = root / "projects" / name
    package.mkdir(parents=True)
    (package / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (package / "blueprint.yml").write_text(
        f"schemaVersion: 1\nname: {name}\ntitle: {name}\nresources:\n  guides:\n{guides}",
        encoding="utf-8",
    )


def test_guide_references_in_target_overrides_join_the_graph(tmp_path: Path) -> None:
    write_graph_project(tmp_path)
    write_guide_package(tmp_path, "zzz", "    base:\n      source: notes.md\n      deploy: true\n")
    write_guide_package(
        tmp_path,
        "aaa",
        "    runbook:\n      source: notes.md\n      deploy: true\n      targets:\n        prod:\n"
        "          references:\n            - type: guide\n              blueprint: zzz\n              resource: base\n",
    )
    project = Project(tmp_path)

    assert project.dependencies["aaa"] == {"zzz"}
    order = project.deployment_blueprint_names("prod", ["aaa", "zzz"])
    assert order.index("zzz") < order.index("aaa")
    assert "aaa" in project.deployment_blueprint_names("prod", ["zzz"])


def test_guide_reference_in_target_override_to_missing_blueprint_is_rejected(tmp_path: Path) -> None:
    write_graph_project(tmp_path)
    write_guide_package(
        tmp_path,
        "aaa",
        "    runbook:\n      source: notes.md\n      targets:\n        prod:\n"
        "          references:\n            - type: guide\n              blueprint: ghost\n              resource: base\n",
    )

    with pytest.raises(ValidationError, match="uses missing blueprint 'ghost'"):
        Project(tmp_path)
