from __future__ import annotations

import json
import math
import re
from pathlib import Path
from uuid import UUID

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from . import __version__
from .assets import schema_root


LATEST_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {1}


class ValidationError(Exception):
    pass


# Keywords SchemaValidator enforces. Annotation-only keywords are listed separately
# so tests can prove that every keyword used by the packaged schemas is understood.
ENFORCED_SCHEMA_KEYWORDS = frozenset({
    "$ref", "const", "enum", "anyOf", "oneOf", "type",
    "minLength", "maxLength", "pattern", "format",
    "minimum", "maximum",
    "minItems", "maxItems", "uniqueItems", "items",
    "required", "properties", "additionalProperties",
})
ANNOTATION_SCHEMA_KEYWORDS = frozenset({"$id", "$schema", "$defs", "title", "description", "default", "examples"})

_TEMPLATE_REFERENCE = re.compile(r"(?<!\\)\$\{[^}]+\}")


def has_template_reference(value: str) -> bool:
    return _TEMPLATE_REFERENCE.search(value) is not None


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
    except OSError as exc:
        raise ValidationError(f"Could not read YAML file {path}: {exc}") from exc


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
        self.schema_root = schema_root()
        self.schemas: dict[tuple[int, str], dict[str, object]] = {}

    def validate(self, data: object, schema_name: str) -> None:
        version = declared_schema_version(data)
        schema = self.load_schema(schema_name, version)
        self._validate_node(data, schema, "$", schema)

    def validate_definition(
        self,
        data: object,
        schema_name: str,
        definition: str,
        *,
        path: str,
        version: int = LATEST_SCHEMA_VERSION,
    ) -> None:
        """Validate one value against ``#/$defs/<definition>`` of a schema."""
        schema = self.load_schema(schema_name, version)
        self._validate_node(data, self._resolve_ref(f"#/$defs/{definition}", schema), path, schema)

    def definition_properties(
        self, schema_name: str, definition: str, *, version: int = LATEST_SCHEMA_VERSION
    ) -> dict[str, object]:
        """Return the ``properties`` map of ``#/$defs/<definition>``, or an empty map."""
        schema = self.load_schema(schema_name, version)
        node = self._resolve_ref(f"#/$defs/{definition}", schema)
        properties = node.get("properties") if isinstance(node, dict) else None
        return properties if isinstance(properties, dict) else {}

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

        one_of = schema.get("oneOf")
        if isinstance(one_of, list):
            matches = 0
            errors = []
            for candidate in one_of:
                try:
                    self._validate_node(data, candidate, path, root_schema)
                    matches += 1
                except ValidationError as exc:
                    errors.append(str(exc))
            if matches != 1:
                detail = f"; {'; '.join(errors)}" if matches == 0 and errors else ""
                raise ValidationError(f"{path} must match exactly one allowed shape (matched {matches}){detail}")

        expected_type = schema.get("type")
        if expected_type is not None:
            self._validate_type(data, expected_type, path)
        if isinstance(data, str):
            self._validate_string(data, schema, path)
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            self._validate_number(data, schema, path)
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
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(data) > max_length:
            raise ValidationError(f"{path} must have length <= {max_length} (got {len(data)})")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, data) is None:
            description = schema.get("description")
            if isinstance(description, str) and description:
                raise ValidationError(f"{path} must be {description}; got {data!r}")
            raise ValidationError(f"{path} must match {pattern}")
        string_format = schema.get("format")
        # Raw manifests may template a value; the rendered resource is checked again.
        if string_format == "uuid" and not has_template_reference(data):
            try:
                UUID(data)
            except ValueError as exc:
                raise ValidationError(f"{path} must be a UUID; got {data!r}") from exc

    def _validate_number(self, data: int | float, schema: dict[str, object], path: str) -> None:
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and data < minimum:
            raise ValidationError(f"{path} must be >= {minimum}")
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and data > maximum:
            raise ValidationError(f"{path} must be <= {maximum}")
        if isinstance(data, float) and not math.isfinite(data):
            raise ValidationError(f"{path} must be a finite number")

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
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(data) > max_items:
            raise ValidationError(f"{path} must contain at most {max_items} item(s)")
        if schema.get("uniqueItems") is True:
            seen: set[str] = set()
            for index, item in enumerate(data):
                fingerprint = json.dumps(item, sort_keys=True, default=str)
                if fingerprint in seen:
                    raise ValidationError(f"{path}[{index}] duplicates an earlier item: {item!r}")
                seen.add(fingerprint)
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
