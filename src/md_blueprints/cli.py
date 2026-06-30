from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

from . import __version__

LATEST_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {1}


class ValidationError(Exception):
    pass


class CommandError(Exception):
    pass


def branch_slug(branch: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", branch.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")[:48]
    return slug or "preview"


def deep_merge(left: object, right: object) -> object:
    if not isinstance(right, dict):
        return left

    merged: dict[str, object] = dict(left) if isinstance(left, dict) else {}
    for key, value in right.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def load_yaml(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"Invalid YAML in {path}: {exc}") from exc


def sql_string(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sql_array(values: list[object]) -> str:
    inner = ", ".join(sql_string(value) for value in values)
    return f"[{inner}]::VARCHAR[]"


def sql_map(values: dict[str, object]) -> str:
    if not values:
        return "map([]::VARCHAR[], []::VARCHAR[])"

    keys = ", ".join(sql_string(key) for key in values.keys())
    rendered_values = ", ".join(sql_string(value) for value in values.values())
    return f"map([{keys}], [{rendered_values}])"


def quote_ident(value: object) -> str:
    rendered = str(value)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", rendered):
        raise ValidationError(f"Unsafe SQL identifier: {rendered!r}")
    return f'"{rendered}"'


def run_command(
    argv: list[str],
    *,
    stdin_data: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> str:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    completed = subprocess.run(
        argv,
        input=stdin_data,
        text=True,
        capture_output=True,
        cwd=str(cwd) if cwd else None,
        env=command_env,
        check=False,
    )
    if completed.returncode == 0:
        return completed.stdout

    stderr = completed.stderr.strip()
    raise CommandError(f"{' '.join(argv)} failed: {stderr}")


class SchemaValidator:
    def __init__(self) -> None:
        schema_root = resources.files("md_blueprints").joinpath("schemas")
        self.schemas = {
            "motherduck-root.schema.json": json.loads(
                schema_root.joinpath("motherduck-root.schema.json").read_text(encoding="utf-8")
            ),
            "blueprint.schema.json": json.loads(
                schema_root.joinpath("blueprint.schema.json").read_text(encoding="utf-8")
            ),
        }

    def validate(self, data: object, schema_name: str) -> None:
        schema = self.schemas[schema_name]
        self._validate_node(data, schema, "$", schema)

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

        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        additional = schema.get("additionalProperties")
        for key, value in data.items():
            key_path = f"{path}.{key}"
            if key in properties:
                self._validate_node(value, properties[key], key_path, root_schema)
            elif additional is False:
                raise ValidationError(f"{key_path} is not allowed")
            elif isinstance(additional, dict):
                self._validate_node(value, additional, key_path, root_schema)


class Template:
    @classmethod
    def render(cls, value: object, context: dict[str, object]) -> object:
        if isinstance(value, str):
            return re.sub(r"\$\{([^}]+)\}", lambda match: str(cls.lookup(match.group(1), context)), value)
        if isinstance(value, list):
            return [cls.render(item, context) for item in value]
        if isinstance(value, dict):
            return {str(cls.render(key, context)): cls.render(item, context) for key, item in value.items()}
        return value

    @staticmethod
    def lookup(path: str, context: dict[str, object]) -> object:
        node: object = context
        for segment in path.split("."):
            if isinstance(node, dict) and segment in node:
                node = node[segment]
            else:
                raise ValidationError(f"Unknown template reference ${{{path}}}")
        return node


@dataclass(frozen=True)
class Blueprint:
    name: str
    title: str
    path: Path
    dir: Path
    raw: dict[str, object]


@dataclass
class RenderedBlueprint:
    name: str
    title: str
    description: str
    shares: dict[str, dict[str, object]]
    flights: dict[str, dict[str, object]]
    dives: dict[str, dict[str, object]]
    contexts: dict[str, dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "shares": self.shares,
            "flights": self.flights,
            "dives": self.dives,
            "contexts": self.contexts,
        }


@dataclass
class PlanRecord:
    blueprint: str
    type: str
    key: str
    name: str
    action: str
    exists: bool | None
    id: str | None
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "blueprint": self.blueprint,
            "type": self.type,
            "key": self.key,
            "name": self.name,
            "action": self.action,
            "exists": self.exists,
            "id": self.id,
            "notes": self.notes,
        }


class PlanFormatter:
    @staticmethod
    def format(records: list[PlanRecord], *, title: str) -> str:
        if not records:
            return f"#### {title}\n\nNo resources selected."

        lines = [
            f"#### {title}",
            "",
            "| Blueprint | Type | Key | Name | Action | Exists | ID | Notes |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for record in records:
            row = [
                record.blueprint,
                record.type,
                record.key,
                record.name,
                record.action,
                PlanFormatter._format_exists(record.exists),
                record.id or "",
                record.notes,
            ]
            lines.append("| " + " | ".join(PlanFormatter._escape_cell(value) for value in row) + " |")
        return "\n".join(lines)

    @staticmethod
    def _format_exists(value: bool | None) -> str:
        if value is None:
            return ""
        return "yes" if value else "no"

    @staticmethod
    def _escape_cell(value: object) -> str:
        return re.sub(r"\s+", " ", str(value).replace("|", "\\|")).strip()


class Project:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.manifest_path = self.root / "motherduck.yml"
        if not self.manifest_path.is_file():
            raise ValidationError(f"motherduck.yml not found in {self.root}")

        self.schema = SchemaValidator()
        manifest = load_yaml(self.manifest_path)
        if not isinstance(manifest, dict):
            raise ValidationError(f"{self.manifest_path} must be an object")
        self.manifest: dict[str, object] = manifest
        self.schema.validate(self.manifest, "motherduck-root.schema.json")
        self.blueprints = self._load_blueprints()

    def validate(self, targets: list[str] | None = None) -> bool:
        target_names = targets or ["preview", "prod"]
        if not self.blueprints:
            raise ValidationError("No blueprints found from include globs")

        for target in target_names:
            branch = "feature/mock-test" if target == "preview" else None
            rendered = self.render_all(target, branch=branch)
            self._validate_uniqueness(target, rendered)
            for blueprint in rendered:
                self._validate_rendered_blueprint(target, branch, blueprint)
        return True

    def render_all(
        self,
        target: str,
        *,
        branch: str | None = None,
        names: list[str] | None = None,
    ) -> list[RenderedBlueprint]:
        return [self._render_blueprint(blueprint, target, branch=branch) for blueprint in self._select_blueprints(names)]

    def all_blueprint_names(self) -> list[str]:
        return [blueprint.name for blueprint in self.blueprints]

    def changed_blueprints(self, *, base: str | None, head: str | None) -> list[str]:
        all_names = self.all_blueprint_names()
        if not base or re.fullmatch(r"0+", base):
            return all_names

        try:
            diff = run_command(["git", "-C", str(self.root), "diff", "--name-only", f"{base}...{head or 'HEAD'}"])
        except CommandError:
            return all_names

        changed_files = [line.strip() for line in diff.splitlines() if line.strip()]
        if not changed_files:
            return []

        global_patterns = [
            "motherduck.yml",
            "schemas/",
            "src/",
            "tools/",
            "scripts/",
            "templates/",
            "pyproject.toml",
            "action.yml",
            ".github/workflows/deploy_blueprints.yaml",
            ".github/workflows/cleanup_preview_blueprints.yaml",
        ]
        if any(
            file == pattern or file.startswith(pattern)
            for file in changed_files
            for pattern in global_patterns
        ):
            return all_names

        changed: list[str] = []
        for blueprint in self.blueprints:
            rel_dir = blueprint.dir.relative_to(self.root).as_posix()
            if any(file == rel_dir or file.startswith(f"{rel_dir}/") for file in changed_files):
                changed.append(blueprint.name)
        return sorted(set(changed))

    def target_config(self, target: str) -> dict[str, object]:
        targets = self.manifest.get("targets")
        if isinstance(targets, dict) and isinstance(targets.get(target), dict):
            return targets[target]
        raise ValidationError(f"Unknown target {target}")

    def _load_blueprints(self) -> list[Blueprint]:
        include = self.manifest.get("include")
        if not isinstance(include, list):
            raise ValidationError("$.include must be array")

        paths: list[Path] = []
        for pattern in include:
            paths.extend(self.root.glob(str(pattern)))

        blueprints: list[Blueprint] = []
        for path in sorted(paths):
            raw = load_yaml(path)
            if not isinstance(raw, dict):
                raise ValidationError(f"{path} must be an object")
            self.schema.validate(raw, "blueprint.schema.json")
            blueprints.append(
                Blueprint(
                    name=str(raw["name"]),
                    title=str(raw["title"]),
                    path=path,
                    dir=path.parent,
                    raw=raw,
                )
            )
        return blueprints

    def _select_blueprints(self, names: list[str] | None) -> list[Blueprint]:
        if not names:
            return self.blueprints

        wanted = set(names)
        selected = [blueprint for blueprint in self.blueprints if blueprint.name in wanted]
        missing = wanted - {blueprint.name for blueprint in selected}
        if missing:
            raise ValidationError(f"Unknown blueprint(s): {', '.join(sorted(missing))}")
        return selected

    def _render_blueprint(self, blueprint: Blueprint, target: str, *, branch: str | None = None) -> RenderedBlueprint:
        target_settings = self.target_config(target)
        if target == "preview" and not branch:
            raise ValidationError("Preview target requires --branch")

        context: dict[str, object] = {
            "repository": self.manifest["repository"],
            "target": {
                "name": target,
                "branch": branch or "",
                "branch_slug": branch_slug(branch or ""),
            },
            "var": {},
            "resources": {"shares": {}},
        }

        raw_variables: dict[str, object] = {}
        raw_variables.update(self._extract_variable_values(self.manifest.get("variables", {})))
        raw_variables.update(self._extract_variable_values(target_settings.get("variables", {})))
        raw_variables.update(self._extract_variable_values(blueprint.raw.get("variables", {})))
        raw_variables.update(
            self._extract_variable_values(
                nested_dict(blueprint.raw, "targets", target, "variables") or {}
            )
        )
        context["var"] = self._render_variables(raw_variables, context)

        resources_node = blueprint.raw["resources"]
        if not isinstance(resources_node, dict):
            raise ValidationError(f"{blueprint.path}.resources must be an object")

        shares = self._render_resources(resources_node.get("shares", {}), target, context)
        for share in shares.values():
            share.setdefault("access", "ORGANIZATION")
            share.setdefault("visibility", "DISCOVERABLE")
        context_resources = context["resources"]
        assert isinstance(context_resources, dict)
        context_shares = context_resources["shares"]
        assert isinstance(context_shares, dict)
        for key, value in shares.items():
            context_shares[key] = value

        flights = self._render_resources(resources_node.get("flights", {}), target, context)
        for flight in flights.values():
            flight["sourcePath"] = str((blueprint.dir / str(flight["source"])).resolve())
            flight["requirementsPath"] = str((blueprint.dir / str(flight["requirements"])).resolve())
            policies = target_settings.get("policies", {})
            if target == "preview" and isinstance(policies, dict) and policies.get("disableSchedules") is True:
                flight["scheduleCron"] = ""
            config = flight.get("config", {})
            flight["config"] = stringify_map(config if isinstance(config, dict) else {})
            flight.setdefault("secrets", [])
            flight.setdefault("accessTokenName", "")
            flight.setdefault("scheduleCron", "")
            flight["runOnDeploy"] = flight.get("runOnDeploy", False)
            flight["waitForRun"] = flight.get("waitForRun", False)

        dives = self._render_resources(resources_node.get("dives", {}), target, context)
        for dive in dives.values():
            dive["sourcePath"] = str((blueprint.dir / str(dive["source"])).resolve())
            dive.setdefault("description", "")

        contexts = self._render_resources(resources_node.get("context", {}), target, context)
        for ctx in contexts.values():
            ctx["sourcePath"] = str((blueprint.dir / str(ctx["source"])).resolve())
            ctx["deploy"] = ctx.get("deploy", False)

        return RenderedBlueprint(
            name=blueprint.name,
            title=str(Template.render(blueprint.title, context)),
            description=str(Template.render(blueprint.raw.get("description", ""), context)),
            shares=shares,
            flights=flights,
            dives=dives,
            contexts=contexts,
        )

    def _render_resources(self, resources: object, target: str, context: dict[str, object]) -> dict[str, dict[str, object]]:
        if not resources:
            return {}
        if not isinstance(resources, dict):
            raise ValidationError("resources entries must be objects")

        rendered: dict[str, dict[str, object]] = {}
        for key, raw_value in resources.items():
            if not isinstance(raw_value, dict):
                raise ValidationError(f"resources.{key} must be an object")
            base = {field: value for field, value in raw_value.items() if field != "targets"}
            target_value = nested_dict(raw_value, "targets", target) or {}
            merged = deep_merge(base, target_value)
            rendered_value = Template.render(merged, context)
            if not isinstance(rendered_value, dict):
                raise ValidationError(f"resources.{key} must render to an object")
            rendered[str(key)] = rendered_value
        return rendered

    def _extract_variable_values(self, variables: object) -> dict[str, object]:
        if not isinstance(variables, dict):
            return {}
        values: dict[str, object] = {}
        for key, value in variables.items():
            if isinstance(value, dict) and "default" in value:
                values[str(key)] = value["default"]
            else:
                values[str(key)] = value
        return values

    def _render_variables(self, variables: dict[str, object], context: dict[str, object]) -> dict[str, str]:
        rendered: dict[str, object] = dict(variables)
        for _ in range(5):
            context["var"] = rendered
            candidate = Template.render(rendered, context)
            if not isinstance(candidate, dict):
                raise ValidationError("variables must render to an object")
            rendered = candidate
        return stringify_map(rendered)

    def _validate_uniqueness(self, target: str, rendered_blueprints: list[RenderedBlueprint]) -> None:
        checks = {
            "Flight name": [flight["name"] for bp in rendered_blueprints for flight in bp.flights.values()],
            "Dive title": [dive["title"] for bp in rendered_blueprints for dive in bp.dives.values()],
            "Share name": [share["name"] for bp in rendered_blueprints for share in bp.shares.values()],
        }
        for label, values in checks.items():
            duplicates = sorted({str(value) for value in values if values.count(value) > 1})
            if duplicates:
                raise ValidationError(f"{label} duplicates in {target}: {', '.join(duplicates)}")

    def _validate_rendered_blueprint(
        self,
        target: str,
        branch: str | None,
        blueprint: RenderedBlueprint,
    ) -> None:
        rendered_branch_slug = branch_slug(branch or "")
        target_settings = self.manifest.get("targets", {})
        target_policies = nested_dict(target_settings, target, "policies") or {}

        for key, share in blueprint.shares.items():
            for field in ["name", "database"]:
                require_nonempty(share.get(field), f"shares.{key}.{field}")
            if share.get("visibility", "DISCOVERABLE") == "HIDDEN" and share.get("access", "ORGANIZATION") != "RESTRICTED":
                raise ValidationError(f"hidden share {blueprint.name}.{key} must use RESTRICTED access")
            if (
                target == "preview"
                and isinstance(target_policies, dict)
                and target_policies.get("requireBranchSlugInDataResources")
            ):
                if rendered_branch_slug not in str(share["name"]):
                    raise ValidationError(
                        f"preview share {blueprint.name}.{key} must include branch slug {rendered_branch_slug}"
                    )
                if share.get("dropDatabase", False) and rendered_branch_slug not in str(share["database"]):
                    raise ValidationError(
                        f"preview database {blueprint.name}.{key} must include branch slug {rendered_branch_slug}"
                    )

        for key, flight in blueprint.flights.items():
            for field in ["name", "sourcePath", "requirementsPath"]:
                require_nonempty(flight.get(field), f"flights.{key}.{field}")
            require_file(Path(str(flight["sourcePath"])))
            require_file(Path(str(flight["requirementsPath"])))
            validate_python(Path(str(flight["sourcePath"])))
            schedule = str(flight.get("scheduleCron", ""))
            if schedule and len(schedule.split()) != 5:
                raise ValidationError(f"flights.{key}.scheduleCron must be a 5-field UTC cron expression")
            if (
                target == "preview"
                and isinstance(target_policies, dict)
                and target_policies.get("disableSchedules")
                and schedule
            ):
                raise ValidationError(f"preview flight {blueprint.name}.{key} must render with schedule disabled")

        for key, dive in blueprint.dives.items():
            for field in ["title", "sourcePath"]:
                require_nonempty(dive.get(field), f"dives.{key}.{field}")
            require_file(Path(str(dive["sourcePath"])))
            required_resources = dive.get("requiredResources")
            if not isinstance(required_resources, list) or not required_resources:
                raise ValidationError(f"dives.{key}.requiredResources must not be empty")

            for index, resource in enumerate(required_resources):
                if not isinstance(resource, dict):
                    raise ValidationError(f"dives.{key}.requiredResources[{index}] must be an object")
                require_nonempty(resource.get("alias"), f"dives.{key}.requiredResources[{index}].alias")
                if resource.get("share"):
                    if str(resource["share"]) not in blueprint.shares:
                        raise ValidationError(
                            f"dives.{key}.requiredResources[{index}] references missing share {resource['share']}"
                        )
                elif not str(resource.get("url", "")):
                    raise ValidationError(f"dives.{key}.requiredResources[{index}] must set share or url")

        for key, ctx in blueprint.contexts.items():
            require_file(Path(str(ctx["sourcePath"])))
            if ctx.get("deploy"):
                raise ValidationError(
                    f"context resource {blueprint.name}.{key} cannot deploy until MotherDuck exposes the context API"
                )


class Deployer:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.sql_env: dict[str, str] | None = None

    def plan(self, *, target: str, branch: str | None, names: list[str] | None) -> list[PlanRecord]:
        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "plan")
        return self._build_deploy_plan(rendered)

    def deploy(self, *, target: str, branch: str | None, names: list[str] | None) -> None:
        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "deploy")
        records = self._build_deploy_plan(rendered)
        self.ensure_plan_succeeds(records)
        plan_index = self._index_by_resource(records)

        for blueprint in rendered:
            self._deploy_blueprint(blueprint, target, plan_index)

    def cleanup_plan(self, *, target: str, branch: str | None, names: list[str] | None) -> list[PlanRecord]:
        if target != "preview":
            raise ValidationError("cleanup is only supported for preview target")

        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "cleanup")
        return self._build_cleanup_plan(rendered, branch_slug(branch or ""))

    def cleanup(self, *, target: str, branch: str | None, names: list[str] | None) -> None:
        records = self.cleanup_plan(target=target, branch=branch, names=names)
        self.ensure_plan_succeeds(records)
        self._apply_cleanup_plan(records)

    def ensure_plan_succeeds(self, records: list[PlanRecord]) -> None:
        errors = [record for record in records if record.action == "error"]
        if not errors:
            return
        details = "; ".join(f"{record.blueprint}.{record.type}.{record.key}: {record.notes}" for record in errors)
        raise ValidationError(f"Plan contains errors: {details}")

    def _validate_and_render(
        self,
        target: str,
        branch: str | None,
        names: list[str] | None,
    ) -> list[RenderedBlueprint]:
        self.project.validate(targets=[target])
        return self.project.render_all(target, branch=branch, names=names)

    def _prepare_live_command(self, target: str, operation: str) -> None:
        deployment = self.project.target_config(target).get("deployment", {})
        token_env_var = "MOTHERDUCK_TOKEN"
        if isinstance(deployment, dict):
            token_env_var = str(deployment.get("tokenEnvVar", token_env_var))
        token = os.environ.get(token_env_var, "")
        if not token:
            raise ValidationError(f"{token_env_var} is required to {operation} target {target}")
        self.sql_env = {"MOTHERDUCK_TOKEN": token}

    def _build_deploy_plan(self, rendered: list[RenderedBlueprint]) -> list[PlanRecord]:
        records: list[PlanRecord] = []
        for blueprint in rendered:
            for key, flight in blueprint.flights.items():
                records.append(
                    self._existing_resource_record(
                        blueprint=blueprint,
                        type_name="flight",
                        key=key,
                        name=str(flight["name"]),
                        ids=self._list_flight_ids(str(flight["name"])),
                        duplicate_note="duplicate Flight name; expected 0 or 1",
                    )
                )

            for key, share in blueprint.shares.items():
                url = self._find_share_url(str(share["name"]))
                records.append(
                    PlanRecord(
                        blueprint=blueprint.name,
                        type="share",
                        key=key,
                        name=str(share["name"]),
                        action="present" if url else "missing",
                        exists=bool(url),
                        id=url or None,
                        notes="produced by Flight/project code; deployer waits for the share URL before dependent Dives",
                    )
                )

            for key, dive in blueprint.dives.items():
                records.append(
                    self._existing_resource_record(
                        blueprint=blueprint,
                        type_name="dive",
                        key=key,
                        name=str(dive["title"]),
                        ids=self._list_dive_ids(str(dive["title"])),
                        duplicate_note="duplicate Dive title; expected 0 or 1",
                    )
                )

            for key, ctx in blueprint.contexts.items():
                records.append(
                    PlanRecord(
                        blueprint=blueprint.name,
                        type="context",
                        key=key,
                        name=Path(str(ctx["sourcePath"])).name,
                        action="validated_only",
                        exists=False,
                        id=None,
                        notes="context deployment is not available yet",
                    )
                )
        return records

    def _build_cleanup_plan(self, rendered: list[RenderedBlueprint], rendered_branch_slug: str) -> list[PlanRecord]:
        records: list[PlanRecord] = []
        for blueprint in rendered:
            for key, dive in blueprint.dives.items():
                title = str(dive["title"])
                ids = self._list_dive_ids(title)
                if not ids:
                    records.append(self._cleanup_record(blueprint, "dive", key, title, "missing", False, None))
                else:
                    for resource_id in ids:
                        records.append(self._cleanup_record(blueprint, "dive", key, title, "delete", True, resource_id))

            for key, flight in blueprint.flights.items():
                name = str(flight["name"])
                ids = self._list_flight_ids(name)
                if not ids:
                    records.append(self._cleanup_record(blueprint, "flight", key, name, "missing", False, None))
                else:
                    for resource_id in ids:
                        records.append(self._cleanup_record(blueprint, "flight", key, name, "delete", True, resource_id))

            for key, share in blueprint.shares.items():
                if not share.get("cleanup", True):
                    continue

                share_name = str(share["name"])
                database_name = str(share["database"])
                if rendered_branch_slug not in share_name:
                    records.append(
                        self._cleanup_record(
                            blueprint,
                            "share",
                            key,
                            share_name,
                            "error",
                            None,
                            None,
                            f"refusing to drop preview share without branch slug {rendered_branch_slug}",
                        )
                    )
                    continue

                share_url = self._find_share_url(share_name)
                if share_url:
                    records.append(self._cleanup_record(blueprint, "share", key, share_name, "drop_share", True, share_url))
                else:
                    records.append(self._cleanup_record(blueprint, "share", key, share_name, "missing", False, None))

                if not share.get("dropDatabase", False):
                    continue

                if rendered_branch_slug not in database_name:
                    records.append(
                        self._cleanup_record(
                            blueprint,
                            "database",
                            key,
                            database_name,
                            "error",
                            None,
                            None,
                            f"refusing to drop preview database without branch slug {rendered_branch_slug}",
                        )
                    )
                    continue

                records.append(
                    self._cleanup_record(
                        blueprint,
                        "database",
                        key,
                        database_name,
                        "drop_database",
                        True,
                        None,
                        "database existence is not inspected; cleanup uses DROP DATABASE IF EXISTS",
                    )
                )
        return records

    def _existing_resource_record(
        self,
        *,
        blueprint: RenderedBlueprint,
        type_name: str,
        key: str,
        name: str,
        ids: list[str],
        duplicate_note: str,
    ) -> PlanRecord:
        if not ids:
            return PlanRecord(blueprint.name, type_name, key, name, "create", False, None)
        if len(ids) == 1:
            return PlanRecord(blueprint.name, type_name, key, name, "update", True, ids[0])
        return PlanRecord(blueprint.name, type_name, key, name, "error", True, ",".join(ids), duplicate_note)

    def _cleanup_record(
        self,
        blueprint: RenderedBlueprint,
        type_name: str,
        key: str,
        name: str,
        action: str,
        exists: bool | None,
        record_id: str | None,
        notes: str = "",
    ) -> PlanRecord:
        return PlanRecord(blueprint.name, type_name, key, name, action, exists, record_id, notes)

    def _index_by_resource(self, records: list[PlanRecord]) -> dict[tuple[str, str, str], PlanRecord]:
        index: dict[tuple[str, str, str], PlanRecord] = {}
        for record in records:
            index.setdefault((record.blueprint, record.type, record.key), record)
        return index

    def _deploy_blueprint(
        self,
        blueprint: RenderedBlueprint,
        target: str,
        plan_index: dict[tuple[str, str, str], PlanRecord],
    ) -> None:
        print(f"Deploying blueprint '{blueprint.name}' to {target}...", file=sys.stderr)
        flight_rows: list[str] = []
        share_rows: list[str] = []
        dive_rows: list[str] = []

        for key, flight in blueprint.flights.items():
            print(f"Deploying Flight {blueprint.name}.{key}...", file=sys.stderr)
            row = self._deploy_flight(flight, target, plan_index[(blueprint.name, "flight", key)])
            if row:
                flight_rows.append(row)

        for share in blueprint.shares.values():
            url = self._wait_for_share(str(share["name"]))
            if target == "preview":
                share_rows.append(f"| {share['name']} | [Open Share]({url}) |")

        for key, dive in blueprint.dives.items():
            print(f"Deploying Dive {blueprint.name}.{key}...", file=sys.stderr)
            row = self._deploy_dive(dive, blueprint.shares, target, plan_index[(blueprint.name, "dive", key)])
            if row:
                dive_rows.append(row)

        if target != "preview":
            return

        print(f"#### {blueprint.title}")
        print()
        self._print_section("Flights", "| Flight | ID | Run started |", "|--------|----|-------------|", flight_rows)
        self._print_section("Shares", "| Share | Link |", "|-------|------|", share_rows)
        self._print_section("Dives", "| Dive | Link |", "|------|------|", dive_rows)

    def _print_section(self, title: str, header: str, separator: str, rows: list[str]) -> None:
        if not rows:
            return
        print(f"##### {title}")
        print()
        print(header)
        print(separator)
        for row in rows:
            print(row)
        print()

    def _deploy_flight(self, flight: dict[str, object], target: str, plan: PlanRecord) -> str | None:
        name = str(flight["name"])
        name_sql = sql_string(name)
        config_sql = sql_map(flight.get("config", {}) if isinstance(flight.get("config"), dict) else {})
        source_sql = f"(SELECT content FROM read_text({sql_string(flight['sourcePath'])}))"
        requirements_sql = f"(SELECT content FROM read_text({sql_string(flight['requirementsPath'])}))"
        common_args = [
            f'"schedule_cron" => {sql_string(flight.get("scheduleCron", ""))}',
            f'"flight_secret_names" => {sql_array(list(flight.get("secrets", [])))}',
            f'"config" => {config_sql}',
            f'"name" => {name_sql}',
            '"source_code" => getvariable(\'source_code\')',
            '"requirements_txt" => getvariable(\'requirements_txt\')',
        ]
        access_token_name = str(flight.get("accessTokenName", ""))
        if access_token_name:
            common_args.insert(3, f'"access_token_name" => {sql_string(access_token_name)}')
        common_args_sql = ", ".join(common_args)

        if plan.action == "create":
            print(f"  Creating new flight '{name}'...", file=sys.stderr)
            self._sql(
                f"SET VARIABLE source_code = {source_sql}; "
                f"SET VARIABLE requirements_txt = {requirements_sql}; "
                f"FROM MD_CREATE_FLIGHT({common_args_sql});"
            )
            ids = self._list_flight_ids(name)
            if len(ids) != 1:
                raise CommandError(f"Expected one Flight named {name} after create, found {len(ids)}")
            flight_id = ids[0]
        elif plan.action == "update":
            print(f"  Updating existing flight '{name}' ({plan.id})...", file=sys.stderr)
            self._sql(
                f"SET VARIABLE source_code = {source_sql}; "
                f"SET VARIABLE requirements_txt = {requirements_sql}; "
                f"FROM MD_UPDATE_FLIGHT(\"flight_id\" => '{plan.id}'::UUID, {common_args_sql});"
            )
            flight_id = str(plan.id)
        else:
            raise ValidationError(f"Cannot deploy Flight {name} with plan action {plan.action}")

        run_started = False
        if flight.get("runOnDeploy", False):
            print(f"  Starting flight run for '{name}'...", file=sys.stderr)
            self._sql(f"FROM MD_RUN_FLIGHT({config_sql}, '{flight_id}'::UUID);")
            run_started = True
            if flight.get("waitForRun", False) == "success":
                self._wait_for_flight_run_success(flight_id)

        return f"| {name} | {flight_id} | {str(run_started).lower()} |" if target == "preview" else None

    def _wait_for_flight_run_success(self, flight_id: str) -> None:
        attempts = max(1, int(os.environ.get("FLIGHT_RUN_POLL_ATTEMPTS", "60")))
        sleep_seconds = int(os.environ.get("FLIGHT_RUN_POLL_SLEEP_SECONDS", "10"))

        for index in range(attempts):
            row = self._sql(
                "SELECT run_number || '|' || status "
                f"FROM MD_LIST_FLIGHT_RUNS(flight_id := '{flight_id}'::UUID) "
                "ORDER BY run_number DESC LIMIT 1"
            ).strip()
            run_number, _, status = row.partition("|")
            if status == "RUN_STATUS_SUCCEEDED":
                return
            if status in {"RUN_STATUS_FAILED", "RUN_STATUS_CANCELLED"}:
                logs = self._sql(
                    f"SELECT logs FROM MD_GET_FLIGHT_LOGS(flight_id := '{flight_id}'::UUID, "
                    f"run_number := {int(run_number or '0')})"
                ).strip()
                raise CommandError(f"Flight run {int(run_number or '0')} ended with {status}. Log tail: {logs}")
            if index < attempts - 1:
                time.sleep(sleep_seconds)

        raise CommandError(f"Timed out waiting for flight {flight_id} to succeed")

    def _wait_for_share(self, share_name: str) -> str:
        attempts = max(1, int(os.environ.get("SHARE_RESOLVE_ATTEMPTS", "18")))
        sleep_seconds = int(os.environ.get("SHARE_RESOLVE_SLEEP_SECONDS", "10"))

        for index in range(attempts):
            url = self._sql(f"SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = {sql_string(share_name)}").strip()
            if url:
                return url
            if index < attempts - 1:
                print(f"  Waiting for share '{share_name}' ({index + 1}/{attempts})...", file=sys.stderr)
                time.sleep(sleep_seconds)

        raise CommandError(f"Timed out waiting for share '{share_name}'")

    def _deploy_dive(
        self,
        dive: dict[str, object],
        shares: dict[str, dict[str, object]],
        target: str,
        plan: PlanRecord,
    ) -> str | None:
        title = str(dive["title"])
        required_resources_sql = self._required_resources_sql(dive["requiredResources"], shares)
        content_sql = (
            "(SELECT regexp_replace(content, 'export const REQUIRED_DATABASES[^\\n]*\\n', '', 'g') "
            f"FROM read_text({sql_string(dive['sourcePath'])}))"
        )
        title_sql = sql_string(title)
        description_sql = sql_string(dive.get("description", ""))

        if plan.action == "create":
            print(f"  Creating new dive '{title}'...", file=sys.stderr)
            dive_id = self._sql(
                f"SET VARIABLE content = {content_sql}; "
                "SELECT id FROM MD_CREATE_DIVE("
                f"title = {title_sql}, content = getvariable('content'), "
                f"description = {description_sql}, api_version = 1, "
                f"required_resources = {required_resources_sql})"
            ).strip()
        elif plan.action == "update":
            print(f"  Updating existing dive '{title}' ({plan.id})...", file=sys.stderr)
            self._sql(
                f"SET VARIABLE content = {content_sql}; "
                f"FROM MD_UPDATE_DIVE_CONTENT(id = '{plan.id}'::UUID, content = getvariable('content'), "
                f"api_version = 1, required_resources = {required_resources_sql}); "
                f"FROM MD_UPDATE_DIVE_METADATA(id = '{plan.id}'::UUID, title = {title_sql}, "
                f"description = {description_sql});"
            )
            dive_id = str(plan.id)
        else:
            raise ValidationError(f"Cannot deploy Dive {title} with plan action {plan.action}")

        print(f"  Deployed: https://app.motherduck.com/dives/{dive_id}", file=sys.stderr)
        return f"| {title} | [Open Dive](https://app.motherduck.com/dives/{dive_id}) |" if target == "preview" else None

    def _required_resources_sql(
        self,
        resources_value: object,
        shares: dict[str, dict[str, object]],
    ) -> str:
        if not isinstance(resources_value, list):
            raise ValidationError("requiredResources must be a list")

        expressions = []
        for resource in resources_value:
            if not isinstance(resource, dict):
                raise ValidationError("requiredResources entries must be objects")
            if resource.get("share"):
                url = self._wait_for_share(str(shares[str(resource["share"])]["name"]))
            else:
                url = str(resource["url"])
            expressions.append(f"{{'url': {sql_string(url)}, 'alias': {sql_string(resource['alias'])}}}")
        return f"[{', '.join(expressions)}]"

    def _apply_cleanup_plan(self, records: list[PlanRecord]) -> None:
        for record in records:
            if (record.type, record.action) == ("dive", "missing"):
                print(f"No preview Dive found for '{record.name}'")
            elif (record.type, record.action) == ("dive", "delete"):
                print(f"Deleting preview Dive {record.id} ({record.name})")
                self._sql(f"FROM MD_DELETE_DIVE(id='{record.id}'::UUID)")
            elif (record.type, record.action) == ("flight", "missing"):
                print(f"No preview Flight found for '{record.name}'")
            elif (record.type, record.action) == ("flight", "delete"):
                print(f"Deleting preview Flight {record.id} ({record.name})")
                self._sql(f"FROM MD_DELETE_FLIGHT('{record.id}'::UUID);")
            elif (record.type, record.action) == ("share", "missing"):
                print(f"No preview share found for '{record.name}'")
            elif (record.type, record.action) == ("share", "drop_share"):
                print(f"Dropping preview share {record.name}")
                self._sql(f"FROM MD_DROP_DATABASE_SHARE({sql_string(record.name)});")
            elif (record.type, record.action) == ("database", "drop_database"):
                print(f"Dropping preview database {record.name}")
                self._sql(f"DROP DATABASE IF EXISTS {quote_ident(record.name)};")

    def _list_flight_ids(self, name: str) -> list[str]:
        return [
            line.strip()
            for line in self._sql(
                'SELECT flight_id FROM MD_LIST_FLIGHTS("offset" => 0::UINTEGER, "limit" => 1000::UINTEGER) '
                f"WHERE flight_name = {sql_string(name)}"
            ).splitlines()
            if line.strip()
        ]

    def _list_dive_ids(self, title: str) -> list[str]:
        return [
            line.strip()
            for line in self._sql(f"SELECT id FROM MD_LIST_DIVES() WHERE title = {sql_string(title)}").splitlines()
            if line.strip()
        ]

    def _find_share_url(self, name: str) -> str:
        lines = self._sql(f"SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = {sql_string(name)}").splitlines()
        return lines[0].strip() if lines else ""

    def _sql(self, statement: str) -> str:
        if self.sql_env is None:
            raise ValidationError("MotherDuck token was not prepared for live command")
        return run_command(["duckdb", "md:", "-csv", "-noheader", "-c", statement], env=self.sql_env).strip()


