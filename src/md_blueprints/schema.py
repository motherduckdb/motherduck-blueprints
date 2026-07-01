from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from . import __version__


LATEST_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {1}


class ValidationError(Exception):
    pass


def unsupported_schema_version_message(version: int) -> str:
    return (
        f"schemaVersion {version} is not supported by md-blueprints {__version__} "
        f"(supports: {sorted(SUPPORTED_SCHEMA_VERSIONS)}). "
        f"If {version} is newer, bump your motherduckdb/motherduck-blueprints action pin; "
        "if older, run md-blueprints migrate --to latest."
    )


def load_yaml(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"Invalid YAML in {path}: {exc}") from exc


def declared_schema_version(data: object) -> int:
    if isinstance(data, dict):
        version = data.get("schemaVersion", LATEST_SCHEMA_VERSION)
        if isinstance(version, int) and not isinstance(version, bool):
            return version
    return LATEST_SCHEMA_VERSION


def validate_required_cli_version(value: object, *, path: Path) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValidationError(f"{path}.requiredCliVersion must be string")
    try:
        specifier = SpecifierSet(value)
        current = Version(__version__)
    except (InvalidSpecifier, InvalidVersion) as exc:
        raise ValidationError(f"{path}.requiredCliVersion is invalid: {value}") from exc

    if current not in specifier:
        raise ValidationError(
            f"this project requires md-blueprints {value}, you have {__version__} - "
            "bump the action or package pin."
        )


class SchemaValidator:
    def __init__(self) -> None:
        self.schema_root = resources.files("md_blueprints").joinpath("schemas")
        self.schemas: dict[tuple[int, str], dict[str, object]] = {}

    def validate(self, data: object, schema_name: str) -> None:
        version = declared_schema_version(data)
        schema = self.load_schema(schema_name, version)
        self._validate_node(data, schema, "$", schema)

    def load_schema(self, schema_name: str, version: int) -> dict[str, object]:
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValidationError(unsupported_schema_version_message(version))

        key = (version, schema_name)
        if key not in self.schemas:
            schema_path = self.schema_root.joinpath(f"v{version}", schema_name)
            self.schemas[key] = json.loads(schema_path.read_text(encoding="utf-8"))
        return self.schemas[key]

    def _validate_node(self, data: object, schema: object, path: str, root_schema: dict[str, object]) -> None:
        if schema is None or schema is True or schema == {}:
            return
        if not isinstance(schema, dict):
            return

        ref = schema.get("$ref")
        if isinstance(ref, str):
            self._validate_node(data, self._resolve_ref(ref, root_schema), path, root_schema)
            return

        if "const" in schema and data != schema["const"]:
            raise ValidationError(f"{path} must equal {schema['const']!r}")

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and data not in enum_values:
            rendered = ", ".join(repr(value) for value in enum_values)
            raise ValidationError(f"{path} must be one of {rendered}")

        any_of = schema.get("anyOf")
        if isinstance(any_of, list):
            errors = []
            matched = False
            for candidate in any_of:
                try:
                    self._validate_node(data, candidate, path, root_schema)
                    matched = True
                    break
                except ValidationError as exc:
                    errors.append(str(exc))
            if not matched:
                raise ValidationError(f"{path} did not match any allowed shape: {'; '.join(errors)}")

        expected_type = schema.get("type")
        if expected_type is not None:
            self._validate_type(data, expected_type, path)
        if isinstance(data, str):
            self._validate_string(data, schema, path)
        if isinstance(data, list):
            self._validate_array(data, schema, path, root_schema)
        if isinstance(data, dict):
            self._validate_object(data, schema, path, root_schema)

    def _resolve_ref(self, ref: str, root_schema: dict[str, object]) -> object:
        if not ref.startswith("#/"):
            raise ValidationError(f"Unsupported schema ref {ref}")
        node: object = root_schema
        for segment in ref.removeprefix("#/").split("/"):
            if not isinstance(node, dict) or segment not in node:
                raise ValidationError(f"Unsupported schema ref {ref}")
            node = node[segment]
        return node

    def _validate_type(self, data: object, expected: object, path: str) -> None:
        types = expected if isinstance(expected, list) else [expected]
        if any(self._matches_type(data, type_name) for type_name in types):
            return
        raise ValidationError(f"{path} must be {' or '.join(str(type_name) for type_name in types)}")

    def _matches_type(self, data: object, type_name: object) -> bool:
        if type_name == "object":
            return isinstance(data, dict)
        if type_name == "array":
            return isinstance(data, list)
        if type_name == "string":
            return isinstance(data, str)
        if type_name == "integer":
            return isinstance(data, int) and not isinstance(data, bool)
        if type_name == "number":
            return isinstance(data, (int, float)) and not isinstance(data, bool)
        if type_name == "boolean":
            return isinstance(data, bool)
        if type_name == "null":
            return data is None
        raise ValidationError(f"Unsupported schema type {type_name}")

    def _validate_string(self, data: str, schema: dict[str, object], path: str) -> None:
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(data) < min_length:
            raise ValidationError(f"{path} must have length >= {min_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, data) is None:
            raise ValidationError(f"{path} must match {pattern}")

    def _validate_array(
        self,
        data: list[object],
        schema: dict[str, object],
        path: str,
        root_schema: dict[str, object],
    ) -> None:
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(data) < min_items:
            raise ValidationError(f"{path} must contain at least {min_items} item(s)")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(data):
                self._validate_node(item, item_schema, f"{path}[{index}]", root_schema)

    def _validate_object(
        self,
        data: dict[object, object],
        schema: dict[str, object],
        path: str,
        root_schema: dict[str, object],
    ) -> None:
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if key not in data:
                    raise ValidationError(f"{path}.{key} is required")

        raw_properties = schema.get("properties")
        properties: dict[object, object] = raw_properties if isinstance(raw_properties, dict) else {}
        additional = schema.get("additionalProperties")
        for key, value in data.items():
            key_path = f"{path}.{key}"
            if key in properties:
                self._validate_node(value, properties[key], key_path, root_schema)
            elif additional is False:
                raise ValidationError(
                    f"Unknown field {key!r} at {path}. Either it is a typo, or it requires a newer "
                    f"md-blueprints than {__version__} - check the field reference for the version "
                    "that introduced it and bump your action pin."
                )
            elif isinstance(additional, dict):
                self._validate_node(value, additional, key_path, root_schema)
