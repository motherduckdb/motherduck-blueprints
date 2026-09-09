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

from md_blueprints.cli import main
from md_blueprints.deploy import Deployer, PlanRecord
from md_blueprints.importer import ImportReader, convert, run_import, dive_source
from md_blueprints.init import run_init
from md_blueprints.project import CommandError, Project
from md_blueprints.schema import ValidationError


OWNER = "owner@example.test"
IDS = {kind: str(UUID(int=index)) for index, kind in enumerate(("flight", "dive", "guide"), 1)}


def snapshots() -> list[dict[str, Any]]:
    flight = {
        "kind": "flight",
        "metadata": {
            "flight_id": IDS["flight"], "flight_name": "Existing pipeline", "owner_name": OWNER,
            "current_version": 3, "schedule_cron": "0 * * * *", "schedule_status": "SCHEDULE_STATUS_DISABLED",
            "status": "JOB_STATUS_ACTIVE", "updated_at": "2026-09-06",
        },
        "content": {
            "flight_id": IDS["flight"], "flight_version": 3, "source_code": "print('unchanged')\n",
            "requirements_txt": "requests==2.32.0\n", "config": {"DATABASE": "existing_db", "PASSWORD": "do-not-print"},
            "flight_secret_names": ["vendor-key"], "access_token_name": "runtime-token", "max_runtime_sec": 600,
        },
    }
    dive = {
        "kind": "dive",
        "metadata": {
            "id": IDS["dive"], "title": "Existing dashboard", "description": "Keep this", "owner_name": OWNER,
            "current_version": 4, "status": "endorsed", "updated_at": "2026-09-06",
        },
        "content": {
            "version": 4, "api_version": 1, "content": "export default function Dive() { return null; }\n",
            "required_resources": [{"url": "md:_share/data/original", "alias": "revenue", "resource_type": "share"}],
        },
    }
    guide_meta = {
        "id": IDS["guide"], "title": "Existing definitions", "description": "", "topic": "finance",
        "owner_name": OWNER, "current_version": 5, "version": 5, "access": "organization",
        "content": "# Revenue\n\nOriginal definition.\n", "updated_at": "2026-09-06",
        "references": [{"type": "dive", "dive_id": IDS["dive"], "flight_id": None, "guide_id": None}],
    }
    return [flight, dive, {"kind": "guide", "metadata": guide_meta, "content": guide_meta}]


def setup(root: Path) -> tuple[Project, Path]:
    run_init(root)
    source = root / ".imports/source.json"
    source.parent.mkdir()
    source.write_text(json.dumps(snapshots()))
    return Project(root), source


def test_dry_run_and_write_preserve_identity_settings_and_disable_deploy(tmp_path: Path) -> None:
    project, source = setup(tmp_path)
    original = project.manifest_path.read_bytes()
    report = run_import(project, target="prod", selectors=[], all_resources=False, write=False, snapshot_path=source)
    assert len(report["resources"]) == 3
    assert "do-not-print" not in json.dumps(report)
    assert project.manifest_path.read_bytes() == original
    assert not any((tmp_path / item["package"]).exists() for item in report["resources"])
    run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    imported = Project(tmp_path)
    assert ">=0.4.3" in str(imported.manifest["requiredCliVersion"])
    names = [Path(item["package"]).name for item in report["resources"]]
    prod = imported.render_all("prod", names=names)
    resources = {
        kind: resource for bp in prod
        for kind, group in (("flight", bp.flights), ("dive", bp.dives), ("guide", bp.guides))
        for resource in group.values()
    }
    for kind, resource in resources.items():
        assert resource["id"] == IDS[kind]
        assert resource["owner"] == OWNER
        assert resource["deploy"] is False
    assert resources["flight"]["scheduleCron"] == "0 * * * *"
    assert resources["flight"]["manageSchedule"] is False
    assert resources["flight"]["runOnDeploy"] is False
    assert resources["flight"]["config"]["DATABASE"] == "existing_db"  # type: ignore[index]
    assert resources["dive"]["requiredResources"] == [{"url": "md:_share/data/original", "alias": "revenue"}]
    assert "status" not in resources["dive"]
    assert resources["guide"]["references"] == [{"type": "dive", "uuid": IDS["dive"]}]
    for bp in imported.render_all("preview", branch="test/import", names=names):
        for resource in [*bp.flights.values(), *bp.dives.values(), *bp.guides.values()]:
            assert "id" not in resource and resource["deploy"] is False