def nested_dict(node: object, *path: str) -> object | None:
    current = node
    for segment in path:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return current


def stringify_map(values: dict[str, object]) -> dict[str, str]:
    return {str(key): str(value) for key, value in values.items()}


def require_nonempty(value: object, label: str) -> None:
    if str(value or "") == "":
        raise ValidationError(f"{label} is required")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise ValidationError(f"Required file not found: {path}")


def validate_python(path: Path) -> None:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ValidationError(f"Python syntax error in {path}: {exc}") from exc


def run_doctor(root: Path) -> None:
    print(f"md-blueprints version: {__version__}")
    print(f"supported schema versions: {', '.join(str(version) for version in sorted(SUPPORTED_SCHEMA_VERSIONS))}")
    print(f"latest packaged schema version: {LATEST_SCHEMA_VERSION}")
    print(f"project root: {root.resolve()}")
    print(f"duckdb command: {shutil.which('duckdb') or 'not found'}")

    root_manifest = root / "motherduck.yml"
    if not root_manifest.is_file():
        print("project manifest: missing")
        return

    try:
        project = Project(root)
    except (ValidationError, CommandError) as exc:
        print(f"validation: failed ({exc})")
        return

    root_version = project.manifest.get("schemaVersion")
    blueprint_versions = sorted({blueprint.raw.get("schemaVersion") for blueprint in project.blueprints})
    print(f"root schemaVersion: {root_version}")
    print(f"blueprint schemaVersions: {', '.join(str(version) for version in blueprint_versions)}")
    print(f"blueprints discovered: {len(project.blueprints)}")
    print("validation: passed")

    unsupported = {root_version, *blueprint_versions} - SUPPORTED_SCHEMA_VERSIONS
    if unsupported:
        print(f"unsupported schemaVersions: {', '.join(str(version) for version in sorted(unsupported))}")
    elif root_version != LATEST_SCHEMA_VERSION or any(version != LATEST_SCHEMA_VERSION for version in blueprint_versions):
        print("schema status: supported but not latest")
    else:
        print("schema status: latest supported schema")

    print(f"repo schema mirror: {schema_mirror_status(root)}")


