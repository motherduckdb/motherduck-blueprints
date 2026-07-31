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
    assert (tmp_path / "projects/revenue/guide.md").is_file()


def test_guide_scaffold_is_ready_to_enable(tmp_path: Path) -> None:
    write_root(tmp_path)
    destination = run_new(tmp_path, "guide", "analytics-guide")
    manifest = destination / "blueprint.yml"

    source = manifest.read_text(encoding="utf-8")
    assert "${target.branch}" in source
    manifest.write_text(source.replace("deploy: false", "deploy: true"), encoding="utf-8")

    assert Project(tmp_path).validate()


@pytest.mark.parametrize("kind", ["flight", "dive", "guide", "role", "project"])
@pytest.mark.parametrize(
    "name",
    ["1alpha", "123", "true", "false", "null", "yes", "no", "on", "off", "2026-07-30"],
)
def test_typed_scaffolds_support_all_schema_valid_slug_shapes(
    tmp_path: Path, kind: str, name: str
) -> None:
    write_root(tmp_path)
    options = {"share_url": "md:_share/example/id"} if kind == "dive" else {}

    destination = run_new(tmp_path, kind, name, **options)

    assert Project(tmp_path).validate()
    loaded = load_yaml(destination / "blueprint.yml")
    assert isinstance(loaded, dict)
    assert loaded["name"] == name
    assert isinstance(loaded["title"], str)


@pytest.mark.parametrize("alias", ["true", "false", "null", "yes", "no", "on", "off"])
def test_new_dive_quotes_yaml_reserved_aliases(tmp_path: Path, alias: str) -> None:
    write_root(tmp_path)

    destination = run_new(
        tmp_path,
        "dive",
        "external-dashboard",
        share_url="md:_share/example/id",
        alias=alias,
    )

    assert Project(tmp_path).validate()
    loaded = load_yaml(destination / "blueprint.yml")
    assert isinstance(loaded, dict)
    required = loaded["resources"]["dives"]["dashboard"]["requiredResources"]
    assert required[0]["alias"] == alias


def test_numeric_leading_slug_gets_a_safe_default_alias(tmp_path: Path) -> None:
    write_root(tmp_path)

    project = run_new(tmp_path, "project", "123-metrics")
    dive = run_new(
        tmp_path,
        "dive",
        "456-dashboard",
        share_url="md:_share/example/id",
    )

    assert Project(tmp_path).validate()
    assert 'default: "_123_metrics"' in (project / "blueprint.yml").read_text(encoding="utf-8")
    assert 'alias: "_456_dashboard"' in (dive / "blueprint.yml").read_text(encoding="utf-8")


def test_new_rejects_duplicate_name_across_typed_roots_before_writing(tmp_path: Path) -> None:
    write_root(tmp_path)
    run_new(tmp_path, "flight", "shared-name")

    with pytest.raises(ValidationError, match="Blueprint name already exists"):
        run_new(tmp_path, "guide", "shared-name")

    assert not (tmp_path / "guides/shared-name").exists()


@pytest.mark.parametrize(
    ("kind", "options", "message"),
    [
        ("flight", {"input_ref": "producer.data"}, "--input and --url"),
        ("guide", {"share_url": "md:_share/example/id"}, "--input and --url"),
        ("role", {"alias": "custom"}, "--alias is only valid"),
    ],
)
def test_new_rejects_options_that_do_not_apply_to_the_kind(
    tmp_path: Path, kind: str, options: dict[str, str], message: str
) -> None:
    write_root(tmp_path)

    with pytest.raises(ValidationError, match=message):
        run_new(tmp_path, kind, "invalid-options", **options)

    assert not (tmp_path / f"{kind}s/invalid-options").exists()


def test_new_project_uses_the_complete_starter_template(tmp_path: Path) -> None:
    write_root(tmp_path)

    destination = run_new(tmp_path, "project", "daily-metrics")

    manifest = (destination / "blueprint.yml").read_text(encoding="utf-8")
    readme = (destination / "README.md").read_text(encoding="utf-8")
    assert "status: ready" in manifest
    assert "status: draft" in manifest
    assert "Starter project that publishes" in manifest
    assert "project-guide:" in manifest
    assert "source: guide.md" in manifest
    assert (destination / "guide.md").is_file()
    assert "## Replace the Starter Logic" in readme
    assert "__BLUEPRINT_" not in manifest
    assert "__BLUEPRINT_" not in readme

    (destination / "blueprint.yml").write_text(
        manifest.replace("deploy: false", "deploy: true"),
        encoding="utf-8",
    )
    assert Project(tmp_path).validate()


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


def test_new_dive_rejects_an_explicitly_empty_alias(tmp_path: Path) -> None:
    write_root(tmp_path)

    with pytest.raises(ValidationError, match="--alias must not be empty"):
        run_new(
            tmp_path,
            "dive",
            "empty-alias",
            share_url="md:_share/example/id",
            alias="",
        )

    assert not (tmp_path / "dives/empty-alias").exists()


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
        share_url="  md:_share/example/id  ",
        alias="external_data",
    )
    source = (destination / "src/dive.tsx").read_text(encoding="utf-8")
    loaded = load_yaml(destination / "blueprint.yml")

    assert isinstance(loaded, dict)
    required = loaded["resources"]["dives"]["dashboard"]["requiredResources"]
    assert required[0]["url"] == "md:_share/example/id"
    assert '"path": "md:_share/example/id"' in source
    assert '"alias": "external_data"' in source
