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


def test_required_resource_schema_requires_exactly_one_selector() -> None:
    manifest = {
        "schemaVersion": 1,
        "name": "bad-dive",
        "title": "Bad Dive",
        "resources": {
            "dives": {
                "dashboard": {
                    "title": "Bad Dive",
                    "source": "src/dive.tsx",
                    "requiredResources": [
                        {
                            "share": "local",
                            "url": "md:_share/example/id",
                            "alias": "data",
                        }
                    ],
                }
            }
        },
    }

    with pytest.raises(ValidationError, match="exactly one allowed shape"):
        SchemaValidator().validate(manifest, "blueprint.schema.json")


def test_blueprint_schema_still_accepts_all_variable_shapes() -> None:
    manifest = {
        "schemaVersion": 1,
        "name": "variables",
        "title": "Variables",
        "variables": {
            "plain": "value",
            "count": 2,
            "enabled": True,
            "documented": {"description": "A value", "default": "value"},
        },
        "resources": {},
    }

    SchemaValidator().validate(manifest, "blueprint.schema.json")


def test_blueprint_schema_accepts_current_guide_rbac_and_runtime_features() -> None:
    manifest = {
        "schemaVersion": 1,
        "name": "governed-analytics",
        "title": "Governed analytics",
        "resources": {
            "roles": {
                "finance": {
                    "name": "finance",
                    "includedRoles": ["explorer"],
                    "members": ["finance@example.com"],
                    "mode": "authoritative",
                    "deploy": True,
                }
            },
            "shares": {
                "data": {
                    "name": "finance",
                    "database": "finance",
                    "includePattern": None,
                    "grants": {"roles": ["finance"], "mode": "authoritative"},
                }
            },
            "flights": {
                "loader": {
                    "name": "finance-loader",
                    "source": "flight.py",
                    "requirements": "requirements.txt",
                    "maxRuntimeSec": 900,
                }
            },
            "dives": {
                "dashboard": {
                    "title": "Finance",
                    "source": "dive.tsx",
                    "status": "endorsed",
                    "requiredResources": [{"share": "data", "alias": "finance"}],
                }
            },
            "guides": {
                "definitions": {
                    "title": "Finance definitions",
                    "topic": "finance/metrics",
                    "source": "guide.md",
                    "access": "organization",
                    "deploy": True,
                    "references": [
                        {
                            "type": "catalog",
                            "share": "data",
                            "schema": "reporting",
                            "table": "metrics",
                        },
                        {"type": "dive", "resource": "dashboard"},
                    ],
                }
            },
        },
    }

    SchemaValidator().validate(manifest, "blueprint.schema.json")