def run_check_updates() -> None:
    configured_latest = os.environ.get("MD_BLUEPRINTS_LATEST_VERSION", "").strip()
    print(f"installed md-blueprints: {__version__}")
    if not configured_latest:
        print("latest md-blueprints: unknown (set MD_BLUEPRINTS_LATEST_VERSION to make CI enforce a known latest version)")
        return
    print(f"latest md-blueprints: {configured_latest}")
    if configured_latest != __version__:
        raise ValidationError(f"md-blueprints {__version__} is not the configured latest version {configured_latest}")


def schema_mirror_status(root: Path) -> str:
    schema_dir = root / "schemas"
    if not schema_dir.is_dir():
        return "not present"

    package_schema_root = resources.files("md_blueprints").joinpath("schemas")
    mismatched: list[str] = []
    for name in ["motherduck-root.schema.json", "blueprint.schema.json"]:
        local_path = schema_dir / name
        if not local_path.is_file():
            mismatched.append(f"{name} missing")
            continue
        packaged = package_schema_root.joinpath(name).read_text(encoding="utf-8").strip()
        local = local_path.read_text(encoding="utf-8").strip()
        if packaged != local:
            mismatched.append(f"{name} differs")

    return "in sync with packaged schemas" if not mismatched else "; ".join(mismatched)


