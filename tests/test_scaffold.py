from __future__ import annotations

from pathlib import Path

import pytest

from md_blueprints.project import Project
from md_blueprints.scaffold import run_new
from md_blueprints.schema import ValidationError, load_yaml


def write_root(root: Path) -> None:
    (root / "motherduck.yml").write_text(
        """schemaVersion: 1
repository: {name: scaffold}
include:
  - flights/**/blueprint.yml
  - dives/**/blueprint.yml
  - guides/**/blueprint.yml
  - roles/**/blueprint.yml
  - projects/**/blueprint.yml
targets:
  preview:
    mode: preview
    policies:
      disableSchedules: true
      requireBranchSlugInDataResources: true
  prod: {mode: production}
variables:
  preview_suffix:
    default: _preview_${target.branch_slug}
""",
        encoding="utf-8",
    )


def write_producer(root: Path, output: str = "data") -> None:
    destination = run_new(root, "flight", "producer")
    if output == "data":
        return
    manifest = destination / "blueprint.yml"
    source = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        source.replace("outputs:\n  data:\n", f"outputs:\n  {output!r}:\n"),
        encoding="utf-8",
    )


def test_all_typed_scaffolds_generate_a_valid_repository(tmp_path: Path) -> None:
    write_root(tmp_path)

    run_new(tmp_path, "flight", "events-ingest")
    run_new(tmp_path, "dive", "events-dashboard", input_ref="events-ingest.data")
    run_new(tmp_path, "dive", "external-dashboard", share_url="md:_share/example/id")
    run_new(tmp_path, "guide", "analytics-guide")
    run_new(tmp_path, "role", "analytics-team")
    run_new(tmp_path, "project", "revenue")

    assert Project(tmp_path).validate()
    assert (tmp_path / "flights/events-ingest/src/flight.py").is_file()
    assert (tmp_path / "dives/events-dashboard/src/dive.tsx").is_file()
    assert (tmp_path / "guides/analytics-guide/guide.md").is_file()
    assert (tmp_path / "roles/analytics-team/blueprint.yml").is_file()
    assert (tmp_path / "projects/revenue/src/dive.tsx").is_file()


def test_new_dive_requires_one_data_source(tmp_path: Path) -> None:
    write_root(tmp_path)

    with pytest.raises(ValidationError, match="exactly one"):
        run_new(tmp_path, "dive", "missing-source")
    with pytest.raises(ValidationError, match="exactly one"):
        run_new(
            tmp_path,
            "dive",
            "two-sources",
            input_ref="producer.data",
            share_url="md:_share/example/id",
        )


def test_new_dive_accepts_non_slug_output_keys_and_uses_schema_neutral_source(tmp_path: Path) -> None:
    write_root(tmp_path)
    write_producer(tmp_path, "daily_metrics")

    destination = run_new(tmp_path, "dive", "external-dashboard", input_ref="producer.daily_metrics")
    source = (destination / "src/dive.tsx").read_text(encoding="utf-8")

    loaded = load_yaml(destination / "blueprint.yml")
    assert isinstance(loaded, dict)
    assert loaded["inputs"] == {"data": {"blueprint": "producer", "output": "daily_metrics"}}
    assert "information_schema.tables" in source
    assert "starter_metric_summary" not in source
    assert '"shareName": "producer"' in source
    assert "__REQUIRED_DATABASE__" not in source


def test_new_dive_preserves_output_keys_that_need_yaml_quoting(tmp_path: Path) -> None:
    write_root(tmp_path)
    write_producer(tmp_path, "true")

    destination = run_new(tmp_path, "dive", "quoted-output", input_ref="producer.true")
    loaded = load_yaml(destination / "blueprint.yml")

    assert isinstance(loaded, dict)
    assert loaded["inputs"] == {"data": {"blueprint": "producer", "output": "true"}}


def test_new_dive_rejects_missing_producer_without_writing_package(tmp_path: Path) -> None:
    write_root(tmp_path)

    with pytest.raises(ValidationError, match="missing blueprint 'producer'"):
        run_new(tmp_path, "dive", "dashboard", input_ref="producer.data")

    assert not (tmp_path / "dives/dashboard").exists()


def test_new_external_dive_preserves_share_url_for_local_preview(tmp_path: Path) -> None:
    write_root(tmp_path)

    destination = run_new(
        tmp_path,
        "dive",
        "external-dashboard",
        share_url="md:_share/example/id",
        alias="external_data",
    )
    source = (destination / "src/dive.tsx").read_text(encoding="utf-8")

    assert '"path": "md:_share/example/id"' in source
    assert '"alias": "external_data"' in source
