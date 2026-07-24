from __future__ import annotations

import ast
import os
import re
import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from .schema import SchemaValidator, ValidationError, load_yaml, validate_required_cli_version
from .template import Template


DIVE_STATUSES = {"draft", "ready", "endorsed", "archived"}
GUIDE_ACCESS = {"user", "organization"}
ROLE_MODES = {"additive", "authoritative"}


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
    guides: dict[str, dict[str, object]] = field(default_factory=dict)
    roles: dict[str, dict[str, object]] = field(default_factory=dict)
    inputs: dict[str, dict[str, object]] = field(default_factory=dict)
    outputs: dict[str, dict[str, object]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "shares": self.shares,
            "flights": self.flights,
            "dives": self.dives,
            "contexts": self.contexts,
            "guides": self.guides,
            "roles": self.roles,
            "inputs": self.inputs,
            "outputs": self.outputs,
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
        self._blueprints_by_name = {blueprint.name: blueprint for blueprint in self.blueprints}
        self.dependencies, self.consumers = self._validate_contracts()
        self._topological_names = self._topological_sort()

    def validate(self, targets: list[str] | None = None, *, branch: str | None = None) -> bool:
        target_names = targets or ["preview", "prod"]
        if not self.blueprints:
            raise ValidationError("No blueprints found from include globs")

        for target in target_names:
            rendered_branch = (branch or "feature/mock-test") if target == "preview" else None
            rendered = self.render_all(target, branch=rendered_branch)
            self._validate_uniqueness(target, rendered)
            self._validate_role_graph(rendered)
            for blueprint in rendered:
                self._validate_rendered_blueprint(target, rendered_branch, blueprint)
            if target == "preview":
                self._validate_preview_separation(rendered, self.render_all("prod"))
        return True

    def render_all(
        self,
        target: str,
        *,
        branch: str | None = None,
        names: list[str] | None = None,
    ) -> list[RenderedBlueprint]:
        selected = {blueprint.name for blueprint in self._select_blueprints(names)}
        rendered: dict[str, RenderedBlueprint] = {}
        for name in self._topological_names:
            blueprint = self._blueprints_by_name[name]
            rendered[name] = self._render_blueprint(
                blueprint,
                target,
                branch=branch,
                rendered_blueprints=rendered,
            )
        return [rendered[name] for name in self._topological_names if name in selected]

    def all_blueprint_names(self) -> list[str]:
        return list(self._topological_names)

    def deployment_blueprint_names(self, target: str, names: list[str] | None) -> list[str]:
        """Expand an explicit deployment selection according to target graph semantics."""
        selected = {blueprint.name for blueprint in self._select_blueprints(names)}
        if not names:
            return list(self._topological_names)

        expanded = set(selected)
        queue = deque(sorted(selected))
        while queue:
            name = queue.popleft()
            related = set(self.consumers[name])
            if target == "preview":
                related.update(self.dependencies[name])
            for candidate in sorted(related):
                if candidate not in expanded:
                    expanded.add(candidate)
                    queue.append(candidate)
        return [name for name in self._topological_names if name in expanded]

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

        paths: set[Path] = set()
        for pattern in include:
            rendered_pattern = str(pattern)
            pattern_path = Path(rendered_pattern)
            if pattern_path.is_absolute() or ".." in pattern_path.parts:
                raise ValidationError(f"Include pattern must stay within the project root: {rendered_pattern}")
            for path in self.root.glob(rendered_pattern):
                paths.add(require_within(path, self.root, f"Included blueprint {path}"))

        blueprints: list[Blueprint] = []
        blueprint_paths: dict[str, Path] = {}
        for path in sorted(paths):
            raw = load_yaml(path)
            if not isinstance(raw, dict):
                raise ValidationError(f"{path} must be an object")
            self.schema.validate(raw, "blueprint.schema.json")
            name = str(raw["name"])
            if name in blueprint_paths:
                raise ValidationError(
                    f"Duplicate blueprint name {name!r}: {blueprint_paths[name]} and {path}"
                )
            blueprint_paths[name] = path
            self._validate_canonical_path(path, name, raw)
            blueprints.append(
                Blueprint(
                    name=name,
                    title=str(raw["title"]),
                    path=path,
                    dir=path.parent,
                    raw=raw,
                )
            )
        return blueprints

    def _validate_canonical_path(self, path: Path, name: str, raw: dict[str, object]) -> None:
        relative = path.relative_to(self.root)
        if not relative.parts:
            return
        root = relative.parts[0]
        if root not in {"flights", "dives", "guides", "roles", "projects"}:
            return
        if path.parent.name != name:
            raise ValidationError(
                f"Canonical blueprint path {relative} must use a parent directory matching name {name!r}"
            )

        resources = raw.get("resources")
        assert isinstance(resources, dict)
        populated = {str(key) for key, value in resources.items() if isinstance(value, dict) and value}
        allowed = {
            "flights": {"shares", "flights"},
            "dives": {"dives"},
            "guides": {"guides", "context"},
            "roles": {"roles"},
            "projects": {"shares", "flights", "dives", "guides", "context", "roles"},
        }[root]
        disallowed = populated - allowed
        if disallowed:
            raise ValidationError(
                f"Canonical {root}/ blueprint {name!r} cannot declare resource group(s): "
                f"{', '.join(sorted(disallowed))}"
            )
        required_groups = {
            "flights": {"flights"},
            "dives": {"dives"},
            "guides": {"guides", "context"},
            "roles": {"roles"},
            "projects": set(),
        }[root]
        if required_groups and not (populated & required_groups):
            expected = " or ".join(sorted(required_groups))
            raise ValidationError(f"Canonical {root}/ blueprint {name!r} must declare {expected} resources")

    def _validate_contracts(self) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        dependencies: dict[str, set[str]] = {blueprint.name: set() for blueprint in self.blueprints}
        consumers: dict[str, set[str]] = {blueprint.name: set() for blueprint in self.blueprints}
        for blueprint in self.blueprints:
            outputs = blueprint.raw.get("outputs", {})
            if isinstance(outputs, dict):
                shares = nested_dict(blueprint.raw, "resources", "shares") or {}
                assert isinstance(shares, dict)
                for output_name, output_value in outputs.items():
                    assert isinstance(output_value, dict)
                    share_key = str(output_value["share"])
                    if share_key not in shares:
                        raise ValidationError(
                            f"blueprint {blueprint.name!r} output {output_name!r} references missing share {share_key!r}"
                        )

            inputs = blueprint.raw.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            for input_name, input_value in inputs.items():
                assert isinstance(input_value, dict)
                producer_name = str(input_value["blueprint"])
                output_name = str(input_value["output"])
                if producer_name == blueprint.name:
                    raise ValidationError(f"blueprint {blueprint.name!r} input {input_name!r} cannot reference itself")
                producer = self._blueprints_by_name.get(producer_name)
                if producer is None:
                    raise ValidationError(
                        f"blueprint {blueprint.name!r} input {input_name!r} references missing blueprint {producer_name!r}"
                    )
                producer_outputs = producer.raw.get("outputs", {})
                if not isinstance(producer_outputs, dict) or output_name not in producer_outputs:
                    raise ValidationError(
                        f"blueprint {blueprint.name!r} input {input_name!r} references missing output "
                        f"{producer_name}.{output_name}"
                    )
                dependencies[blueprint.name].add(producer_name)
                consumers[producer_name].add(blueprint.name)

            guides = nested_dict(blueprint.raw, "resources", "guides") or {}
            if not isinstance(guides, dict):
                continue
            for guide_key, guide_value in guides.items():
                if not isinstance(guide_value, dict):
                    continue
                references = guide_value.get("references", [])
                if not isinstance(references, list):
                    continue
                for index, reference in enumerate(references):
                    if not isinstance(reference, dict):
                        continue
                    producer_name = str(reference.get("blueprint", blueprint.name))
                    resource_key = str(reference.get("resource", ""))
                    reference_type = str(reference.get("type", ""))
                    if not resource_key:
                        continue
                    producer = self._blueprints_by_name.get(producer_name)
                    if producer is None:
                        raise ValidationError(
                            f"guide {blueprint.name}.{guide_key} reference {index} uses missing blueprint "
                            f"{producer_name!r}"
                        )
                    group_name = {
                        "dive": "dives",
                        "flight": "flights",
                        "guide": "guides",
                    }.get(reference_type)
                    producer_resources = producer.raw.get("resources", {})
                    group = producer_resources.get(group_name, {}) if isinstance(producer_resources, dict) else {}
                    if group_name is None or not isinstance(group, dict) or resource_key not in group:
                        raise ValidationError(
                            f"guide {blueprint.name}.{guide_key} reference {index} uses missing "
                            f"{producer_name}.{reference_type}.{resource_key}"
                        )
                    if producer_name != blueprint.name:
                        dependencies[blueprint.name].add(producer_name)
                        consumers[producer_name].add(blueprint.name)
        return dependencies, consumers

    def _topological_sort(self) -> list[str]:
        indegree = {name: len(dependencies) for name, dependencies in self.dependencies.items()}
        ready = sorted(name for name, count in indegree.items() if count == 0)
        ordered: list[str] = []
        while ready:
            name = ready.pop(0)
            ordered.append(name)
            for consumer in sorted(self.consumers[name]):
                indegree[consumer] -= 1
                if indegree[consumer] == 0:
                    ready.append(consumer)
                    ready.sort()
        if len(ordered) != len(self.blueprints):
            cycle = self._find_dependency_cycle()
            raise ValidationError(f"Blueprint dependency cycle: {' -> '.join(cycle)}")
        return ordered

    def _find_dependency_cycle(self) -> list[str]:
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(name: str) -> list[str] | None:
            if name in visiting:
                index = visiting.index(name)
                return visiting[index:] + [name]
            if name in visited:
                return None
            visiting.append(name)
            for dependency in sorted(self.dependencies[name]):
                cycle = visit(dependency)
                if cycle:
                    return cycle
            visiting.pop()
            visited.add(name)
            return None

        for name in sorted(self.dependencies):
            cycle = visit(name)
            if cycle:
                return cycle
        return []

    def _select_blueprints(self, names: list[str] | None) -> list[Blueprint]:
        if not names:
            return self.blueprints

        wanted = set(names)
        selected = [blueprint for blueprint in self.blueprints if blueprint.name in wanted]
        missing = wanted - {blueprint.name for blueprint in selected}
        if missing:
            raise ValidationError(f"Unknown blueprint(s): {', '.join(sorted(missing))}")
        return selected

    def _render_blueprint(
        self,
        blueprint: Blueprint,
        target: str,
        *,
        branch: str | None = None,
        rendered_blueprints: dict[str, RenderedBlueprint],
    ) -> RenderedBlueprint:
        target_settings = self.target_config(target)
        if target == "preview" and not branch:
            raise ValidationError("Preview target requires --branch")

        rendered_inputs: dict[str, dict[str, object]] = {}
        raw_inputs = blueprint.raw.get("inputs", {})
        if isinstance(raw_inputs, dict):
            for input_name, input_value in raw_inputs.items():
                assert isinstance(input_value, dict)
                producer_name = str(input_value["blueprint"])
                output_name = str(input_value["output"])
                producer_output = rendered_blueprints[producer_name].outputs[output_name]
                rendered_inputs[str(input_name)] = {
                    **producer_output,
                    "blueprint": producer_name,
                    "output": output_name,
                }

        context: dict[str, object] = {
            "repository": self.manifest["repository"],
            "target": {
                "name": target,
                "branch": branch or "",
                "branch_slug": branch_slug(branch or ""),
            },
            "var": {},
            "resources": {"shares": {}, "roles": {}},
            "inputs": rendered_inputs,
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

        roles = self._render_resources(resources_node.get("roles", {}), target, context)
        for role in roles.values():
            role.setdefault("includedRoles", [])
            role.setdefault("members", [])
            role.setdefault("mode", "additive")
            role["deploy"] = role.get("deploy", target == "prod")
            if target == "preview":
                role["deploy"] = False
        context_resources = context["resources"]
        assert isinstance(context_resources, dict)
        context_roles = context_resources["roles"]
        assert isinstance(context_roles, dict)
        context_roles.update(roles)

        shares = self._render_resources(resources_node.get("shares", {}), target, context)
        for share in shares.values():
            share.setdefault("access", "ORGANIZATION")
            share.setdefault("visibility", "DISCOVERABLE")
            grants = share.get("grants", {})
            if isinstance(grants, dict):
                grants.setdefault("roles", [])
                grants.setdefault("users", [])
                grants.setdefault("mode", "additive")
        context_shares = context_resources["shares"]
        assert isinstance(context_shares, dict)
        for key, value in shares.items():
            context_shares[key] = value

        flights = self._render_resources(resources_node.get("flights", {}), target, context)
        for flight in flights.values():
            flight["sourcePath"] = str(
                require_within(
                    blueprint.dir / str(flight["source"]),
                    blueprint.dir,
                    f"Flight source for {blueprint.name}",
                )
            )
            flight["requirementsPath"] = str(
                require_within(
                    blueprint.dir / str(flight["requirements"]),
                    blueprint.dir,
                    f"Flight requirements for {blueprint.name}",
                )
            )
            policies = target_settings.get("policies", {})
            if target == "preview" and isinstance(policies, dict) and policies.get("disableSchedules") is True:
                flight["scheduleCron"] = ""
            config = flight.get("config", {})
            flight["config"] = stringify_map(config if isinstance(config, dict) else {})
            flight.setdefault("secrets", [])
            flight.setdefault("accessTokenName", "")
            flight.setdefault("scheduleCron", "")
            if "maxRuntimeSec" in flight:
                flight["maxRuntimeSec"] = int(str(flight["maxRuntimeSec"]))
            flight["runOnDeploy"] = flight.get("runOnDeploy", False)
            flight["waitForRun"] = flight.get("waitForRun", False)

        dives = self._render_resources(resources_node.get("dives", {}), target, context)
        for dive in dives.values():
            dive["sourcePath"] = str(
                require_within(
                    blueprint.dir / str(dive["source"]),
                    blueprint.dir,
                    f"Dive source for {blueprint.name}",
                )
            )
            dive.setdefault("description", "")
            if target == "preview":
                dive.setdefault("status", "draft")

        contexts = self._render_resources(resources_node.get("context", {}), target, context)
        for ctx in contexts.values():
            ctx["sourcePath"] = str(
                require_within(
                    blueprint.dir / str(ctx["source"]),
                    blueprint.dir,
                    f"Context source for {blueprint.name}",
                )
            )
            ctx["deploy"] = ctx.get("deploy", False)

        guides = self._render_resources(resources_node.get("guides", {}), target, context)
        for guide in guides.values():
            guide["sourcePath"] = str(
                require_within(
                    blueprint.dir / str(guide["source"]),
                    blueprint.dir,
                    f"Guide source for {blueprint.name}",
                )
            )
            guide.setdefault("topic", "")
            guide.setdefault("description", "")
            guide.setdefault("access", "user")
            guide.setdefault("references", [])
            guide.setdefault("cleanup", True)
            guide["deploy"] = guide.get("deploy", False)

        outputs: dict[str, dict[str, object]] = {}
        raw_outputs = blueprint.raw.get("outputs", {})
        if isinstance(raw_outputs, dict):
            for output_name, output_value in raw_outputs.items():
                assert isinstance(output_value, dict)
                share_key = str(output_value["share"])
                outputs[str(output_name)] = {"share": share_key, **shares[share_key]}

        return RenderedBlueprint(
            name=blueprint.name,
            title=str(Template.render(blueprint.title, context)),
            description=str(Template.render(blueprint.raw.get("description", ""), context)),
            shares=shares,
            flights=flights,
            dives=dives,
            contexts=contexts,
            guides=guides,
            roles=roles,
            inputs=rendered_inputs,
            outputs=outputs,
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
        checks: dict[str, list[object]] = {
            "Flight name": [flight["name"] for bp in rendered_blueprints for flight in bp.flights.values()],
            "Dive title": [dive["title"] for bp in rendered_blueprints for dive in bp.dives.values()],
            "Share name": [share["name"] for bp in rendered_blueprints for share in bp.shares.values()],
            "Role name": [role["name"] for bp in rendered_blueprints for role in bp.roles.values()],
            "Guide topic/title": [
                f"{guide.get('topic', '')}\0{guide['title']}"
                for bp in rendered_blueprints
                for guide in bp.guides.values()
                if guide.get("deploy")
            ],
        }
        for label, values in checks.items():
            duplicates = sorted({str(value) for value in values if values.count(value) > 1})
            if duplicates:
                raise ValidationError(f"{label} duplicates in {target}: {', '.join(duplicates)}")

    def _validate_role_graph(self, rendered_blueprints: list[RenderedBlueprint]) -> None:
        managed_names = {
            str(role["name"])
            for blueprint in rendered_blueprints
            for role in blueprint.roles.values()
        }
        dependencies: dict[str, set[str]] = {name: set() for name in managed_names}
        for blueprint in rendered_blueprints:
            for role in blueprint.roles.values():
                name = str(role["name"])
                included = role.get("includedRoles", [])
                if not isinstance(included, list):
                    continue
                for value in included:
                    included_name = str(value)
                    if included_name == name:
                        raise ValidationError(f"Role {name!r} cannot include itself")
                    if included_name in managed_names:
                        dependencies[name].add(included_name)

        remaining = {name: set(values) for name, values in dependencies.items()}
        while remaining:
            ready = [name for name, values in remaining.items() if not values]
            if not ready:
                cycle = ", ".join(sorted(remaining))
                raise ValidationError(f"Role dependency cycle: {cycle}")
            for name in ready:
                remaining.pop(name)
            for values in remaining.values():
                values.difference_update(ready)

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
            include_pattern = share.get("includePattern")
            if include_pattern is not None and not isinstance(include_pattern, list):
                raise ValidationError(f"shares.{key}.includePattern must be an array")
            self._validate_grants(share.get("grants"), f"shares.{key}.grants")
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
            if (
                target == "preview"
                and not includes_branch_scope(str(flight["name"]), branch)
            ):
                raise ValidationError(
                    f"preview Flight {blueprint.name}.{key} must include branch name or slug {rendered_branch_slug}"
                )
            max_runtime = flight.get("maxRuntimeSec")
            if max_runtime is not None and (not isinstance(max_runtime, int) or isinstance(max_runtime, bool) or max_runtime < 0):
                raise ValidationError(f"flights.{key}.maxRuntimeSec must be a non-negative integer")

        for key, dive in blueprint.dives.items():
            for field in ["title", "sourcePath"]:
                require_nonempty(dive.get(field), f"dives.{key}.{field}")
            require_file(Path(str(dive["sourcePath"])))
            required_resources = dive.get("requiredResources")
            status = dive.get("status")
            if status is not None and status not in DIVE_STATUSES:
                raise ValidationError(
                    f"dives.{key}.status must be one of {', '.join(sorted(DIVE_STATUSES))}"
                )
            if target == "preview" and status != "draft":
                raise ValidationError(f"preview Dive {blueprint.name}.{key} must use draft status")
            if (
                target == "preview"
                and not includes_branch_scope(str(dive["title"]), branch)
            ):
                raise ValidationError(
                    f"preview Dive {blueprint.name}.{key} must include branch name or slug {rendered_branch_slug}"
                )
            if not isinstance(required_resources, list) or not required_resources:
                raise ValidationError(f"dives.{key}.requiredResources must not be empty")

            aliases: set[str] = set()
            for index, resource in enumerate(required_resources):
                if not isinstance(resource, dict):
                    raise ValidationError(f"dives.{key}.requiredResources[{index}] must be an object")
                require_nonempty(resource.get("alias"), f"dives.{key}.requiredResources[{index}].alias")
                alias = str(resource["alias"])
                if alias in aliases:
                    raise ValidationError(f"dives.{key}.requiredResources has duplicate alias {alias!r}")
                aliases.add(alias)
                selectors = [key for key in ("share", "url", "input") if str(resource.get(key, ""))]
                if len(selectors) != 1:
                    raise ValidationError(
                        f"dives.{key}.requiredResources[{index}] must set exactly one of share, url, or input"
                    )
                if resource.get("share"):
                    if str(resource["share"]) not in blueprint.shares:
                        raise ValidationError(
                            f"dives.{key}.requiredResources[{index}] references missing share {resource['share']}"
                        )
                elif resource.get("input") and str(resource["input"]) not in blueprint.inputs:
                    raise ValidationError(
                        f"dives.{key}.requiredResources[{index}] references missing input {resource['input']}"
                    )

        for key, ctx in blueprint.contexts.items():
            require_file(Path(str(ctx["sourcePath"])))
            if ctx.get("deploy"):
                raise ValidationError(
                    f"context resource {blueprint.name}.{key} cannot deploy until MotherDuck exposes the context API"
                )

        for key, guide in blueprint.guides.items():
            require_nonempty(guide.get("sourcePath"), f"guides.{key}.sourcePath")
            if guide.get("deploy"):
                require_nonempty(guide.get("title"), f"guides.{key}.title")
            require_file(Path(str(guide["sourcePath"])))
            content = Path(str(guide["sourcePath"])).read_text(encoding="utf-8")
            if not content:
                raise ValidationError(f"guides.{key}.source must not be empty")
            if len(content.encode("utf-8")) > 1024 * 1024:
                raise ValidationError(f"guides.{key}.source must be at most 1048576 UTF-8 bytes")
            access = str(guide.get("access", "user"))
            if access not in GUIDE_ACCESS:
                raise ValidationError(f"guides.{key}.access must be one of {', '.join(sorted(GUIDE_ACCESS))}")
            if target == "preview" and guide.get("deploy"):
                if guide.get("id"):
                    raise ValidationError(f"preview Guide {blueprint.name}.{key} must not use a production id")
                if not (
                    includes_branch_scope(str(guide["title"]), branch)
                    or includes_branch_scope(str(guide.get("topic", "")), branch)
                ):
                    raise ValidationError(
                        f"preview Guide {blueprint.name}.{key} title or topic must include branch name or slug "
                        f"{rendered_branch_slug}"
                    )
            self._validate_guide_references(blueprint, key, guide.get("references"))
        self._validate_guide_reference_cycles(blueprint)

        for key, role in blueprint.roles.items():
            require_nonempty(role.get("name"), f"roles.{key}.name")
            mode = str(role.get("mode", "additive"))
            if mode not in ROLE_MODES:
                raise ValidationError(f"roles.{key}.mode must be one of {', '.join(sorted(ROLE_MODES))}")
            if str(role["name"]).lower() in {"admin", "builder", "explorer"}:
                raise ValidationError(f"roles.{key}.name uses reserved preset role {role['name']!r}")
            if target == "preview" and role.get("deploy"):
                raise ValidationError(f"preview role {blueprint.name}.{key} cannot deploy")

    def _validate_preview_separation(
        self,
        preview_blueprints: list[RenderedBlueprint],
        production_blueprints: list[RenderedBlueprint],
    ) -> None:
        production = {blueprint.name: blueprint for blueprint in production_blueprints}
        resource_fields = [
            ("Flight", "flights", "name"),
            ("Dive", "dives", "title"),
            ("share", "shares", "name"),
            ("database", "shares", "database"),
        ]
        for preview in preview_blueprints:
            prod = production.get(preview.name)
            if prod is None:
                continue
            for label, group_name, field in resource_fields:
                preview_group = cast(dict[str, dict[str, object]], getattr(preview, group_name))
                production_group = cast(dict[str, dict[str, object]], getattr(prod, group_name))
                for key, resource in preview_group.items():
                    production_resource = production_group.get(key)
                    if production_resource is not None and resource.get(field) == production_resource.get(field):
                        raise ValidationError(
                            f"preview {label} {preview.name}.{key} must not match its production {field}: "
                            f"{resource.get(field)}"
                        )
            for key, guide in preview.guides.items():
                production_guide = prod.guides.get(key)
                if (
                    guide.get("deploy")
                    and production_guide is not None
                    and guide.get("title") == production_guide.get("title")
                ):
                    raise ValidationError(
                        f"preview Guide {preview.name}.{key} must not match its production title: "
                        f"{guide.get('title')}"
                    )

    def _validate_grants(self, grants: object, label: str) -> None:
        if grants is None:
            return
        if not isinstance(grants, dict):
            raise ValidationError(f"{label} must be an object")
        mode = str(grants.get("mode", "additive"))
        if mode not in ROLE_MODES:
            raise ValidationError(f"{label}.mode must be one of {', '.join(sorted(ROLE_MODES))}")

    def _validate_guide_references(
        self,
        blueprint: RenderedBlueprint,
        guide_key: str,
        references: object,
    ) -> None:
        if not isinstance(references, list):
            raise ValidationError(f"guides.{guide_key}.references must be an array")
        for index, reference in enumerate(references):
            label = f"guides.{guide_key}.references[{index}]"
            if not isinstance(reference, dict):
                raise ValidationError(f"{label} must be an object")
            reference_type = str(reference.get("type", ""))
            if reference_type == "catalog":
                sources = [name for name in ("url", "share", "input") if reference.get(name)]
                if len(sources) != 1:
                    raise ValidationError(f"{label} must set exactly one of url, share, or input")
                if reference.get("share") and str(reference["share"]) not in blueprint.shares:
                    raise ValidationError(f"{label} references missing share {reference['share']!r}")
                if reference.get("input") and str(reference["input"]) not in blueprint.inputs:
                    raise ValidationError(f"{label} references missing input {reference['input']!r}")
                narrowings = [name for name in ("table", "view", "macro") if reference.get(name)]
                if len(narrowings) > 1:
                    raise ValidationError(f"{label} may set at most one of table, view, or macro")
                if narrowings and not reference.get("schema"):
                    raise ValidationError(f"{label}.{narrowings[0]} requires schema")
                if reference.get("column") and not reference.get("table"):
                    raise ValidationError(f"{label}.column requires table")
                continue
            if reference_type not in {"dive", "flight", "guide"}:
                raise ValidationError(f"{label}.type is invalid")
            selectors = [name for name in ("uuid", "resource") if reference.get(name)]
            if len(selectors) != 1:
                raise ValidationError(f"{label} must set exactly one of uuid or resource")

    def _validate_guide_reference_cycles(self, blueprint: RenderedBlueprint) -> None:
        dependencies: dict[str, set[str]] = {key: set() for key in blueprint.guides}
        for key, guide in blueprint.guides.items():
            references = guide.get("references", [])
            if not isinstance(references, list):
                continue
            for reference in references:
                if (
                    isinstance(reference, dict)
                    and reference.get("type") == "guide"
                    and reference.get("resource")
                    and str(reference.get("blueprint", blueprint.name)) == blueprint.name
                ):
                    dependencies[key].add(str(reference["resource"]))

        remaining = {key: set(values) for key, values in dependencies.items()}
        while remaining:
            ready = [key for key, values in remaining.items() if not values]
            if not ready:
                cycle = ", ".join(sorted(remaining))
                raise ValidationError(f"Guide reference cycle in blueprint {blueprint.name}: {cycle}")
            for key in ready:
                remaining.pop(key)
            for values in remaining.values():
                values.difference_update(ready)

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


def includes_branch_scope(value: str, branch: str | None) -> bool:
    if not branch:
        return False
    return branch in value or branch_slug(branch) in value


def require_nonempty(value: object, label: str) -> None:
    if str(value or "") == "":
        raise ValidationError(f"{label} is required")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise ValidationError(f"Required file not found: {path}")


def require_within(path: Path, root: Path, label: str) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValidationError(f"{label} must stay within {resolved_root}: {path}") from exc
    return resolved_path


def validate_python(path: Path) -> None:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ValidationError(f"Python syntax error in {path}: {exc}") from exc