def test_reimport_keeps_customer_edits(tmp_path: Path) -> None:
    project, source = setup(tmp_path)
    report = run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    script = tmp_path / report["resources"][0]["package"] / "main.py"
    script.write_text("print('customer changes')\n")
    again = run_import(Project(tmp_path), target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    assert {item["action"] for item in again["resources"]} == {"already_managed"}
    assert script.read_text() == "print('customer changes')\n"


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


@pytest.mark.parametrize("kind", ["flight", "dive", "guide"])
def test_bound_id_never_falls_back_to_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    project, _ = setup(tmp_path)
    deployer = Deployer(project)
    bp = project.render_all("prod")[0]
    resource: dict[str, object] = {"id": IDS[kind], "owner": OWNER, "name": "renamed", "title": "renamed"}
    calls = []

    def missing(statement: str) -> list[tuple[object, ...]]:
        calls.append(statement)
        raise CommandError("not found")

    monkeypatch.setattr(deployer, "_query_rows", missing)
    record = deployer._bound_resource_record(bp, kind, "resource", resource)
    assert record.action == "error" and record.id == IDS[kind]
    assert all("MD_GET_" in statement for statement in calls)
    assert not any("MD_LIST_" in statement or "CREATE" in statement for statement in calls)


def test_adopted_flight_renames_by_id_without_running_or_changing_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _ = setup(tmp_path)
    _, files, _ = convert(snapshots()[0], "prod")
    data = yaml.safe_load(files["blueprint.yml"])["resources"]["flights"]["imported"]
    data.update(name="new name", sourcePath="main.py", requirementsPath="requirements.txt")
    deployer = Deployer(project)
    calls: list[str] = []
    def capture(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", capture)
    deployer._deploy_flight(data, "prod", PlanRecord("package", "flight", "imported", "new name", "update", True, IDS["flight"]))
    assert len(calls) == 1
    assert "MD_UPDATE_FLIGHT" in calls[0] and IDS["flight"] in calls[0]
    assert "schedule_cron" not in calls[0] and "MD_RUN_FLIGHT" not in calls[0]
    assert "runtime-token" in calls[0] and "vendor-key" in calls[0]


def test_cli_dry_run_reports_without_source_or_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, source = setup(tmp_path)
    capsys.readouterr()
    assert main(["import", "--root", str(tmp_path), "--snapshot", str(source)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["written"] is False
    assert "do-not-print" not in output and "print('unchanged')" not in output


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


def test_bound_flight_rejects_other_owner_and_preserves_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, _ = setup(tmp_path)
    deployer = Deployer(project)
    bp = project.render_all("prod")[0]
    monkeypatch.setattr(deployer, "_query_rows", lambda statement: [(IDS["flight"], OWNER)])
    monkeypatch.setattr(deployer, "_sql", lambda statement: "different-account")
    record = deployer._bound_resource_record(bp, "flight", "item", {"id": IDS["flight"], "owner": OWNER, "name": "Renamed"})
    assert record.action == "error" and "creator" in record.notes
    monkeypatch.setattr(deployer, "_sql", lambda statement: OWNER)
    record = deployer._bound_resource_record(bp, "flight", "item", {"id": IDS["flight"], "owner": OWNER, "name": "Renamed"})
    assert record.action == "update" and record.id == IDS["flight"]


def test_imported_resources_are_inert_in_deployment_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, source = setup(tmp_path)
    report = run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    project = Project(tmp_path)
    names = [Path(item["package"]).name for item in report["resources"]]
    deployer = Deployer(project)
    monkeypatch.setattr(deployer, "_query_rows", lambda statement: pytest.fail(f"Unexpected live read: {statement}"))
    rendered = project.render_all("prod", names=names)
    records = deployer._build_deploy_plan(rendered)
    assert {record.action for record in records} == {"validated_only"}
    for bp in rendered:
        deployer._deploy_blueprint(bp, "prod", deployer._index_by_resource(records))
    preview = project.render_all("preview", branch="test/import", names=names)
    assert deployer._build_cleanup_plan(preview, "test_import", branch="test/import") == []


def test_reviewed_imports_update_all_original_ids_without_creating_replacements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, source = setup(tmp_path)
    report = run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    names = []
    for item in report["resources"]:
        path = tmp_path / item["package"] / "blueprint.yml"
        data = yaml.safe_load(path.read_text())
        resource = data["resources"][item["kind"] + "s"]["imported"]
        resource["targets"]["prod"]["deploy"] = True
        resource["name" if item["kind"] == "flight" else "title"] = "Renamed " + item["kind"]
        path.write_text(yaml.safe_dump(data))
        names.append(data["name"])
    deployer = Deployer(Project(tmp_path))
    statements: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        if "md_list_roles_for_user" in statement:
            return [("admin",)]
        if statement.startswith("SET VARIABLE desired_guide_references"):
            return [("old content", "", "[]", "[]", "Old title", "finance", "", "organization")]
        for kind in IDS:
            if f"MD_GET_{kind.upper()}" in statement:
                return [(IDS[kind], OWNER, "endorsed")] if kind == "dive" else [(IDS[kind], OWNER)]
        pytest.fail(f"Unexpected SQL: {statement}")

    def sql(statement: str) -> str:
        if statement == "SELECT current_user":
            return OWNER
        statements.append(statement)
        return ""

    monkeypatch.setenv("MOTHERDUCK_TOKEN", "fake-local-only-token")
    monkeypatch.setattr(deployer, "_query_rows", rows)
    monkeypatch.setattr(deployer, "_sql", sql)
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: pytest.fail("name-based Flight lookup"))
    monkeypatch.setattr(deployer, "_list_dive_states", lambda title: pytest.fail("name-based Dive lookup"))
    deployer.deploy(target="prod", branch=None, names=names)
    combined = "\n".join(statements)
    assert "MD_CREATE_" not in combined and "MD_RUN_FLIGHT" not in combined
    assert "schedule_cron" not in combined and "MD_UPDATE_DIVE_STATUS" not in combined
    for kind in IDS:
        assert IDS[kind] in combined and f"MD_UPDATE_{kind.upper()}" in combined


@pytest.mark.parametrize("missing", ["flight", "dive", "guide"])
@pytest.mark.parametrize("failure", ["missing", "owner_changed"])
def test_customer_cd_checks_every_bound_id_before_first_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str, failure: str,
) -> None:
    project, source = setup(tmp_path)
    report = run_import(project, target="prod", selectors=[], all_resources=False, write=True, snapshot_path=source)
    names = []
    for item in report["resources"]:
        path = tmp_path / item["package"] / "blueprint.yml"
        data = yaml.safe_load(path.read_text())
        data["resources"][item["kind"] + "s"]["imported"]["targets"]["prod"]["deploy"] = True
        path.write_text(yaml.safe_dump(data))
        names.append(data["name"])
    calls = []

    def rows(self: Deployer, statement: str) -> list[tuple[object, ...]]:
        calls.append(statement)
        assert statement.startswith("SELECT "), "CD must not write before all IDs pass"
        if statement == "SELECT current_user":
            return [(OWNER,)]
        if "md_list_roles_for_user" in statement:
            return [("admin",)]
        for kind in IDS:
            if f"MD_GET_{kind.upper()}(" in statement:
                if kind == missing:
                    if failure == "missing":
                        raise CommandError("resource no longer exists")
                    return [(IDS[kind], "changed-owner", "endorsed")] if kind == "dive" else [(IDS[kind], "changed-owner")]
                return [(IDS[kind], OWNER, "endorsed")] if kind == "dive" else [(IDS[kind], OWNER)]
        pytest.fail(f"Unexpected query: {statement}")

    monkeypatch.setenv("MOTHERDUCK_TOKEN", "test-token")
    monkeypatch.setattr(Deployer, "_query_rows", rows)
    with pytest.raises((ValidationError, CommandError)):
        Deployer(Project(tmp_path)).deploy(target="prod", branch=None, names=names)
    assert calls and all(statement.startswith("SELECT ") for statement in calls)


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