def run_migrate(root: Path, *, from_version: int | None, to_version: str, write: bool) -> None:
    target_version = LATEST_SCHEMA_VERSION if to_version == "latest" else int(to_version)
    if target_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValidationError(f"schemaVersion {target_version} is not supported by md-blueprints {__version__}")

    project_files = [root / "motherduck.yml"]
    manifest = load_yaml(root / "motherduck.yml")
    if not isinstance(manifest, dict):
        raise ValidationError("motherduck.yml must be an object")
    include = manifest.get("include", [])
    for pattern in include if isinstance(include, list) else []:
        project_files.extend(sorted(root.glob(str(pattern))))

    versions: set[int] = set()
    for path in project_files:
        data = load_yaml(path)
        if isinstance(data, dict) and isinstance(data.get("schemaVersion"), int):
            versions.add(int(data["schemaVersion"]))

    if from_version is not None and versions and versions != {from_version}:
        rendered = ", ".join(str(version) for version in sorted(versions))
        raise ValidationError(f"--from {from_version} does not match project schemaVersion set: {rendered}")

    if versions == {target_version}:
        print(f"No migration needed; schemaVersion {target_version} is already current for this project.")
        return

    if versions - SUPPORTED_SCHEMA_VERSIONS:
        rendered = ", ".join(str(version) for version in sorted(versions))
        raise ValidationError(f"Cannot migrate unsupported schemaVersion set with this CLI: {rendered}")

    diffs: list[str] = []
    for path in project_files:
        original = path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated = [
            re.sub(r"^schemaVersion:\s*\d+\s*$", f"schemaVersion: {target_version}\n", line)
            for line in original
        ]
        if original != updated:
            diffs.extend(
                difflib.unified_diff(
                    original,
                    updated,
                    fromfile=str(path),
                    tofile=str(path),
                )
            )
            if write:
                path.write_text("".join(updated), encoding="utf-8")

    if not diffs:
        print("No migration changes were generated.")
        return

    print("".join(diffs), end="")
    if write:
        print("Migration written.")
    else:
        print("Dry run only. Re-run with --write to apply these changes.")


