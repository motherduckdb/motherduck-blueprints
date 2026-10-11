"""End-to-end adoption of existing resources: `import --snapshot`, then plan, deploy, verify, and cleanup."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from e2e_support import IMPORT_IDS, OWNER, Cli, FakeMotherDuck, edit_yaml, import_snapshot, records, snapshot


def write_snapshot(tmp_path: Path) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(import_snapshot()), encoding="utf-8")
    return path


def import_packages(root: Path, md_cli: Cli, source: Path) -> list[str]:
    report = md_cli.ok("import", "--root", str(root), "--snapshot", str(source), "--write").json()
    assert report["written"] is True
    return [Path(item["package"]).name for item in report["resources"]]


def seed_live_resources(fake: FakeMotherDuck, **overrides: dict[str, Any] | None) -> None:
    """The account as it was exported, with optional per-kind changes (None removes the resource)."""
    live: dict[str, dict[str, Any]] = {
        "flight": {"name": "Existing pipeline", "owner": OWNER, "schedule": "0 * * * *"},
        "dive": {"title": "Existing dashboard", "owner": OWNER, "status": "endorsed"},
        "guide": {
            "title": "Existing definitions", "topic": "finance", "owner": OWNER, "access": "organization",
            "content": "# Revenue\n\nOriginal definition.\n",
        },
    }
    state: dict[str, dict[str, Any]] = {"flights": {}, "dives": {}, "guides": {}}
    for kind, resource in live.items():
        change = overrides.get(kind, {})
        if change is not None:
            state[f"{kind}s"][IMPORT_IDS[kind]] = {**resource, **change}
    fake.seed(current_user=OWNER, **state)


def enable_reviewed_imports(root: Path, names: list[str], *, rename: bool = False) -> None:
    for name in names:
        package = next(path for path in root.glob(f"*/{name}") if (path / "blueprint.yml").is_file())

        def enable(data: dict[str, Any]) -> None:
            group, resource = next(
                (group, resources["imported"]) for group, resources in data["resources"].items()
            )
            resource["targets"]["prod"]["deploy"] = True
            if rename:
                resource["name" if group == "flights" else "title"] = f"Renamed {group[:-1]}"

        edit_yaml(package / "blueprint.yml", enable)


def test_import_reports_first_then_writes_disabled_packages_that_stay_inert(
    tmp_path: Path, starter: Path, md_cli: Cli,
) -> None:
    fake = md_cli.fake
    source = write_snapshot(tmp_path)
    root = ("--root", str(starter))
    before = snapshot(starter)
    for args in ((), ("--write", "--dry-run")):
        report = md_cli.ok("import", *root, "--snapshot", str(source), *args)
        assert report.json()["written"] is False and len(report.json()["resources"]) == 3
        assert "do-not-print" not in report.stdout and "print('unchanged')" not in report.stdout
    assert snapshot(starter) == before

    names = import_packages(starter, md_cli, source)
    md_cli.ok("validate", *root)
    prod = md_cli.ok("render", *root, "--blueprints", ",".join(names)).json()
    resources = {
        kind: resource for blueprint in prod
        for kind in ("flight", "dive", "guide") for resource in blueprint[f"{kind}s"].values()
    }
    for kind, resource in resources.items():
        assert (resource["id"], resource["owner"], resource["deploy"]) == (IMPORT_IDS[kind], OWNER, False)
    flight = resources["flight"]
    assert (flight["scheduleCron"], flight["manageSchedule"], flight["runOnDeploy"]) == ("0 * * * *", False, False)
    assert flight["config"]["DATABASE"] == "existing_db"
    assert resources["dive"]["requiredResources"] == [{"url": "md:_share/data/original", "alias": "revenue"}]
    assert "status" not in resources["dive"]
    assert resources["guide"]["references"] == [{"type": "dive", "uuid": IMPORT_IDS["dive"]}]
    preview = md_cli.ok("render", *root, "--target", "preview", "--branch", "test/import", "--blueprints", ",".join(names))
    for blueprint in preview.json():
        for resource in [*blueprint["flights"].values(), *blueprint["dives"].values(), *blueprint["guides"].values()]:
            assert "id" not in resource and resource["deploy"] is False

    selection = ("--blueprints", ",".join(names))
    plan = records(md_cli.ok("plan", *root, *selection, "--json"))
    assert {row["action"] for row in plan.values()} == {"validated_only"}
    md_cli.ok("deploy", *root, *selection)
    md_cli.ok("cleanup", *root, "--branch", "test/import", *selection)
    assert fake.queries() == []

    # verify checks the disabled bindings against the live account without enabling them.
    seed_live_resources(fake)
    verified = records(md_cli.ok("verify", *root, *selection, "--json"))
    assert {(key[1], row["action"], row["id"]) for key, row in verified.items()} == {
        (kind, "verified", IMPORT_IDS[kind]) for kind in ("flight", "dive", "guide")
    }
    assert fake.mutations() == []

    flight_source = next(starter.glob("flights/*/main.py"))
    flight_source.write_text("print('customer changes')\n", encoding="utf-8")
    again = md_cli.ok("import", *root, "--snapshot", str(source), "--write").json()
    assert {item["action"] for item in again["resources"]} == {"already_managed"}
    assert flight_source.read_text(encoding="utf-8") == "print('customer changes')\n"


def test_reviewed_imports_update_the_original_ids_and_never_create_replacements(
    tmp_path: Path, starter: Path, md_cli: Cli,
) -> None:
    fake = md_cli.fake
    names = import_packages(starter, md_cli, write_snapshot(tmp_path))
    enable_reviewed_imports(starter, names, rename=True)
    seed_live_resources(fake)

    md_cli.ok("deploy", "--root", str(starter), "--blueprints", ",".join(names))
    writes = "\n".join(fake.mutations())
    assert "MD_CREATE_" not in writes and "MD_RUN_FLIGHT" not in writes
    assert "schedule_cron" not in writes and "MD_UPDATE_DIVE_STATUS" not in writes
    for kind in ("flight", "dive", "guide"):
        assert any(f"MD_UPDATE_{kind.upper()}" in query and IMPORT_IDS[kind] in query for query in fake.mutations())
    flight_update = next(query for query in fake.mutations() if "MD_UPDATE_FLIGHT" in query)
    assert "'runtime-token'" in flight_update and "'vendor-key'" in flight_update
    assert not any("MD_LIST_" in query for query in fake.queries())
    assert fake.ids("flights") == {"Renamed flight": IMPORT_IDS["flight"]}
    assert fake.ids("dives") == {"Renamed dive": IMPORT_IDS["dive"]}
    assert fake.ids("guides") == {"Renamed guide": IMPORT_IDS["guide"]}
    assert fake.state()["dives"][IMPORT_IDS["dive"]]["status"] == "endorsed"
    assert fake.state()["flights"][IMPORT_IDS["flight"]]["schedule"] == "0 * * * *"


@pytest.mark.parametrize(("kind", "change", "message"), [
    ("flight", None, "configured Flight id is missing or inaccessible; refusing to create a replacement"),
    # The imported Guide also references this Dive by UUID; both problems are reported as plan errors.
    ("dive", None, "configured Dive id is missing or inaccessible; refusing to create a replacement"),
    ("guide", None, "configured Guide id is missing or inaccessible; refusing to create a replacement"),
    ("flight", {"owner": "changed-owner"}, "live owner differs from the imported owner"),
    ("dive", {"owner": "changed-owner"}, "live owner differs from the imported owner"),
    ("guide", {"owner": "changed-owner"}, "live owner differs from the imported owner"),
    ("current_user", "different-account", "only the Flight creator can update it"),
])
def test_bound_ids_are_checked_before_the_first_write_and_never_fall_back_to_names(
    tmp_path: Path, starter: Path, md_cli: Cli, kind: str, change: Any, message: str,
) -> None:
    fake = md_cli.fake
    names = import_packages(starter, md_cli, write_snapshot(tmp_path))
    enable_reviewed_imports(starter, names)
    if kind == "current_user":
        seed_live_resources(fake)
        fake.seed(current_user=change)
    else:
        seed_live_resources(fake, **{kind: change})

    result = md_cli.fails("deploy", "--root", str(starter), "--blueprints", ",".join(names))
    assert message in result.stderr
    assert fake.mutations() == []
    assert not any("MD_LIST_" in query for query in fake.queries())
