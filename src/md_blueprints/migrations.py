from __future__ import annotations

import copy
import difflib
from collections.abc import Callable
from pathlib import Path

import yaml

from .schema import LATEST_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS, SchemaValidator, ValidationError, load_yaml

Migration = Callable[[dict[str, object]], dict[str, object]]
MIGRATIONS: dict[tuple[int, int], Migration] = {}


def project_manifest_files(root: Path) -> list[Path]:
    manifest_path = root / "motherduck.yml"
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise ValidationError("motherduck.yml must be an object")

    project_files = [manifest_path]
    include = manifest.get("include", [])
    for pattern in include if isinstance(include, list) else []:
        project_files.extend(sorted(root.glob(str(pattern))))
    return project_files


def migration_path(source_version: int, target_version: int) -> list[Migration]:
    if source_version == target_version:
        return []
    direction = 1 if target_version > source_version else -1
    current = source_version
    migrations: list[Migration] = []
    while current != target_version:
        next_version = current + direction
        migration = MIGRATIONS.get((current, next_version))
        if migration is None:
            raise ValidationError(f"No migration is available from schemaVersion {current} to {next_version}")
        migrations.append(migration)
        current = next_version
    return migrations


def migrate_document(data: dict[str, object], migrations: list[Migration]) -> dict[str, object]:
    migrated = copy.deepcopy(data)
    for migration in migrations:
        migrated = migration(migrated)
        if not isinstance(migrated, dict):
            raise ValidationError("Migration returned a non-object document")
    return migrated


def dump_yaml(data: dict[str, object]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def run_migrate(root: Path, *, from_version: int | None, to_version: str, write: bool) -> None:
    target_version = LATEST_SCHEMA_VERSION if to_version == "latest" else int(to_version)
    if target_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValidationError(f"schemaVersion {target_version} is not supported by this md-blueprints release")

    project_files = project_manifest_files(root)
    documents: list[tuple[Path, dict[str, object]]] = []
    versions: set[int] = set()
    for path in project_files:
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise ValidationError(f"{path} must be an object")
        version = data.get("schemaVersion")
        if isinstance(version, int) and not isinstance(version, bool):
            versions.add(version)
        documents.append((path, data))

    if from_version is not None and versions and versions != {from_version}:
        rendered = ", ".join(str(version) for version in sorted(versions))
        raise ValidationError(f"--from {from_version} does not match project schemaVersion set: {rendered}")

    if versions == {target_version}:
        print(f"No migration needed; schemaVersion {target_version} is already current for this project.")
        return

    if not versions:
        raise ValidationError("No schemaVersion values found to migrate")
    if len(versions) != 1:
        rendered = ", ".join(str(version) for version in sorted(versions))
        raise ValidationError(f"Cannot migrate mixed schemaVersion set in one pass: {rendered}")

    source_version = next(iter(versions))
    if source_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValidationError(f"Cannot migrate unsupported schemaVersion {source_version} with this CLI")

    migrations = migration_path(source_version, target_version)
    if not migrations:
        print("No migration changes were generated.")
        return

    validator = SchemaValidator()
    diffs: list[str] = []
    for path, data in documents:
        migrated = migrate_document(data, migrations)
        schema_name = "motherduck-root.schema.json" if path.name == "motherduck.yml" else "blueprint.schema.json"
        validator.validate(migrated, schema_name)

        original = path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated_text = dump_yaml(migrated)
        updated = updated_text.splitlines(keepends=True)
        if original != updated:
            diffs.extend(difflib.unified_diff(original, updated, fromfile=str(path), tofile=str(path)))
            if write:
                path.write_text(updated_text, encoding="utf-8")

    if not diffs:
        print("No migration changes were generated.")
        return

    print("".join(diffs), end="")
    if write:
        print("Migration written.")
    else:
        print("Dry run only. Re-run with --write to apply these changes.")