def parse_blueprints(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--target")
    parser.add_argument("--branch")
    parser.add_argument("--blueprints")
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from", dest="from_version", type=int)
    parser.add_argument("--to", dest="to_version", default="latest")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--version", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="md-blueprints",
        usage="md-blueprints <validate|render|changed|plan|deploy|cleanup|doctor|check-updates|migrate> [options]",
    )
    parser.add_argument("command", nargs="?")
    add_common_options(parser)
    options = parser.parse_args(argv)

    if options.version:
        print(__version__)
        return 0

    command = options.command
    if not command:
        parser.print_usage(sys.stderr)
        return 2

    try:
        root = Path(options.root)
        names = parse_blueprints(options.blueprints)
        if command == "doctor":
            run_doctor(root)
        elif command == "check-updates":
            run_check_updates()
        elif command == "migrate":
            run_migrate(root, from_version=options.from_version, to_version=options.to_version, write=options.write)
        else:
            project = Project(root)
            if command == "validate":
                targets = [options.target] if options.target else ["preview", "prod"]
                project.validate(targets=targets)
                print(f"Validation passed for {len(project.all_blueprint_names())} blueprint(s).")
            elif command == "render":
                target = options.target or "prod"
                rendered = project.render_all(target, branch=options.branch, names=names)
                print(json.dumps([blueprint.to_dict() for blueprint in rendered], indent=2))
            elif command == "changed":
                changed = project.changed_blueprints(base=options.base, head=options.head or "HEAD")
                print(json.dumps(changed) if options.json else "\n".join(changed))
            elif command == "plan":
                deployer = Deployer(project)
                records = deployer.plan(target=options.target or "prod", branch=options.branch, names=names)
                print(
                    json.dumps([record.to_dict() for record in records], indent=2)
                    if options.json
                    else PlanFormatter.format(records, title="Deployment Plan")
                )
                deployer.ensure_plan_succeeds(records)
            elif command == "deploy":
                Deployer(project).deploy(target=options.target or "prod", branch=options.branch, names=names)
            elif command == "cleanup":
                deployer = Deployer(project)
                if options.dry_run:
                    records = deployer.cleanup_plan(target=options.target or "preview", branch=options.branch, names=names)
                    print(
                        json.dumps([record.to_dict() for record in records], indent=2)
                        if options.json
                        else PlanFormatter.format(records, title="Cleanup Plan")
                    )
                    deployer.ensure_plan_succeeds(records)
                else:
                    deployer.cleanup(target=options.target or "preview", branch=options.branch, names=names)
            else:
                parser.print_usage(sys.stderr)
                return 2
        return 0
    except (ValidationError, CommandError, KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
