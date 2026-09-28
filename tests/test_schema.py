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


def schema_keywords(node: object, *, in_map: bool = False) -> set[str]:
    """Collect keywords from schema nodes, skipping names inside properties/$defs maps."""
    found: set[str] = set()
    if isinstance(node, list):
        for item in node:
            found |= schema_keywords(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if in_map:
                found |= schema_keywords(value)
                continue
            found.add(str(key))
            found |= schema_keywords(value, in_map=key in {"properties", "$defs"})
    return found


@pytest.mark.parametrize("schema_name", ["blueprint.schema.json", "motherduck-root.schema.json"])
def test_python_validator_understands_every_schema_keyword(schema_name: str) -> None:
    from md_blueprints.schema import ANNOTATION_SCHEMA_KEYWORDS, ENFORCED_SCHEMA_KEYWORDS

    schema = SchemaValidator().load_schema(schema_name, 1)
    unknown = schema_keywords(schema) - ENFORCED_SCHEMA_KEYWORDS - ANNOTATION_SCHEMA_KEYWORDS

    assert unknown == set()


def blueprint_with_guide(**guide: object) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "name": "docs",
        "title": "Docs",
        "resources": {"guides": {"runbook": {"source": "guide.md", **guide}}},
    }


def test_schema_enforces_max_length() -> None:
    SchemaValidator().validate(blueprint_with_guide(title="x" * 255), "blueprint.schema.json")
    with pytest.raises(ValidationError, match=r"title must have length <= 255"):
        SchemaValidator().validate(blueprint_with_guide(title="x" * 256), "blueprint.schema.json")


def test_schema_enforces_uuid_format_but_defers_templates() -> None:
    validator = SchemaValidator()
    validator.validate(blueprint_with_guide(id="00000000-0000-0000-0000-000000000001"), "blueprint.schema.json")
    validator.validate(blueprint_with_guide(id="${var.guide_id}"), "blueprint.schema.json")
    with pytest.raises(ValidationError, match=r"id must be a UUID"):
        validator.validate(blueprint_with_guide(id="not-a-uuid"), "blueprint.schema.json")


def test_schema_enforces_minimum_and_unique_items() -> None:
    validator = SchemaValidator()
    flight = {"name": "loader", "source": "flight.py", "requirements": "requirements.txt"}
    data: dict[str, object] = {
        "schemaVersion": 1,
        "name": "loader",
        "title": "Loader",
        "resources": {"flights": {"loader": {**flight, "maxRuntimeSec": -1}}},
    }
    with pytest.raises(ValidationError, match=r"maxRuntimeSec must be >= 0"):
        validator.validate(data, "blueprint.schema.json")

    data["resources"] = {"roles": {"team": {"name": "team", "members": ["a@example.com", "a@example.com"]}}}
    with pytest.raises(ValidationError, match=r"members\[1\] duplicates an earlier item"):
        validator.validate(data, "blueprint.schema.json")


@pytest.mark.parametrize(
    ("field", "value", "valid"),
    [
        ("access", "ORGANIZATION", True),
        ("access", "unrestricted", True),
        ("access", "${var.share_access}", True),
        ("access", "organisation", False),
        ("visibility", "HIDDEN", True),
        ("visibility", "Discoverable", True),
        ("visibility", "public", False),
    ],
)
def test_share_access_and_visibility_schema(field: str, value: str, valid: bool) -> None:
    data = {
        "schemaVersion": 1,
        "name": "data",
        "title": "Data",
        "resources": {"shares": {"data": {"name": "data", "database": "data", field: value}}},
    }
    if valid:
        SchemaValidator().validate(data, "blueprint.schema.json")
    else:
        with pytest.raises(ValidationError, match=f"{field} must be one of"):
            SchemaValidator().validate(data, "blueprint.schema.json")
