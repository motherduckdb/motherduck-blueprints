from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .project import CommandError, Project, RenderedBlueprint, branch_slug
from .schema import ValidationError

DuckDBConfigValue = str | bool | int | float | list[str]


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


def quote_name(value: object) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def format_sql_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def format_sql_rows(rows: list[tuple[object, ...]]) -> str:
    lines: list[str] = []
    for row in rows:
        if len(row) == 1:
            lines.append(format_sql_value(row[0]))
        else:
            lines.append(",".join(format_sql_value(value) for value in row))
    return "\n".join(lines)


def normalize_guide_references(value: object) -> object:
    try:
        parsed: object = json.loads(str(value))
    except json.JSONDecodeError:
        return str(value)
    if not isinstance(parsed, list):
        return parsed

    normalized: list[dict[str, object]] = []
    for raw_reference in parsed:
        if not isinstance(raw_reference, dict):
            return parsed
        reference_type = str(raw_reference.get("type", ""))
        uuid_value = raw_reference.get("uuid")
        if uuid_value is None:
            uuid_value = raw_reference.get(f"{reference_type}_id")
        normalized.append(
            {
                "type": reference_type,
                "url": raw_reference.get("url"),
                "schema": raw_reference.get("schema"),
                "table": raw_reference.get("table"),
                "column": raw_reference.get("column"),
                "view": raw_reference.get("view"),
                "macro": raw_reference.get("macro"),
                "uuid": uuid_value,
                "description": raw_reference.get("description"),
            }
        )
    return normalized


def guide_references_equal(left: object, right: object) -> bool:
    return bool(normalize_guide_references(left) == normalize_guide_references(right))


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
    current_status: str | None = None
    desired_status: str | None = None

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
            "current_status": self.current_status,
            "desired_status": self.desired_status,
        }

    def formatted_status(self) -> str:
        if self.type != "dive":
            return ""
        if self.desired_status is None:
            if self.current_status:
                return f"preserve {self.current_status}"
            return "draft (default)" if self.action == "create" else "unmanaged"
        if self.current_status is None:
            return self.desired_status
        if self.current_status == self.desired_status:
            return self.desired_status
        return f"{self.current_status} -> {self.desired_status}"


