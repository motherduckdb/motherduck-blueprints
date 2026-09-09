"""Read-only discovery and review-first, UUID-bound adoption."""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
import json5
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .deploy import Deployer, sql_string
from . import __version__
from .project import Project, require_within
from .schema import ValidationError

KINDS = {"flight": "flights", "dive": "dives", "guide": "guides"}
PAGE_SIZE = 100
IMPORT_VERSION = "0.4.3"


def checked_uuid(value: object) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise ValidationError(f"Invalid resource UUID: {value!r}") from exc


def required(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ValidationError(f"Export is missing {key}; refusing a lossy import")
    return data[key]


def literal(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("$" + "{", "\\" + "$" + "{")
    if isinstance(value, dict):
        return {key: literal(item) for key, item in value.items()}
    if isinstance(value, list):
        return [literal(item) for item in value]
    return value


def dive_source(source: str, mounts: list[dict[str, Any]]) -> str:
    match = re.search(r"^export const REQUIRED_DATABASES\s*=\s*", source, re.MULTILINE)
    if not match and re.search(r"\b(?:const|let|var)\s+REQUIRED_DATABASES\b", source):
        raise ValidationError("Unsupported REQUIRED_DATABASES declaration; use a static array export before import")
    if match:
        value, error, end = json5.parse(source, start=match.end(), consume_trailing=False, allow_duplicate_keys=False)
        if error:
            raise ValidationError("REQUIRED_DATABASES must be a static array before import")
        if not isinstance(value, list):
            raise ValidationError("REQUIRED_DATABASES must be an array")
        tail = end
        suffix = re.match(r"[ \t]*(?:as[ \t]+const)?[ \t]*;?[ \t]*(?:\r?\n|$)", source[tail:])
        if suffix is None:
            raise ValidationError("Unsupported expression after REQUIRED_DATABASES")
        source = source[:match.start()] + source[tail + suffix.end():]
    return "export const REQUIRED_DATABASES = " + json.dumps(mounts) + ";\n" + source


def guarded_manifest(project: Project) -> tuple[str, str, dict[str, object]]:
    before = project.manifest_path.read_text(encoding="utf-8")
    if yaml.safe_load(before) != project.manifest:
        raise ValidationError("motherduck.yml changed during import; retry")
    spec = str(project.manifest.get("requiredCliVersion", ""))
    if Version(__version__) not in SpecifierSet(spec):
        raise ValidationError("requiredCliVersion excludes the importer release; review the constraint first")
    updated_spec = str(SpecifierSet(",".join(filter(None, [spec, f">={IMPORT_VERSION}"]))))
    document = yaml.compose(before)
    assert isinstance(document, yaml.MappingNode)
    after = before
    for key, value in document.value:
        if key.value == "requiredCliVersion":
            original_value = before[value.start_mark.index:value.end_mark.index]
            replacement = (
                original_value.replace(value.value, updated_spec, 1)
                if value.value in original_value else json.dumps(updated_spec)
            )
            after = before[:value.start_mark.index] + replacement + before[value.end_mark.index:]
            break
    else:
        after = before.rstrip() + "\nrequiredCliVersion: " + json.dumps(updated_spec) + "\n"
    expected = {**project.manifest, "requiredCliVersion": updated_spec}
    try:
        matches = yaml.safe_load(after) == expected
    except yaml.YAMLError as exc:
        raise ValidationError("Could not preserve motherduck.yml while updating the CLI guard; nothing was written") from exc
    if not matches:
        raise ValidationError("CLI guard would change other manifest values; update requiredCliVersion explicitly first")
    return before, after, expected


class ImportReader:
    def __init__(self, deployer: Deployer) -> None:
        self.deployer = deployer

    def rows(self, function: str) -> list[dict[str, Any]]:
        rows = self.deployer._query_rows(f"SELECT to_json(item) FROM {function} AS item")
        result = []
        for row in rows:
            data = json.loads(str(row[0]))
            if not isinstance(data, dict):
                raise ValidationError("Unexpected MotherDuck response; expected an object")
            result.append(data)
        return result

    def inventory(self, kind: str) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        offset = 0
        while True:
            extra = ", include_org_shares := true" if kind == "dive" else ""
            page = self.rows(
                f'MD_LIST_{KINDS[kind].upper()}("limit" := {PAGE_SIZE}::UINTEGER, '
                f'"offset" := {offset}::UINTEGER{extra})'
            )
            if not page:
                return result
            ids = [checked_uuid(item["flight_id" if kind == "flight" else "id"]) for item in page]
            if seen.intersection(ids) or len(ids) != len(set(ids)):
                raise ValidationError("Catalog changed or pagination repeated an ID; retry the import")
            result.extend(ids)
            seen.update(ids)
            offset += len(page)

    def snapshot(self, kind: str, resource_id: str) -> dict[str, Any]:
        argument = "flight_id" if kind == "flight" else "id"
        getter = f"MD_GET_{kind.upper()}({argument} := {sql_string(resource_id)}::UUID)"
        rows = self.rows(getter)
        if len(rows) != 1:
            raise ValidationError(f"Could not read {kind} {resource_id}")
        metadata = rows[0]
        if checked_uuid(required(metadata, argument)) != resource_id:
            raise ValidationError("Returned identity differs from the requested UUID")
        version = required(metadata, "current_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValidationError(f"Invalid version for {kind} {resource_id}")
        if kind in {"flight", "dive"}:
            version_key = "version_number" if kind == "flight" else "version"
            versions = self.rows(
                f"MD_GET_{kind.upper()}_VERSION({argument} := {sql_string(resource_id)}::UUID, "
                f"{version_key} := {version}::UINTEGER)"
            )
            if len(versions) != 1:
                raise ValidationError(f"Could not read version {version} of {kind} {resource_id}")
            content = versions[0]
            actual_version = required(content, "flight_version" if kind == "flight" else "version")
            if type(actual_version) is not int or actual_version != version:
                raise ValidationError("Returned version differs from the requested snapshot")
        else:
            content = metadata
        final = self.rows(getter)
        if len(final) != 1 or any(
            final[0].get(key) != metadata.get(key) for key in ("current_version", "updated_at")
        ):
            raise ValidationError(f"{kind} {resource_id} changed during export; retry")
        return {"kind": kind, "metadata": metadata, "content": content}


def convert(snapshot: dict[str, Any], target: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    kind = required(snapshot, "kind")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValidationError(f"Unsupported import kind {kind!r}")
    meta, content = required(snapshot, "metadata"), required(snapshot, "content")
    if not isinstance(meta, dict) or not isinstance(content, dict):
        raise ValidationError("Snapshot metadata and content must be objects")
    resource_id = checked_uuid(required(meta, "flight_id" if kind == "flight" else "id"))
    owner = required(meta, "owner_name")
    if not isinstance(owner, str) or not owner:
        raise ValidationError(f"Owner is unknown for {kind} {resource_id}; inspect it before adoption")
    name = required(meta, "flight_name" if kind == "flight" else "title")
    version = required(meta, "current_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValidationError("Imported source version must be a positive integer")
    if not isinstance(name, str) or not name:
        raise ValidationError("Imported resource name/title must not be empty")
    slug = f"imported-{kind}-{resource_id}-{target}"
    resource: dict[str, Any] = {"deploy": False}
    files: dict[str, str] = {}
    warnings = ["Deployment is disabled. Review source/config for secrets and production writes before enabling it."]
    if kind == "flight":
        if (
            checked_uuid(required(content, "flight_id")) != resource_id
            or type(required(content, "flight_version")) is not int or content["flight_version"] != version
        ):
            raise ValidationError("Flight snapshot identity/version mismatch")
        files["main.py"] = required(content, "source_code")
        files["requirements.txt"] = required(content, "requirements_txt") or ""
        resource.update(
            name=name, source="main.py", requirements="requirements.txt",
            scheduleCron=required(meta, "schedule_cron") or "", manageSchedule=False,
            config=required(content, "config"), secrets=required(content, "flight_secret_names"),
            accessTokenName=required(content, "access_token_name") or "",
            maxRuntimeSec=required(content, "max_runtime_sec"), runOnDeploy=False, waitForRun=False,
        )
        if not isinstance(resource["config"], dict) or not isinstance(resource["secrets"], list):
            if resource["config"] is None:
                resource["config"] = {}
            if resource["secrets"] is None:
                resource["secrets"] = []
            if not isinstance(resource["config"], dict) or not isinstance(resource["secrets"], list):
                raise ValidationError("Flight config/secrets have an unsupported shape")
        if resource["maxRuntimeSec"] is None:
            del resource["maxRuntimeSec"]
        warnings.append("manageSchedule: false preserves the live schedule, including paused state.")
    elif kind == "dive":
        if (
            type(required(content, "version")) is not int or content["version"] != version
            or type(required(content, "api_version")) is not int or content["api_version"] != 1
        ):
            raise ValidationError("Dive snapshot version mismatch or unsupported API version")
        mounts = required(content, "required_resources")
        if mounts is None:
            mounts = []
        if not isinstance(mounts, list):
            raise ValidationError("Dive required_resources must be an array")
        resources = []
        preview_mounts = []
        for mount in mounts:
            if not isinstance(mount, dict) or not mount.get("url") or not mount.get("alias"):
                raise ValidationError("Dive mount has no portable URL/alias; resolve it before importing")
            resources.append({"url": mount["url"], "alias": mount["alias"]})
            preview_mounts.append({
                "type": "share" if str(mount["url"]).startswith("md:_share/") else "database",
                "path": mount["url"], "alias": mount["alias"],
            })
        source = required(content, "content")
        if not isinstance(source, str):
            raise ValidationError("Dive source must be text")
        files["index.tsx"] = dive_source(source, preview_mounts)
        resource.update(
            title=name, description=required(meta, "description") or "",
            source="index.tsx", requiredResources=resources,
        )
        warnings.append("Database/share URLs remain external dependencies; data and grants are not copied.")
    else:
        if (
            type(required(content, "version")) is not int or content["version"] != version
            or checked_uuid(required(content, "id")) != resource_id
        ):
            raise ValidationError("Guide snapshot identity/version mismatch")
        files["guide.md"] = required(content, "content")
        references = required(content, "references")
        if references is None:
            references = []
        if not isinstance(references, list):
            raise ValidationError("Guide references must be an array")
        normalized = []
        for reference in references:
            if not isinstance(reference, dict):
                raise ValidationError("Guide reference must be an object")
            result = {key: value for key, value in reference.items() if value is not None and value != ""}
            for reference_kind in KINDS:
                value = result.pop(f"{reference_kind}_id", None)
                if value is not None:
                    result["uuid"] = checked_uuid(value)
            normalized.append(result)
        resource.update(
            source="guide.md", title=name, topic=required(meta, "topic") or "",
            description=required(meta, "description") or "", access=required(meta, "access"),
            references=normalized,
        )
    if any(not isinstance(value, str) for value in files.values()):
        raise ValidationError("Exported source and requirements must be text")
    resource = literal(resource)
    preview_name = literal(name) + ":" + "$" + "{target.branch} (Preview)"
    resource["targets"] = {
        target: {"id": resource_id, "owner": literal(owner), "deploy": False},
        "preview": {"name" if kind == "flight" else "title": preview_name, "deploy": False},
    }
    if kind == "guide":
        resource["targets"]["preview"]["access"] = "user"
    manifest = {
        "schemaVersion": 1, "name": slug, "title": literal(name),
        "resources": {KINDS[kind]: {"imported": resource}},
    }
    files["blueprint.yml"] = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    report = {
        "kind": kind, "id": resource_id, "name": name, "owner": owner,
        "sourceVersion": required(meta, "current_version"), "sourceUpdatedAt": meta.get("updated_at"),
        "target": target, "package": f"{KINDS[kind]}/{slug}", "warnings": warnings,
        "sourceStatus": meta.get("status"), "scheduleStatus": meta.get("schedule_status"),
        "sourceHashes": {
            filename: hashlib.sha256(contents.encode("utf-8")).hexdigest()
            for filename, contents in files.items() if filename != "blueprint.yml"
        },
    }
    files["import.json"] = json.dumps(report, indent=2) + "\n"
    files["README.md"] = (
        f"# Imported {kind}\n\nBound to {resource_id} in target {target}; original owner: {owner}.\n\n"
        "Deployment is disabled. Review import.json and the source, then enable deploy only in the bound target. "
        "Never remove the id to work around a lookup or permission failure.\n"
    )
    return report["package"], files, report


def run_import(
    project: Project, *, target: str, selectors: list[str], all_resources: bool,
    write: bool, snapshot_path: Path | None = None,
) -> dict[str, Any]:
    if target == "preview" or project.target_config(target).get("mode") != "production":
        raise ValidationError("Import requires a stable target such as prod or staging, never preview")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", target):
        raise ValidationError("Import target must use lowercase letters, digits, and hyphens")
    before_manifest, after_manifest, manifest = guarded_manifest(project)
    if snapshot_path is None and (bool(selectors) == all_resources):
        raise ValidationError("Choose --all or one or more --resource KIND:UUID selectors")
    if snapshot_path is not None and (selectors or all_resources):
        raise ValidationError("--snapshot cannot be combined with --all or --resource")
    snapshots: list[dict[str, Any]] = []
    read_identity: str | None = None
    if snapshot_path:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValidationError("Snapshot must be an array of {kind, metadata, content} objects")
        snapshots = data
    else:
        deployer = Deployer(project)
        deployer._prepare_live_command(target, "import")
        read_identity = deployer._sql("SELECT current_user").strip()
        reader = ImportReader(deployer)
        selected: list[tuple[str, str]] = []
        if all_resources:
            selected = [(kind, resource_id) for kind in KINDS for resource_id in reader.inventory(kind)]
        else:
            for value in selectors:
                kind, separator, resource_id = value.partition(":")
                if not separator or kind not in KINDS:
                    raise ValidationError("--resource must be flight:UUID, dive:UUID, or guide:UUID")
                selected.append((kind, checked_uuid(resource_id)))
        snapshots = [reader.snapshot(kind, resource_id) for kind, resource_id in dict.fromkeys(selected)]
    proposals: list[tuple[str, dict[str, str]]] = []
    reports = []
    seen: set[tuple[str, str]] = set()
    paths = {bp.name: bp.dir.relative_to(project.root).as_posix() for bp in project.blueprints}
    existing = {
        (kind, str(resource["id"])): paths[blueprint.name]
        for blueprint in project.render_all(target)
        for kind, group in (("flight", blueprint.flights), ("dive", blueprint.dives), ("guide", blueprint.guides))
        for resource in group.values() if resource.get("id")
    }
    for snapshot in snapshots:
        relative, files, report = convert(snapshot, target)
        report["readIdentity"] = read_identity
        if read_identity and report["owner"] != read_identity:
            report["warnings"].append("This object belongs to another identity; visibility does not grant update rights.")
        files["import.json"] = json.dumps(report, indent=2) + "\n"
        identity = (report["kind"], report["id"])
        if identity in seen:
            raise ValidationError(f"Duplicate snapshot identity {identity}; nothing was written")
        seen.add(identity)
        if identity in existing:
            report["action"] = "already_managed"
            report["package"] = existing[identity]
        else:
            destination = require_within(project.root / relative, project.root, "Import destination")
            if destination.exists():
                raise ValidationError(f"Import destination exists: {relative}; no existing files will be overwritten")
            report["action"] = "import"
            proposals.append((relative, files))
        reports.append(report)
    if proposals:
        with tempfile.TemporaryDirectory(prefix="md-blueprints-import-") as temporary:
            staging = Path(temporary)
            (staging / "motherduck.yml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
            for relative, files in proposals:
                destination = staging / relative
                destination.mkdir(parents=True)
                for name, content in files.items():
                    (destination / name).write_text(content, encoding="utf-8")
            candidate = Project(staging)
            if len(candidate.blueprints) != len(proposals):
                raise ValidationError("Imported packages do not match motherduck.yml include globs; nothing was written")
            candidate.validate()
            if write:
                created: list[Path] = []
                try:
                    for relative, files in proposals:
                        destination = require_within(project.root / relative, project.root, "Import destination")
                        destination.mkdir(parents=True, exist_ok=False)
                        created.append(destination)
                        for name, content in files.items():
                            with (destination / name).open("x", encoding="utf-8") as handle:
                                os.fchmod(handle.fileno(), 0o600)
                                handle.write(content)
                    Project(project.root).validate()
                    if project.manifest_path.read_text(encoding="utf-8") != before_manifest:
                        raise ValidationError("motherduck.yml changed during import; retry")
                    manifest_temp: Path | None = None
                    try:
                        with tempfile.NamedTemporaryFile(mode="w", dir=project.root, delete=False) as handle:
                            manifest_temp = Path(handle.name)
                            handle.write(after_manifest)
                        manifest_temp.chmod(project.manifest_path.stat().st_mode & 0o777)
                        manifest_temp.replace(project.manifest_path)
                    finally:
                        if manifest_temp:
                            manifest_temp.unlink(missing_ok=True)
                except Exception:
                    for path in reversed(created):
                        shutil.rmtree(path)
                    raise
    return {"target": target, "written": bool(write and proposals), "resources": reports}
