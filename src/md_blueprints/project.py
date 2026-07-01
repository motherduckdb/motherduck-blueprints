from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .schema import SchemaValidator, ValidationError, load_yaml, validate_required_cli_version
from .template import Template


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
        validate_required_cli_version(self.manifest.get("requiredCliVersion"), path=self.manifest_path)
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
        target_config = targets.get(target) if isinstance(targets, dict) else None
        if isinstance(target_config, dict):
            return cast(dict[str, object], target_config)
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
