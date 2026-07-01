from __future__ import annotations

from pathlib import Path

import pytest

from md_blueprints.project import Project
from md_blueprints.schema import SchemaValidator, ValidationError


def minimal_root(**extra: object) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "repository": {"name": "example"},
        "include": ["blueprints/*/blueprint.yml"],
        "targets": {
            "preview": {"mode": "preview"},
            "prod": {"mode": "production"},
        },
        **extra,
    }


def test_unsupported_schema_version_names_action_pin() -> None:
    data = minimal_root(schemaVersion=2)

    with pytest.raises(ValidationError, match="bump your motherduckdb/motherduck-blueprints action pin"):
        SchemaValidator().validate(data, "motherduck-root.schema.json")


def test_unknown_field_error_explains_additive_upgrade_path() -> None:
    data = minimal_root(refreshWindow="daily")

    with pytest.raises(ValidationError) as exc:
        SchemaValidator().validate(data, "motherduck-root.schema.json")

    message = str(exc.value)
    assert "Unknown field 'refreshWindow' at $" in message
    assert "requires a newer md-blueprints" in message
    assert "bump your action pin" in message


def test_required_cli_version_is_checked_before_schema_details(tmp_path: Path) -> None:
    (tmp_path / "motherduck.yml").write_text(
        """
schemaVersion: 1
requiredCliVersion: ">=999.0"
repository:
  name: example
include: []
targets:
  preview:
    mode: preview
  prod:
    mode: production
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="this project requires md-blueprints >=999.0"):
        Project(tmp_path)
