from __future__ import annotations

from pathlib import Path

import pytest

import md_blueprints.migrations as migrations
from md_blueprints.migrations import run_migrate
from md_blueprints.schema import ValidationError


FIXTURES = Path(__file__).parent / "fixtures"


def test_migrate_latest_is_idempotent_for_current_schema(capsys: pytest.CaptureFixture[str]) -> None:
    run_migrate(FIXTURES / "simple", from_version=None, to_version="latest", write=False)

    assert "No migration needed" in capsys.readouterr().out


def test_migrate_from_mismatch_rejects_project() -> None:
    with pytest.raises(ValidationError, match="--from 2 does not match project schemaVersion set: 1"):
        run_migrate(FIXTURES / "simple", from_version=2, to_version="latest", write=False)


def write_v1_project(root: Path) -> None:
    blueprint_dir = root / "blueprints" / "demo"
    blueprint_dir.mkdir(parents=True)
    (root / "motherduck.yml").write_text(
        """
schemaVersion: 1
repository:
  name: migration-demo
include:
  - blueprints/*/blueprint.yml
targets:
  preview:
    mode: preview
  prod:
    mode: production
""".lstrip(),
        encoding="utf-8",
    )
    (blueprint_dir / "blueprint.yml").write_text(
        """
schemaVersion: 1
name: demo
title: Demo
resources: {}
""".lstrip(),
        encoding="utf-8",
    )


def install_fake_v2_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    def migrate_v1_to_v2(data: dict[str, object]) -> dict[str, object]:
        migrated = dict(data)
        migrated["schemaVersion"] = 2
        migrated["requiredCliVersion"] = ">=2.0"
        return migrated

    class FakeValidator:
        def validate(self, data: object, schema_name: str) -> None:
            assert isinstance(data, dict)
            assert data["schemaVersion"] == 2
            assert schema_name in {"motherduck-root.schema.json", "blueprint.schema.json"}

    monkeypatch.setattr(migrations, "SUPPORTED_SCHEMA_VERSIONS", {1, 2})
    monkeypatch.setattr(migrations, "LATEST_SCHEMA_VERSION", 2)
    monkeypatch.setattr(migrations, "MIGRATIONS", {(1, 2): migrate_v1_to_v2})
    monkeypatch.setattr(migrations, "SchemaValidator", FakeValidator)


def test_future_migration_dry_run_outputs_unified_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_v1_project(tmp_path)
    install_fake_v2_migration(monkeypatch)

    run_migrate(tmp_path, from_version=1, to_version="latest", write=False)

    output = capsys.readouterr().out
    assert f"--- {tmp_path / 'motherduck.yml'}" in output
    assert f"--- {tmp_path / 'blueprints/demo/blueprint.yml'}" in output
    assert "+schemaVersion: 2" in output
    assert "+requiredCliVersion:" in output
    assert ">=2.0" in output
    assert "Dry run only" in output
    assert "schemaVersion: 1" in (tmp_path / "motherduck.yml").read_text(encoding="utf-8")


def test_future_migration_write_then_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_v1_project(tmp_path)
    install_fake_v2_migration(monkeypatch)

    run_migrate(tmp_path, from_version=1, to_version="2", write=True)

    output = capsys.readouterr().out
    assert "Migration written." in output
    assert "schemaVersion: 2" in (tmp_path / "motherduck.yml").read_text(encoding="utf-8")
    assert "schemaVersion: 2" in (tmp_path / "blueprints/demo/blueprint.yml").read_text(encoding="utf-8")

    run_migrate(tmp_path, from_version=None, to_version="latest", write=True)

    assert "No migration needed" in capsys.readouterr().out
