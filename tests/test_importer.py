from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml
import duckdb

from md_blueprints.deploy import Deployer
from md_blueprints.importer import ImportReader, convert, run_import, dive_source
from md_blueprints.init import run_init
from md_blueprints.project import Project
from md_blueprints.schema import ValidationError
from e2e_support import IMPORT_IDS as IDS, import_snapshot as snapshots


def setup(root: Path) -> tuple[Project, Path]:
    run_init(root)
    source = root / ".imports/source.json"
    source.parent.mkdir()
    source.write_text(json.dumps(snapshots()))
    return Project(root), source


def test_incomplete_batch_and_path_escape_do_not_write(tmp_path: Path) -> None:
    project, source = setup(tmp_path)
    data = snapshots()
    del data[-1]["content"]["references"]
    source.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="missing references"):
        run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    assert len(Project(tmp_path).blueprints) == 2
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (tmp_path / "guides").symlink_to(outside)
    source.write_text(json.dumps(snapshots()))
    # Existing destinations, even via an internal symlink, are not overwritten.
    package, _, _ = convert(snapshots()[-1], "prod")
    (tmp_path / package).mkdir()
    with pytest.raises(ValidationError, match="destination exists"):
        run_import(Project(tmp_path), target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    assert len(Project(tmp_path).blueprints) == 2


def test_failure_during_writes_rolls_back_only_new_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, source = setup(tmp_path)
    original = project.manifest_path.read_bytes()
    normal_open = Path.open

    def fail_second_package(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if mode == "x" and path.name == "index.tsx":
            raise OSError("disk full")
        return normal_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_second_package)
    with pytest.raises(OSError, match="disk full"):
        run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    assert len(Project(tmp_path).blueprints) == 2
    assert project.manifest_path.read_bytes() == original


def test_pagination_continues_past_short_pages_and_1000(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, _ = setup(tmp_path)
    reader = ImportReader(Deployer(project))
    pages = [[{"flight_id": str(UUID(int=i))} for i in range(start, min(start + 75, 1102))]
             for start in range(1, 1102, 75)]
    pages.append([])
    calls = []

    def rows(function: str) -> list[dict[str, Any]]:
        calls.append(function)
        return pages.pop(0)

    monkeypatch.setattr(reader, "rows", rows)
    assert len(reader.inventory("flight")) == 1101
    assert '"offset" := 75' in calls[1]


def test_repeated_catalog_page_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, _ = setup(tmp_path)
    reader = ImportReader(Deployer(project))
    monkeypatch.setattr(reader, "rows", lambda statement: [{"id": IDS["dive"]}])
    with pytest.raises(ValidationError, match="pagination repeated"):
        reader.inventory("dive")


def test_import_guard_rejects_older_cli_and_preview_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, source = setup(tmp_path)
    report = run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    with monkeypatch.context() as context:
        context.setattr("md_blueprints.schema.__version__", "0.4.2")
        with pytest.raises(ValidationError, match="requires md-blueprints"):
            Project(tmp_path)
    path = tmp_path / report["resources"][0]["package"] / "blueprint.yml"
    data = yaml.safe_load(path.read_text())
    data["resources"]["flights"]["imported"]["targets"]["preview"]["id"] = IDS["flight"]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValidationError, match="must not use an adopted id"):
        Project(tmp_path).validate()


def test_import_into_staging_never_binds_production(tmp_path: Path) -> None:
    project, source = setup(tmp_path)
    manifest = yaml.safe_load(project.manifest_path.read_text())
    manifest["targets"]["staging"] = copy.deepcopy(manifest["targets"]["prod"])
    manifest["targets"]["staging"]["environment"] = "motherduck-staging"
    manifest["targets"]["preview"]["environment"] = "motherduck-staging"
    project.manifest_path.write_text(yaml.safe_dump(manifest))
    report = run_import(Project(tmp_path), target="staging", selectors=[], all_resources=False, write=True, snapshot_path=source)
    project = Project(tmp_path)
    names = [Path(item["package"]).name for item in report["resources"]]
    for bp in project.render_all("prod", names=names):
        for resource in [*bp.flights.values(), *bp.dives.values(), *bp.guides.values()]:
            assert "id" not in resource and resource["deploy"] is False


def test_snapshot_refuses_concurrent_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, _ = setup(tmp_path)
    reader = ImportReader(Deployer(project))
    item = snapshots()[0]
    changed = {**item["metadata"], "current_version": 4}
    replies = [[item["metadata"]], [item["content"]], [changed]]
    monkeypatch.setattr(reader, "rows", lambda statement: replies.pop(0))
    with pytest.raises(ValidationError, match="changed during export"):
        reader.snapshot("flight", IDS["flight"])


def test_import_rejects_preview_and_inconsistent_versions(tmp_path: Path) -> None:
    project, source = setup(tmp_path)
    with pytest.raises(ValidationError, match="never preview"):
        run_import(project, target="preview", selectors=[], all_resources=False, write=True, snapshot_path=source)
    item = copy.deepcopy(snapshots()[0])
    item["content"]["flight_version"] = 99
    with pytest.raises(ValidationError, match="mismatch"):
        convert(item, "prod")


def test_native_local_mount_export_is_replaced_without_changing_component() -> None:
    component = "export default function Dive() { return null; }\n"
    source = 'export const REQUIRED_DATABASES = [\n {"path": "old"}\n];\n' + component
    imported = dive_source(source, [{"type": "database", "path": "md:live", "alias": "data"}])
    assert imported.split("\n", 1)[1] == component
    assert imported.count("export const REQUIRED_DATABASES") == 1
    assert '"path": "md:live"' in imported


@pytest.mark.parametrize(("live", "declared", "warned"), [
    ("F32", "F32", False),
    ("F8", None, True),
    (None, None, False),
])
def test_flight_import_keeps_a_declarable_instance_type(live: str | None, declared: str | None, warned: bool) -> None:
    items = snapshots()
    if live is not None:
        items[0]["content"]["instance_type"] = live
    _, files, report = convert(items[0], "prod")
    flight = yaml.safe_load(files["blueprint.yml"])["resources"]["flights"]["imported"]
    assert flight.get("instanceType") == declared
    assert any("instance size" in warning for warning in report["warnings"]) is warned


def test_explicit_null_collections_are_not_mistaken_for_missing_fields() -> None:
    items = snapshots()
    items[0]["content"].update(config=None, flight_secret_names=None, max_runtime_sec=None)
    _, files, _ = convert(items[0], "prod")
    flight = yaml.safe_load(files["blueprint.yml"])["resources"]["flights"]["imported"]
    assert flight["config"] == {} and flight["secrets"] == [] and "maxRuntimeSec" not in flight
    items[1]["content"]["required_resources"] = None
    _, files, _ = convert(items[1], "prod")
    assert yaml.safe_load(files["blueprint.yml"])["resources"]["dives"]["imported"]["requiredResources"] == []


def test_all_import_executes_readonly_sql_contracts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, _ = setup(tmp_path)
    with duckdb.connect() as connection:
        for item in snapshots():
            kind = item["kind"]
            for part in ("metadata", "content"):
                path = tmp_path / f"{kind}-{part}.json"
                path.write_text(json.dumps([item[part]]))
                connection.execute(f"CREATE TABLE {kind}_{part} AS SELECT * FROM read_json(?)", [str(path)])
            id_arg = "flight_id" if kind == "flight" else "id"
            connection.execute(f"CREATE MACRO MD_GET_{kind.upper()}({id_arg}) AS TABLE SELECT * FROM {kind}_metadata")
            if kind != "guide":
                version_arg = "version_number" if kind == "flight" else "version"
                connection.execute(
                    f"CREATE MACRO MD_GET_{kind.upper()}_VERSION({id_arg}, {version_arg}) "
                    f"AS TABLE SELECT * FROM {kind}_content"
                )
            extra = ", include_org_shares := false" if kind == "dive" else ""
            connection.execute(
                f'CREATE MACRO MD_LIST_{kind.upper()}S("limit" := 100, "offset" := 0{extra}) '
                f'AS TABLE SELECT * FROM {kind}_metadata LIMIT "limit" OFFSET "offset"'
            )
        queries = []

        def execute(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            assert argv[1:3] == ["query", "--file"]
            statement = Path(argv[3]).read_text()
            queries.append(statement)
            assert statement.startswith("SELECT ")
            assert kwargs["env"]["MOTHERDUCK_TOKEN"] == "fake-local-only-token"
            result = connection.execute(statement)
            columns = [description[0] for description in result.description]
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return subprocess.CompletedProcess(argv, 0, json.dumps(rows))

        from md_blueprints import motherduck_cli
        monkeypatch.setenv("MOTHERDUCK_TOKEN", "fake-local-only-token")
        monkeypatch.setenv("MD_BLUEPRINTS_SQL_BACKEND", "motherduck")
        monkeypatch.setattr(motherduck_cli, "executable", lambda: "/fake/motherduck")
        monkeypatch.setattr(subprocess, "run", execute)
        report = run_import(project, target="prod", selectors=[], all_resources=True, write=True)
    assert len(report["resources"]) == 3
    assert len(Project(tmp_path).blueprints) == 5
    assert any("MD_GET_DIVE_VERSION" in query for query in queries)
    assert any("MD_GET_FLIGHT_VERSION" in query for query in queries)


def test_import_normalizes_native_javascript_mounts_without_evaluating_code() -> None:
    component = 'export default function Dive() { return null; }\n'
    source = (
        'export const REQUIRED_DATABASES = [\n'
        "  // Native CLI Dives use JavaScript object syntax.\n"
        "  { type: 'database', path: 'md:old', alias: 'data', },\n"
        '] as const;\n' + component
    )
    mounts = [{'type': 'database', 'path': 'md:live', 'alias': 'data'}]
    imported = dive_source(source, mounts)
    assert imported == 'export const REQUIRED_DATABASES = ' + json.dumps(mounts) + ';\n' + component
    for expression in ('[getMounts()]', '[...mounts]', '[{path: "x", path: "y"}]', '[]; runSomething();'):
        with pytest.raises(ValidationError):
            dive_source('export const REQUIRED_DATABASES = ' + expression + '\n' + component, mounts)


@pytest.mark.parametrize("selector", ["flight:abc", "table:00000000-0000-0000-0000-000000000001", "flight"])
def test_invalid_resource_selector_fails_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selector: str,
) -> None:
    from md_blueprints.deploy import Deployer

    project, _ = setup(tmp_path)
    monkeypatch.setattr(Deployer, "_prepare_live_command", lambda *a: pytest.fail("connected before checking selectors"))

    with pytest.raises(ValidationError):
        run_import(project, target="prod", selectors=[selector], all_resources=False, write=False, snapshot_path=None)