class PlanFormatter:
    @staticmethod
    def format(records: list[PlanRecord], *, title: str) -> str:
        if not records:
            return f"#### {title}\n\nNo resources selected."

        lines = [
            f"#### {title}",
            "",
            "| Blueprint | Type | Key | Name | Action | Exists | ID | Status | Notes |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
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
                record.formatted_status(),
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

class Deployer:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.sql_env: dict[str, DuckDBConfigValue] | None = None
        self.rendered_by_name: dict[str, RenderedBlueprint] = {}

    def plan(self, *, target: str, branch: str | None, names: list[str] | None) -> list[PlanRecord]:
        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "plan")
        self._preflight_rbac(rendered)
        return self._build_deploy_plan(rendered)

    def deploy(self, *, target: str, branch: str | None, names: list[str] | None) -> None:
        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "deploy")
        self._preflight_rbac(rendered)
        records = self._build_deploy_plan(rendered)
        self.ensure_plan_succeeds(records)
        plan_index = self._index_by_resource(records)

        for blueprint, key, role in self._role_deployment_order(rendered):
            self._deploy_role(role, plan_index[(blueprint.name, "role", key)])

        for blueprint in rendered:
            self._deploy_blueprint(blueprint, target, plan_index)

    def cleanup_plan(self, *, target: str, branch: str | None, names: list[str] | None) -> list[PlanRecord]:
        if target != "preview":
            raise ValidationError("cleanup is only supported for preview target")
        policies = self.project.target_config(target).get("policies", {})
        if not isinstance(policies, dict) or policies.get("cleanup") is not True:
            raise ValidationError("cleanup is disabled by the preview target policy")

        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "cleanup")
        rendered_names = [blueprint.name for blueprint in rendered]
        production = {
            blueprint.name: blueprint
            for blueprint in self.project.render_all("prod", names=rendered_names)
        }
        return self._build_cleanup_plan(
            rendered,
            branch_slug(branch or ""),
            branch=branch,
            production=production,
        )

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
        self.project.validate(targets=[target], branch=branch)
        expanded_names = self.project.deployment_blueprint_names(target, names)
        self.rendered_by_name = {
            blueprint.name: blueprint
            for blueprint in self.project.render_all(target, branch=branch)
        }
        return self.project.render_all(target, branch=branch, names=expanded_names)

    def _prepare_live_command(self, target: str, operation: str) -> None:
        deployment = self.project.target_config(target).get("deployment", {})
        token_env_var = "MOTHERDUCK_TOKEN"
        if isinstance(deployment, dict):
            token_env_var = str(deployment.get("tokenEnvVar", token_env_var))
        token = os.environ.get(token_env_var, "")
        if not token:
            raise ValidationError(f"{token_env_var} is required to {operation} target {target}")
        self.sql_env = {"motherduck_token": token}

    def _build_deploy_plan(self, rendered: list[RenderedBlueprint]) -> list[PlanRecord]:
        self.rendered_by_name.update({blueprint.name: blueprint for blueprint in rendered})
        records: list[PlanRecord] = []
        selected_names = {blueprint.name for blueprint in rendered}
        managed_role_names = {
            str(role["name"])
            for blueprint in rendered
            for role in blueprint.roles.values()
            if role.get("deploy")
        }
        needs_role_catalog = bool(managed_role_names) or any(
            isinstance(grants := share.get("grants"), dict) and bool(grants.get("roles"))
            for blueprint in rendered
            for share in blueprint.shares.values()
        )
        live_role_names = self._live_role_names() if needs_role_catalog else set()
        can_produce = {
            blueprint.name: any(flight.get("runOnDeploy") is True for flight in blueprint.flights.values())
            for blueprint in rendered
        }
        for blueprint in rendered:
            for key, role in blueprint.roles.items():
                name = str(role["name"])
                if not role.get("deploy"):
                    records.append(
                        PlanRecord(
                            blueprint.name,
                            "role",
                            key,
                            name,
                            "skipped",
                            None,
                            None,
                            "roles deploy only when resources.roles.<key>.deploy is true",
                        )
                    )
                    continue
                raw_included_roles = role.get("includedRoles", [])
                included_roles = (
                    {str(value) for value in raw_included_roles}
                    if isinstance(raw_included_roles, list)
                    else set()
                )
                missing_roles = sorted(included_roles - live_role_names - managed_role_names)
                exists = name in live_role_names
                records.append(
                    PlanRecord(
                        blueprint.name,
                        "role",
                        key,
                        name,
                        "error" if missing_roles else ("update" if exists else "create"),
                        exists,
                        name if exists else None,
                        (
                            "included role(s) do not exist and are not selected for deployment: "
                            f"{', '.join(missing_roles)}"
                            if missing_roles
                            else ""
                        ),
                    )
                )

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
                grants = share.get("grants")
                desired_grant_roles = (
                    {str(value) for value in grants.get("roles", [])}
                    if isinstance(grants, dict)
                    else set()
                )
                missing_grant_roles = sorted(
                    desired_grant_roles - live_role_names - managed_role_names
                )
                manages_share = "includePattern" in share or isinstance(grants, dict)
                if missing_grant_roles:
                    action = "error"
                    notes = (
                        "grant role(s) do not exist and are not selected for deployment: "
                        f"{', '.join(missing_grant_roles)}"
                    )
                elif url and manages_share:
                    action = "update"
                    notes = "share is available; filter and/or grants will be reconciled"
                elif url:
                    action = "present"
                    notes = "share is available"
                elif can_produce[blueprint.name]:
                    action = "pending"
                    notes = "will be produced by a Flight configured with runOnDeploy"
                else:
                    action = "error"
                    notes = "share is missing and no Flight in this blueprint is configured with runOnDeploy"
                records.append(
                    PlanRecord(
                        blueprint=blueprint.name,
                        type="share",
                        key=key,
                        name=str(share["name"]),
                        action=action,
                        exists=bool(url),
                        id=url or None,
                        notes=notes,
                    )
                )

            for key, input_value in blueprint.inputs.items():
                share_name = str(input_value["name"])
                producer = str(input_value["blueprint"])
                output = str(input_value["output"])
                url = self._find_share_url(share_name)
                producer_selected = producer in selected_names
                if url:
                    action = "present"
                    notes = f"resolved from {producer}.{output}"
                elif producer_selected and can_produce.get(producer, False):
                    action = "pending"
                    notes = f"will be produced by selected blueprint {producer}.{output}"
                elif producer_selected:
                    action = "error"
                    notes = (
                        f"selected blueprint {producer}.{output} is missing and has no Flight configured "
                        "with runOnDeploy"
                    )
                else:
                    action = "error"
                    notes = f"required production output {producer}.{output} is not available"
                records.append(
                    PlanRecord(
                        blueprint=blueprint.name,
                        type="input",
                        key=key,
                        name=share_name,
                        action=action,
                        exists=bool(url),
                        id=url or None,
                        notes=notes,
                    )
                )

            for key, dive in blueprint.dives.items():
                records.append(self._dive_plan_record(blueprint, key, dive))

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
            for key, guide in blueprint.guides.items():
                reference_error = self._guide_reference_plan_error(
                    blueprint,
                    guide,
                    selected_names,
                )
                if reference_error:
                    records.append(
                        PlanRecord(
                            blueprint.name,
                            "guide",
                            key,
                            str(guide.get("title") or Path(str(guide["sourcePath"])).name),
                            "error",
                            None,
                            str(guide.get("id")) if guide.get("id") else None,
                            reference_error,
                        )
                    )
                else:
                    records.append(self._guide_plan_record(blueprint, key, guide))
        return records

    def _build_cleanup_plan(
        self,
        rendered: list[RenderedBlueprint],
        rendered_branch_slug: str,
        *,
        branch: str | None = None,
        production: dict[str, RenderedBlueprint] | None = None,
    ) -> list[PlanRecord]:
        records: list[PlanRecord] = []
        dependency_safe = list(reversed(rendered))
        for blueprint in dependency_safe:
            production_blueprint = production.get(blueprint.name) if production else None
            for key in reversed(self._guide_deployment_order(blueprint)):
                guide = blueprint.guides[key]
                if not guide.get("deploy") or not guide.get("cleanup", True):
                    continue
                title = str(guide["title"])
                production_title = None
                if production_blueprint and key in production_blueprint.guides:
                    raw_production_title = production_blueprint.guides[key].get("title")
                    if raw_production_title is not None:
                        production_title = str(raw_production_title)
                safety_error = self._preview_scope_error(
                    "Guide", title, branch, rendered_branch_slug, production_title
                )
                if safety_error:
                    records.append(
                        self._cleanup_record(blueprint, "guide", key, title, "error", None, None, safety_error)
                    )
                    continue
                topic = str(guide.get("topic", ""))
                ids = self._list_guide_ids(title, topic)
                if not ids:
                    records.append(self._cleanup_record(blueprint, "guide", key, title, "missing", False, None))
                else:
                    for resource_id in ids:
                        records.append(
                            self._cleanup_record(blueprint, "guide", key, title, "delete", True, resource_id)
                        )

        for blueprint in dependency_safe:
            production_blueprint = production.get(blueprint.name) if production else None
            for key, dive in blueprint.dives.items():
                title = str(dive["title"])
                production_title = None
                if production_blueprint and key in production_blueprint.dives:
                    production_title = str(production_blueprint.dives[key]["title"])
                safety_error = self._preview_scope_error(
                    "Dive", title, branch, rendered_branch_slug, production_title
                )
                if safety_error:
                    records.append(
                        self._cleanup_record(blueprint, "dive", key, title, "error", None, None, safety_error)
                    )
                    continue
                ids = self._list_dive_ids(title)
                if not ids:
                    records.append(self._cleanup_record(blueprint, "dive", key, title, "missing", False, None))
                else:
                    for resource_id in ids:
                        records.append(self._cleanup_record(blueprint, "dive", key, title, "delete", True, resource_id))

        for blueprint in dependency_safe:
            production_blueprint = production.get(blueprint.name) if production else None
            for key, flight in blueprint.flights.items():
                name = str(flight["name"])
                production_name = None
                if production_blueprint and key in production_blueprint.flights:
                    production_name = str(production_blueprint.flights[key]["name"])
                safety_error = self._preview_scope_error(
                    "Flight", name, branch, rendered_branch_slug, production_name
                )
                if safety_error:
                    records.append(
                        self._cleanup_record(blueprint, "flight", key, name, "error", None, None, safety_error)
                    )
                    continue
                ids = self._list_flight_ids(name)
                if not ids:
                    records.append(self._cleanup_record(blueprint, "flight", key, name, "missing", False, None))
                else:
                    for resource_id in ids:
                        records.append(self._cleanup_record(blueprint, "flight", key, name, "delete", True, resource_id))

        for blueprint in dependency_safe:
            production_blueprint = production.get(blueprint.name) if production else None
            for key, share in blueprint.shares.items():
                if not share.get("cleanup", True):
                    continue

                share_name = str(share["name"])
                database_name = str(share["database"])
                production_share = production_blueprint.shares.get(key) if production_blueprint else None
                production_share_name = str(production_share["name"]) if production_share else None
                share_safety_error = self._preview_scope_error(
                    "share", share_name, branch, rendered_branch_slug, production_share_name
                )
                if share_safety_error:
                    records.append(
                        self._cleanup_record(
                            blueprint,
                            "share",
                            key,
                            share_name,
                            "error",
                            None,
                            None,
                            share_safety_error,
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

                production_database_name = str(production_share["database"]) if production_share else None
                database_safety_error = self._preview_scope_error(
                    "database", database_name, branch, rendered_branch_slug, production_database_name
                )
                if database_safety_error:
                    records.append(
                        self._cleanup_record(
                            blueprint,
                            "database",
                            key,
                            database_name,
                            "error",
                            None,
                            None,
                            database_safety_error,
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

    @staticmethod
    def _preview_scope_error(
        resource_type: str,
        name: str,
        branch: str | None,
        rendered_branch_slug: str,
        production_name: str | None,
    ) -> str | None:
        if production_name is not None and name == production_name:
            return f"refusing to delete preview {resource_type} because it matches production: {name}"
        branch_markers = {rendered_branch_slug}
        if branch:
            branch_markers.add(branch)
        if not any(marker and marker in name for marker in branch_markers):
            action = "drop" if resource_type in {"share", "database"} else "delete"
            return f"refusing to {action} preview {resource_type} without branch slug {rendered_branch_slug}"
        return None

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

    def _dive_plan_record(
        self,
        blueprint: RenderedBlueprint,
        key: str,
        dive: dict[str, object],
    ) -> PlanRecord:
        title = str(dive["title"])
        desired_status_value = dive.get("status")
        desired_status = str(desired_status_value) if desired_status_value is not None else None
        states = self._list_dive_states(title)
        if not states:
            notes = "endorsing requires an organization admin" if desired_status == "endorsed" else ""
            return PlanRecord(
                blueprint.name,
                "dive",
                key,
                title,
                "create",
                False,
                None,
                notes,
                desired_status=desired_status,
            )
        if len(states) == 1:
            dive_id, current_status = states[0]
            notes = ""
            if current_status == "endorsed" and desired_status not in {None, "endorsed"}:
                notes = "moving off endorsed may be one-way unless the deployer is an organization admin"
            elif desired_status == "endorsed" and current_status != "endorsed":
                notes = "endorsing requires an organization admin"
            elif current_status == "endorsed":
                notes = "content update remains endorsed"
            return PlanRecord(
                blueprint.name,
                "dive",
                key,
                title,
                "update",
                True,
                dive_id,
                notes,
                current_status=current_status,
                desired_status=desired_status,
            )
        return PlanRecord(
            blueprint.name,
            "dive",
            key,
            title,
            "error",
            True,
            ",".join(state[0] for state in states),
            "duplicate Dive title; expected 0 or 1",
            desired_status=desired_status,
        )

    def _guide_plan_record(
        self,
        blueprint: RenderedBlueprint,
        key: str,
        guide: dict[str, object],
    ) -> PlanRecord:
        if not guide.get("deploy"):
            name = str(guide.get("title") or Path(str(guide["sourcePath"])).name)
            return PlanRecord(
                blueprint.name,
                "guide",
                key,
                name,
                "validated_only",
                False,
                None,
                "set deploy: true to publish this Guide",
            )

        title = str(guide["title"])
        guide_id = guide.get("id")
        if guide_id:
            try:
                rows = self._query_rows(
                    f"SELECT id FROM MD_GET_GUIDE(id := {sql_string(guide_id)}::UUID)"
                )
            except CommandError as exc:
                if "does not exist" not in str(exc).lower() and "not found" not in str(exc).lower():
                    raise
                rows = []
        else:
            topic = str(guide.get("topic", ""))
            topic_predicate = (
                "topic IS NULL OR topic = ''"
                if not topic
                else f"topic = {sql_string(topic)}"
            )
            rows = self._query_rows(
                "SELECT id FROM MD_LIST_GUIDES("
                '"limit" := 1000::UINTEGER, "offset" := 0::UINTEGER) '
                f"WHERE title = {sql_string(title)} AND ({topic_predicate})"
            )
        ids = [str(row[0]) for row in rows]
        if not ids:
            if guide_id:
                return PlanRecord(
                    blueprint.name,
                    "guide",
                    key,
                    title,
                    "error",
                    False,
                    str(guide_id),
                    "configured Guide id does not exist",
                )
            return PlanRecord(blueprint.name, "guide", key, title, "create", False, None)
        if len(ids) == 1:
            return PlanRecord(blueprint.name, "guide", key, title, "update", True, ids[0])
        return PlanRecord(
            blueprint.name,
            "guide",
            key,
            title,
            "error",
            True,
            ",".join(ids),
            "duplicate Guide topic/title; set id explicitly",
        )

    def _guide_reference_plan_error(
        self,
        blueprint: RenderedBlueprint,
        guide: dict[str, object],
        selected_names: set[str],
    ) -> str | None:
        if not guide.get("deploy"):
            return None
        references = guide.get("references", [])
        if not isinstance(references, list):
            return "Guide references must be an array"

        for reference in references:
            if not isinstance(reference, dict) or reference.get("type") == "catalog":
                continue
            reference_type = str(reference["type"])
            if reference.get("uuid"):
                uuid_value = str(reference["uuid"])
                ids = self._resource_ids_by_uuid(reference_type, uuid_value)
                if len(ids) != 1:
                    return (
                        f"Guide {reference_type} reference {uuid_value} does not resolve "
                        "to exactly one live resource"
                    )
                continue

            producer_name = str(reference.get("blueprint", blueprint.name))
            producer = self.rendered_by_name.get(producer_name)
            if producer is None:
                return f"Guide reference blueprint {producer_name!r} is not available"
            resource_key = str(reference["resource"])
            selected_resource_will_deploy = producer_name in selected_names
            if reference_type == "guide":
                referenced_guide = producer.guides[resource_key]
                selected_resource_will_deploy = (
                    selected_resource_will_deploy and bool(referenced_guide.get("deploy"))
                )
            if selected_resource_will_deploy:
                continue

            ids = self._resource_ids_for_reference(reference_type, producer, resource_key)
            if len(ids) != 1:
                return (
                    f"Guide reference {producer_name}.{reference_type}.{resource_key} "
                    f"resolved to {len(ids)} live resources; expected exactly one"
                )
        return None

    def _resource_ids_by_uuid(self, reference_type: str, uuid_value: str) -> list[str]:
        uuid_sql = f"{sql_string(uuid_value)}::UUID"
        if reference_type == "dive":
            rows = self._query_rows(f"SELECT id FROM MD_LIST_DIVES() WHERE id = {uuid_sql}")
        elif reference_type == "flight":
            rows = self._query_rows(
                "SELECT flight_id FROM MD_LIST_FLIGHTS("
                '"offset" => 0::UINTEGER, "limit" => 1000::UINTEGER) '
                f"WHERE flight_id = {uuid_sql}"
            )
        else:
            rows = self._get_guide_rows_by_id(uuid_value)
        return [str(row[0]) for row in rows]

    def _resource_ids_for_reference(
        self,
        reference_type: str,
        producer: RenderedBlueprint,
        resource_key: str,
    ) -> list[str]:
        if reference_type == "dive":
            return [
                state[0]
                for state in self._list_dive_states(str(producer.dives[resource_key]["title"]))
            ]
        if reference_type == "flight":
            return self._list_flight_ids(str(producer.flights[resource_key]["name"]))

        referenced_guide = producer.guides[resource_key]
        if referenced_guide.get("id"):
            return [
                str(row[0])
                for row in self._get_guide_rows_by_id(str(referenced_guide["id"]))
            ]
        return self._list_guide_ids(
            str(referenced_guide["title"]),
            str(referenced_guide.get("topic", "")),
        )

    def _get_guide_rows_by_id(self, guide_id: str) -> list[tuple[object, ...]]:
        try:
            return self._query_rows(
                f"SELECT id FROM MD_GET_GUIDE(id := {sql_string(guide_id)}::UUID)"
            )
        except CommandError as exc:
            message = str(exc).lower()
            if "does not exist" in message or "not found" in message:
                return []
            raise

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
        guide_rows: list[str] = []

        for key, flight in blueprint.flights.items():
            print(f"Deploying Flight {blueprint.name}.{key}...", file=sys.stderr)
            row = self._deploy_flight(flight, target, plan_index[(blueprint.name, "flight", key)])
            if row:
                flight_rows.append(row)

        for share in blueprint.shares.values():
            url = self._wait_for_share(str(share["name"]))
            self._reconcile_share(share)
            if target == "preview":
                share_rows.append(f"| {share['name']} | [Open Share]({url}) |")

        for key, dive in blueprint.dives.items():
            print(f"Deploying Dive {blueprint.name}.{key}...", file=sys.stderr)
            row = self._deploy_dive(
                dive,
                blueprint.shares,
                blueprint.inputs,
                target,
                plan_index[(blueprint.name, "dive", key)],
            )
            if row:
                dive_rows.append(row)

        for key in self._guide_deployment_order(blueprint):
            guide = blueprint.guides[key]
            if not guide.get("deploy"):
                continue
            print(f"Deploying Guide {blueprint.name}.{key}...", file=sys.stderr)
            row = self._deploy_guide(
                blueprint,
                guide,
                target,
                plan_index[(blueprint.name, "guide", key)],
            )
            if row:
                guide_rows.append(row)

        if target != "preview":
            return

        print(f"#### {blueprint.title}")
        print()
        self._print_section("Flights", "| Flight | ID | Run started |", "|--------|----|-------------|", flight_rows)
        self._print_section("Shares", "| Share | Link |", "|-------|------|", share_rows)
        self._print_section("Dives", "| Dive | Status | Link |", "|------|--------|------|", dive_rows)
        self._print_section("Guides", "| Guide | ID |", "|-------|----|", guide_rows)

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
        raw_config = flight.get("config", {})
        config = {str(key): value for key, value in raw_config.items()} if isinstance(raw_config, dict) else {}
        raw_secrets = flight.get("secrets", [])
        secrets = list(raw_secrets) if isinstance(raw_secrets, list) else []
        config_sql = sql_map(config)
        source_sql = f"(SELECT content FROM read_text({sql_string(flight['sourcePath'])}))"
        requirements_sql = f"(SELECT content FROM read_text({sql_string(flight['requirementsPath'])}))"
        schedule_cron = str(flight.get("scheduleCron", ""))
        schedule_arg = f'"schedule_cron" => {sql_string(schedule_cron)}'
        common_args = [
            schedule_arg,
            f'"flight_secret_names" => {sql_array(secrets)}',
            f'"config" => {config_sql}',
            f'"name" => {name_sql}',
            '"source_code" => getvariable(\'source_code\')',
            '"requirements_txt" => getvariable(\'requirements_txt\')',
        ]
        access_token_name = str(flight.get("accessTokenName", ""))
        if access_token_name:
            common_args.insert(3, f'"access_token_name" => {sql_string(access_token_name)}')
        if "maxRuntimeSec" in flight:
            common_args.insert(3, f'"max_runtime_sec" => {int(str(flight["maxRuntimeSec"]))}::UINTEGER')
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
            try:
                self._sql(
                    f"SET VARIABLE source_code = {source_sql}; "
                    f"SET VARIABLE requirements_txt = {requirements_sql}; "
                    f"FROM MD_UPDATE_FLIGHT(\"flight_id\" => '{plan.id}'::UUID, {common_args_sql});"
                )
            except CommandError as exc:
                if schedule_cron or "Cannot clear schedule: Flight has no schedule" not in str(exc):
                    raise
                args_without_schedule_sql = ", ".join(arg for arg in common_args if arg != schedule_arg)
                self._sql(
                    f"SET VARIABLE source_code = {source_sql}; "
                    f"SET VARIABLE requirements_txt = {requirements_sql}; "
                    f"FROM MD_UPDATE_FLIGHT(\"flight_id\" => '{plan.id}'::UUID, {args_without_schedule_sql});"
                )
            flight_id = str(plan.id)
        else:
            raise ValidationError(f"Cannot deploy Flight {name} with plan action {plan.action}")

        run_started = False
        if flight.get("runOnDeploy", False):
            print(f"  Starting flight run for '{name}'...", file=sys.stderr)
            self._sql(f"FROM MD_RUN_FLIGHT(\"config\" => {config_sql}, \"flight_id\" => '{flight_id}'::UUID);")
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
        inputs: dict[str, dict[str, object]],
        target: str,
        plan: PlanRecord,
    ) -> str | None:
        title = str(dive["title"])
        required_resources_sql = self._required_resources_sql(dive["requiredResources"], shares, inputs)
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

        desired_status_value = dive.get("status")
        desired_status = str(desired_status_value) if desired_status_value is not None else None
        if (
            desired_status is not None
            and desired_status != plan.current_status
            and not (plan.action == "create" and desired_status == "draft")
        ):
            print(f"  Setting Dive status to {desired_status}...", file=sys.stderr)
            self._sql(
                f"FROM MD_UPDATE_DIVE_STATUS(id = '{dive_id}'::UUID, status = {sql_string(desired_status)});"
            )

        print(f"  Deployed: https://app.motherduck.com/dives/{dive_id}", file=sys.stderr)
        effective_status = desired_status or plan.current_status or "draft"
        return (
            f"| {title} | {effective_status} | [Open Dive](https://app.motherduck.com/dives/{dive_id}) |"
            if target == "preview"
            else None
        )

    def _required_resources_sql(
        self,
        resources_value: object,
        shares: dict[str, dict[str, object]],
        inputs: dict[str, dict[str, object]] | None = None,
    ) -> str:
        if not isinstance(resources_value, list):
            raise ValidationError("requiredResources must be a list")

        expressions = []
        for resource in resources_value:
            if not isinstance(resource, dict):
                raise ValidationError("requiredResources entries must be objects")
            if resource.get("share"):
                url = self._wait_for_share(str(shares[str(resource["share"])]["name"]))
            elif resource.get("input"):
                input_values = inputs or {}
                url = self._wait_for_share(str(input_values[str(resource["input"])]["name"]))
            else:
                url = str(resource["url"])
            expressions.append(f"{{'url': {sql_string(url)}, 'alias': {sql_string(resource['alias'])}}}")
        return f"[{', '.join(expressions)}]"

    def _preflight_rbac(self, rendered: list[RenderedBlueprint]) -> None:
        admin_reasons: list[str] = []
        for blueprint in rendered:
            if any(role.get("deploy") for role in blueprint.roles.values()):
                admin_reasons.append(f"{blueprint.name} manages roles")
            if any(
                guide.get("deploy") and guide.get("access") == "organization"
                for guide in blueprint.guides.values()
            ):
                admin_reasons.append(f"{blueprint.name} publishes organization Guides")
        if not admin_reasons:
            return

        rows = self._query_rows("SELECT role_name FROM md_list_roles_for_user(current_user)")
        roles = {str(row[0]).lower() for row in rows}
        if "admin" not in roles:
            reasons = "; ".join(admin_reasons)
            raise ValidationError(
                f"RBAC preflight failed: target requires the admin role ({reasons}); "
                f"the deployment identity has: {', '.join(sorted(roles)) or 'no roles'}"
            )

    def _live_role_names(self) -> set[str]:
        return {
            str(row[0])
            for row in self._query_rows("SELECT role_name FROM md_list_roles()")
        }

    def _deploy_role(self, role: dict[str, object], plan: PlanRecord) -> None:
        name = str(role["name"])
        name_sql = quote_name(name)
        print(f"Reconciling role '{name}'...", file=sys.stderr)
        self._sql(f"CREATE ROLE IF NOT EXISTS {name_sql};")

        included_roles = role.get("includedRoles", [])
        members = role.get("members", [])
        if not isinstance(included_roles, list) or not isinstance(members, list):
            raise ValidationError("Role includedRoles and members must be arrays")
        desired_roles = {str(value) for value in included_roles}
        desired_users = {str(value) for value in members}
        current_roles: set[str] = set()
        current_users: set[str] = set()
        if role.get("mode") == "authoritative" or plan.action == "update":
            current_roles = {
                str(row[0])
                for row in self._query_rows(f"SHOW ROLES TO ROLE {name_sql}")
                if len(row) >= 3 and bool(row[2])
            }
            current_users = {
                str(row[0])
                for row in self._query_rows(f"SHOW USERS OF ROLE {name_sql}")
            }

        for included in sorted(desired_roles - current_roles):
            self._sql(f"GRANT ROLE {quote_name(included)} TO ROLE {name_sql};")
        for member in sorted(desired_users - current_users):
            self._sql(f"GRANT ROLE {name_sql} TO USER {quote_name(member)};")
        if role.get("mode") == "authoritative":
            for included in sorted(current_roles - desired_roles):
                self._sql(f"REVOKE ROLE {quote_name(included)} FROM ROLE {name_sql};")
            for member in sorted(current_users - desired_users):
                self._sql(f"REVOKE ROLE {name_sql} FROM USER {quote_name(member)};")

    def _role_deployment_order(
        self,
        rendered: list[RenderedBlueprint],
    ) -> list[tuple[RenderedBlueprint, str, dict[str, object]]]:
        resources = {
            str(role["name"]): (blueprint, key, role)
            for blueprint in rendered
            for key, role in blueprint.roles.items()
            if role.get("deploy")
        }
        dependencies: dict[str, set[str]] = {name: set() for name in resources}
        for name, (_, _, role) in resources.items():
            included = role.get("includedRoles", [])
            if isinstance(included, list):
                dependencies[name] = {str(value) for value in included if str(value) in resources}

        ordered: list[tuple[RenderedBlueprint, str, dict[str, object]]] = []
        remaining = {name: set(values) for name, values in dependencies.items()}
        while remaining:
            ready = sorted(name for name, values in remaining.items() if not values)
            if not ready:
                raise ValidationError(f"Role dependency cycle: {', '.join(sorted(remaining))}")
            for name in ready:
                ordered.append(resources[name])
                remaining.pop(name)
            for values in remaining.values():
                values.difference_update(ready)
        return ordered

    def _reconcile_share(self, share: dict[str, object]) -> None:
        name = str(share["name"])
        if "includePattern" in share:
            include_pattern = share["includePattern"]
            if include_pattern is None:
                self._sql(f"ALTER SHARE {quote_name(name)} RESET INCLUDE_PATTERN;")
            else:
                assert isinstance(include_pattern, list)
                pattern = ", ".join(str(value) for value in include_pattern)
                self._sql(
                    f"ALTER SHARE {quote_name(name)} SET INCLUDE_PATTERN {sql_string(pattern)};"
                )

        grants = share.get("grants")
        if not isinstance(grants, dict):
            return
        desired_roles = {str(value) for value in grants.get("roles", [])}
        desired_users = {str(value) for value in grants.get("users", [])}
        current_rows = self._query_rows(
            "SELECT grantee_name, grantee_type "
            f"FROM md_list_share_grantees({sql_string(name)})"
        )
        current_roles = {str(row[0]) for row in current_rows if str(row[1]).lower() == "role"}
        current_users = {str(row[0]) for row in current_rows if str(row[1]).lower() == "user"}

        for role in sorted(desired_roles - current_roles):
            self._sql(f"GRANT READ ON SHARE {quote_name(name)} TO ROLE {quote_name(role)};")
        for user in sorted(desired_users - current_users):
            self._sql(f"GRANT READ ON SHARE {quote_name(name)} TO USER {quote_name(user)};")
        if grants.get("mode") == "authoritative":
            for role in sorted(current_roles - desired_roles):
                self._sql(f"REVOKE READ ON SHARE {quote_name(name)} FROM ROLE {quote_name(role)};")
            for user in sorted(current_users - desired_users):
                self._sql(f"REVOKE READ ON SHARE {quote_name(name)} FROM USER {quote_name(user)};")

    def _guide_deployment_order(self, blueprint: RenderedBlueprint) -> list[str]:
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

        ordered: list[str] = []
        remaining = {key: set(values) for key, values in dependencies.items()}
        while remaining:
            ready = sorted(key for key, values in remaining.items() if not values)
            if not ready:
                cycle = ", ".join(sorted(remaining))
                raise ValidationError(f"Guide reference cycle in blueprint {blueprint.name}: {cycle}")
            for key in ready:
                ordered.append(key)
                remaining.pop(key)
            for values in remaining.values():
                values.difference_update(ready)
        return ordered

    def _deploy_guide(
        self,
        blueprint: RenderedBlueprint,
        guide: dict[str, object],
        target: str,
        plan: PlanRecord,
    ) -> str | None:
        title = str(guide["title"])
        content_sql = f"(SELECT content FROM read_text({sql_string(guide['sourcePath'])}))"
        references_sql = self._guide_references_sql(blueprint, guide.get("references", []))
        change_comment = str(guide.get("changeComment", "deployed by md-blueprints"))
        external_id = str(guide.get("externalId") or os.environ.get("GITHUB_SHA", ""))
        version_args = [
            '"content" := getvariable(\'guide_content\')',
            f'"change_comment" := {sql_string(change_comment)}',
            f'"references" := {references_sql}',
        ]
        if external_id:
            version_args.append(f'"external_id" := {sql_string(external_id)}')

        if plan.action == "create":
            create_args = [
                f'"title" := {sql_string(title)}',
                *version_args,
                f'"description" := {sql_string(guide.get("description", ""))}',
                f'"access" := {sql_string(guide.get("access", "user"))}',
            ]
            topic = str(guide.get("topic", ""))
            if topic:
                create_args.append(f'"topic" := {sql_string(topic)}')
            guide_id = self._sql(
                f"SET VARIABLE guide_content = {content_sql}; "
                f"SELECT id FROM MD_CREATE_GUIDE({', '.join(create_args)});"
            ).strip()
        elif plan.action == "update":
            guide_id = str(plan.id)
            existing = self._query_rows(
                f"SET VARIABLE desired_guide_references = {references_sql}; "
                "SELECT content, version_external_id, "
                'to_json("references")::VARCHAR, '
                "to_json(getvariable('desired_guide_references'))::VARCHAR, "
                "title, topic, description, access "
                f"FROM MD_GET_GUIDE(id := '{guide_id}'::UUID)"
            )
            current_content = str(existing[0][0]) if existing else ""
            current_external_id = (
                str(existing[0][1]) if existing and existing[0][1] is not None else ""
            )
            references_match = bool(
                existing
                and len(existing[0]) >= 4
                and guide_references_equal(existing[0][2], existing[0][3])
            )
            source_content = Path(str(guide["sourcePath"])).read_text(encoding="utf-8")
            append_version = not (
                current_content == source_content
                and (not external_id or current_external_id == external_id)
                and references_match
            )
            statements = [f"SET VARIABLE guide_content = {content_sql};"]
            if append_version:
                statements.append(
                    f"FROM MD_UPDATE_GUIDE(\"id\" := '{guide_id}'::UUID, {', '.join(version_args)});"
                )

            desired_metadata = {
                "title": title,
                "description": str(guide.get("description", "")),
                "topic": str(guide.get("topic", "")),
            }
            current_metadata = {
                "title": str(existing[0][4]) if existing and existing[0][4] is not None else "",
                "topic": str(existing[0][5]) if existing and existing[0][5] is not None else "",
                "description": str(existing[0][6]) if existing and existing[0][6] is not None else "",
            }
            changed_metadata = [
                f'"{field}" := {sql_string(value)}'
                for field, value in desired_metadata.items()
                if current_metadata[field] != value
            ]
            if changed_metadata:
                statements.append(
                    "FROM MD_UPDATE_GUIDE_METADATA("
                    f"\"id\" := '{guide_id}'::UUID, {', '.join(changed_metadata)});"
                )

            desired_access = str(guide.get("access", "user"))
            current_access = (
                str(existing[0][7]) if existing and existing[0][7] is not None else ""
            )
            if current_access != desired_access:
                statements.append(
                    "FROM MD_SET_GUIDE_ACCESS("
                    f"\"id\" := '{guide_id}'::UUID, "
                    f"\"access\" := {sql_string(desired_access)});"
                )

            if len(statements) > 1:
                self._sql(" ".join(statements))
        else:
            raise ValidationError(f"Cannot deploy Guide {title} with plan action {plan.action}")

        return f"| {title} | {guide_id} |" if target == "preview" else None

    def _guide_references_sql(
        self,
        blueprint: RenderedBlueprint,
        references_value: object,
    ) -> str:
        if not isinstance(references_value, list):
            raise ValidationError("Guide references must be an array")
        rendered: list[str] = []
        for reference_value in references_value:
            if not isinstance(reference_value, dict):
                raise ValidationError("Guide references entries must be objects")
            reference = reference_value
            reference_type = str(reference["type"])
            url: str | None = None
            uuid_value: str | None = None
            if reference_type == "catalog":
                if reference.get("share"):
                    url = self._wait_for_share(str(blueprint.shares[str(reference["share"])]["name"]))
                elif reference.get("input"):
                    url = self._wait_for_share(str(blueprint.inputs[str(reference["input"])]["name"]))
                else:
                    url = str(reference["url"])
            elif reference.get("uuid"):
                uuid_value = str(reference["uuid"])
            else:
                producer_name = str(reference.get("blueprint", blueprint.name))
                producer = self.rendered_by_name.get(producer_name)
                if producer is None:
                    raise ValidationError(f"Guide reference blueprint {producer_name!r} was not selected")
                resource_key = str(reference["resource"])
                if reference_type == "dive":
                    states = self._list_dive_states(str(producer.dives[resource_key]["title"]))
                    ids = [state[0] for state in states]
                elif reference_type == "flight":
                    ids = self._list_flight_ids(str(producer.flights[resource_key]["name"]))
                else:
                    ids = self._resource_ids_for_reference(
                        reference_type,
                        producer,
                        resource_key,
                    )
                if len(ids) != 1:
                    raise CommandError(
                        f"Expected one {reference_type} for Guide reference "
                        f"{producer_name}.{resource_key}, found {len(ids)}"
                    )
                uuid_value = ids[0]

            def nullable_string(field: str, value: str | None = None) -> str:
                raw = value if value is not None else reference.get(field)
                return "NULL::VARCHAR" if raw in {None, ""} else sql_string(raw)

            uuid_sql = "NULL::UUID" if uuid_value is None else f"{sql_string(uuid_value)}::UUID"
            rendered.append(
                "{"
                f"'type': {sql_string(reference_type)}, "
                f"'url': {nullable_string('url', url)}, "
                f"'schema': {nullable_string('schema')}, "
                f"'table': {nullable_string('table')}, "
                f"'column': {nullable_string('column')}, "
                f"'view': {nullable_string('view')}, "
                f"'macro': {nullable_string('macro')}, "
                f"'uuid': {uuid_sql}, "
                f"'description': {nullable_string('description')}"
                "}"
            )
        return f"[{', '.join(rendered)}]"

    def _apply_cleanup_plan(self, records: list[PlanRecord]) -> None:
        for record in records:
            if (record.type, record.action) == ("guide", "missing"):
                print(f"No preview Guide found for '{record.name}'")
            elif (record.type, record.action) == ("guide", "delete"):
                print(f"Deleting preview Guide {record.id} ({record.name})")
                self._delete_if_present(
                    f"FROM MD_DELETE_GUIDE(id := '{record.id}'::UUID)",
                    f"preview Guide {record.name}",
                )
            elif (record.type, record.action) == ("dive", "missing"):
                print(f"No preview Dive found for '{record.name}'")
            elif (record.type, record.action) == ("dive", "delete"):
                print(f"Deleting preview Dive {record.id} ({record.name})")
                self._delete_if_present(f"FROM MD_DELETE_DIVE(id='{record.id}'::UUID)", f"preview Dive {record.name}")
            elif (record.type, record.action) == ("flight", "missing"):
                print(f"No preview Flight found for '{record.name}'")
            elif (record.type, record.action) == ("flight", "delete"):
                print(f"Deleting preview Flight {record.id} ({record.name})")
                self._delete_if_present(
                    f"FROM MD_DELETE_FLIGHT(\"flight_id\" => '{record.id}'::UUID);",
                    f"preview Flight {record.name}",
                )
            elif (record.type, record.action) == ("share", "missing"):
                print(f"No preview share found for '{record.name}'")
            elif (record.type, record.action) == ("share", "drop_share"):
                print(f"Dropping preview share {record.name}")
                self._delete_if_present(
                    f"FROM MD_DROP_DATABASE_SHARE({sql_string(record.name)});",
                    f"preview share {record.name}",
                )
            elif (record.type, record.action) == ("database", "drop_database"):
                print(f"Dropping preview database {record.name}")
                self._sql(f"DROP DATABASE IF EXISTS {quote_ident(record.name)};")

    def _delete_if_present(self, statement: str, label: str) -> None:
        try:
            self._sql(statement)
        except CommandError as exc:
            message = str(exc).lower()
            if "does not exist" not in message and "not found" not in message:
                raise
            print(f"Skipping {label}; it was already removed by another cleanup run")

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

    def _list_dive_states(self, title: str) -> list[tuple[str, str | None]]:
        return [
            (str(row[0]), str(row[1]).lower() if row[1] is not None else None)
            for row in self._query_rows(
                f"SELECT id, status FROM MD_LIST_DIVES() WHERE title = {sql_string(title)}"
            )
        ]

    def _list_guide_ids(self, title: str, topic: str) -> list[str]:
        topic_predicate = "topic IS NULL OR topic = ''" if not topic else f"topic = {sql_string(topic)}"
        return [
            str(row[0])
            for row in self._query_rows(
                "SELECT id FROM MD_LIST_GUIDES("
                '"limit" := 1000::UINTEGER, "offset" := 0::UINTEGER) '
                f"WHERE title = {sql_string(title)} AND ({topic_predicate})"
            )
        ]

    def _find_share_url(self, name: str) -> str:
        lines = self._sql(f"SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = {sql_string(name)}").splitlines()
        return lines[0].strip() if lines else ""

    def _sql(self, statement: str) -> str:
        return format_sql_rows(self._query_rows(statement)).strip()

    def _query_rows(self, statement: str) -> list[tuple[object, ...]]:
        if self.sql_env is None:
            raise ValidationError("MotherDuck token was not prepared for live command")
        try:
            import duckdb
        except ModuleNotFoundError as exc:
            raise CommandError(
                "duckdb Python package is required for live MotherDuck commands. "
                "Install md-blueprints[deploy] or run through the MotherDuck Blueprints action."
            ) from exc

        connection = None
        try:
            connection = duckdb.connect("md:", config=self.sql_env)
            result = connection.execute(statement)
            rows = result.fetchall()
        except duckdb.Error as exc:
            raise CommandError(f"MotherDuck SQL failed: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
        return rows
