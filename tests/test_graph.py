from __future__ import annotations

from pathlib import Path

import pytest

from md_blueprints.deploy import Deployer
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


def test_consumer_only_production_plan_requires_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = write_graph_project(tmp_path)
    deployer = Deployer(project)
    rendered = project.render_all("prod", names=project.deployment_blueprint_names("prod", ["consumer"]))
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "")
    monkeypatch.setattr(deployer, "_list_dive_states", lambda title: [])

    records = deployer._build_deploy_plan(rendered)

    input_record = next(record for record in records if record.type == "input")
    assert input_record.action == "error"
    assert "producer.data" in input_record.notes


def test_preview_plan_allows_selected_producer_output_to_be_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = write_graph_project(tmp_path)
    deployer = Deployer(project)
    names = project.deployment_blueprint_names("preview", ["consumer"])
    rendered = project.render_all("preview", branch="feature/contracts", names=names)
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "")
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])
    monkeypatch.setattr(deployer, "_list_dive_states", lambda title: [])

    records = deployer._build_deploy_plan(rendered)

    assert next(record for record in records if record.type == "input").action == "pending"


def test_plan_rejects_missing_share_when_selected_producer_will_not_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = write_graph_project(tmp_path)
    deployer = Deployer(project)
    names = project.deployment_blueprint_names("preview", ["consumer"])
    rendered = project.render_all("preview", branch="feature/contracts", names=names)
    rendered[0].flights["loader"]["runOnDeploy"] = False
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "")
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])
    monkeypatch.setattr(deployer, "_list_dive_states", lambda title: [])

    records = deployer._build_deploy_plan(rendered)

    share_record = next(record for record in records if record.type == "share")
    input_record = next(record for record in records if record.type == "input")
    assert share_record.action == "error"
    assert input_record.action == "error"
    assert "runOnDeploy" in share_record.notes
    assert "runOnDeploy" in input_record.notes


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


def test_cleanup_plan_removes_consumers_before_producers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = write_graph_project(tmp_path)
    deployer = Deployer(project)
    rendered = project.render_all("preview", branch="feature/contracts")
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: ["dive-id"])
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: ["flight-id"])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/example/id")

    records = deployer._build_cleanup_plan(rendered, "feature_contracts", branch="feature/contracts")

    assert [record.type for record in records] == ["dive", "flight", "share"]
    assert [record.blueprint for record in records] == ["consumer", "producer", "producer"]


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
