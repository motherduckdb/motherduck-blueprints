from __future__ import annotations

import json
import copy
import importlib
import math
import os
import re
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

import json5

from .project import (
    CommandError,
    Project,
    RenderedBlueprint,
    branch_slug,
    contains_branch_marker,
    legacy_branch_slug,
)
from .schema import ValidationError
from .motherduck_cli import query_rows as cli_query_rows, sql_backend

# MD_CREATE_FLIGHT and MD_UPDATE_FLIGHT accept instance_type from this client release.
FLIGHT_INSTANCE_TYPE_MIN_DUCKDB = (1, 5, 6)

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
    """Strict identifier quoting, kept for compatibility. Deploy SQL uses ``quote_name``."""
    rendered = str(value)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", rendered):
        raise ValidationError(f"Unsafe SQL identifier: {rendered!r}")
    return f'"{rendered}"'


def quote_name(value: object) -> str:
    return '"' + str(value).replace('"', '""') + '"'


_REQUIRED_DATABASES_EXPORT = re.compile(r"^export const REQUIRED_DATABASES\s*=\s*", re.MULTILINE)
_LEGACY_REQUIRED_DATABASES_LINE = re.compile(r"export const REQUIRED_DATABASES[^\n]*\n")
FLIGHT_RUN_DEFAULT_POLL_ATTEMPTS = 60
LIST_PAGE_SIZE = 1000
FLIGHT_RUN_START_GRACE_SECONDS = 120
AUTHORITATIVE_NOTE = (
    "mode: authoritative revokes every grant not declared here, including grants created outside "
    "Blueprints (for example by Terraform or the UI)"
)


def required_databases_export(source: str, start: int = 0) -> tuple[int, int, object] | None:
    """Locate a static ``export const REQUIRED_DATABASES = ...`` at a line start.

    Returns ``(start, end, value)`` where ``end`` includes the trailing ``;`` and line
    break. The value is parsed with JSON5, so JavaScript object syntax, comments,
    trailing commas, ``as const`` and multi-line arrays are supported without
    evaluating code.
    """
    match = _REQUIRED_DATABASES_EXPORT.search(source, start)
    if match is None:
        return None
    value, error, end = json5.parse(source, start=match.end(), consume_trailing=False, allow_duplicate_keys=False)
    if error:
        raise ValidationError("REQUIRED_DATABASES must be a static array")
    suffix = re.match(r"[ \t]*(?:as[ \t]+const)?[ \t]*;?[ \t]*(?:\r?\n|$)", source[end:])
    if suffix is None:
        raise ValidationError("Unsupported expression after REQUIRED_DATABASES")
    return match.start(), end + suffix.end(), value


def strip_required_databases_export(source: str) -> str:
    """Remove the local-preview ``REQUIRED_DATABASES`` export before deploying a Dive.

    Single-line exports are removed exactly as before (the legacy line regex).
    Multi-line static exports are removed as a whole instead of leaving the array
    body behind.
    """
    result = source
    position = 0
    while True:
        try:
            found = required_databases_export(result, position)
        except ValidationError:
            match = _REQUIRED_DATABASES_EXPORT.search(result, position)
            if match is None:
                break
            position = match.end()
            continue
        if found is None:
            break
        start, end, _ = found
        if "\n" in result[start:end].rstrip("\r\n"):
            result = result[:start] + result[end:]
            position = start
        else:
            position = end
    return _LEGACY_REQUIRED_DATABASES_LINE.sub("", result)


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
    def format(records: list[PlanRecord], *, title: str, requested: list[str] | None = None) -> str:
        if not records:
            return f"#### {title}\n\nNo resources selected."
        selection = PlanFormatter.selection(requested, [record.blueprint for record in records])
        return "\n\n".join(part for part in (f"#### {title}", selection, PlanFormatter.table(records)) if part)

    @staticmethod
    def selection(requested: list[str] | None, deployed: list[str]) -> str:
        """Separate the packages a run asked for from those the dependency graph added."""
        if not requested:
            return ""
        added = list(dict.fromkeys(name for name in deployed if name not in requested))
        line = f"**Selected:** {PlanFormatter._names(requested)}"
        if added:
            line += f" · **Added by the dependency graph:** {PlanFormatter._names(added)}"
        return line

    @staticmethod
    def table(records: list[PlanRecord]) -> str:
        lines = [
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
    def _count(count: int, noun: str) -> str:
        return f"{count} {noun}" if count == 1 else f"{count} {noun}s"

    @staticmethod
    def _names(names: list[str]) -> str:
        return ", ".join(f"`{name}`" for name in names)

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
        self.target: str | None = None

    def plan(self, *, target: str, branch: str | None, names: list[str] | None) -> list[PlanRecord]:
        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "plan")
        self._preflight_rbac(rendered)
        self._preflight_flight_instance_types(rendered)
        return self._build_deploy_plan(rendered)

    def verify(self, *, target: str, branch: str | None, names: list[str] | None) -> list[PlanRecord]:
        rendered = copy.deepcopy(self._validate_and_render(target, branch, names))
        # Imported bindings can be checked before enabling writes in their manifests.
        for blueprint in rendered:
            for resource in [*blueprint.flights.values(), *blueprint.dives.values(), *blueprint.guides.values()]:
                if resource.get("id"):
                    resource["deploy"] = True
        self._prepare_live_command(target, "verify")
        self._preflight_rbac(rendered)
        records = self._verify_rendered(rendered)
        self._verification_summary(records, names)
        return records

    @staticmethod
    def _verification_summary(records: list[PlanRecord], requested: list[str] | None = None) -> str:
        summary = PlanFormatter.format(records, title="Deployment Verification", requested=requested)
        if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(summary_path).open("a", encoding="utf-8") as handle:
                handle.write(summary + "\n")
        return summary

    @staticmethod
    def _preview_report(
        requested: list[str] | None,
        rendered: list[RenderedBlueprint],
        sections: list[str],
        verified: list[PlanRecord] | None,
    ) -> str:
        """Lead with what changed and the preview links; fold the full resource table away."""
        parts = [PlanFormatter.selection(requested, [blueprint.name for blueprint in rendered]), *sections]
        if verified:
            resources = PlanFormatter._count(len(verified), "resource")
            blueprints = PlanFormatter._count(len({record.blueprint for record in verified}), "blueprint")
            parts.append(
                "<details>\n"
                f"<summary>Verified {resources} across {blueprints}</summary>\n\n"
                f"{PlanFormatter.table(verified)}\n\n"
                "</details>"
            )
        return "\n\n".join(part for part in parts if part)

    def _verify_rendered(
        self, rendered: list[RenderedBlueprint], expected: list[PlanRecord] | None = None,
    ) -> list[PlanRecord]:
        actual = self._build_deploy_plan(rendered)
        self.ensure_plan_succeeds(actual)
        baseline = self._index_by_resource(expected or [])
        observed = self._index_by_resource(actual)
        for key, previous in baseline.items():
            if previous.action not in {"validated_only", "skipped"} and key not in observed:
                raise ValidationError(f"Verification omitted resource {'.'.join(key)}")
        for record in actual:
            if record.action in {"validated_only", "skipped"}:
                continue
            if record.action not in {"update", "present"} or not record.id:
                raise ValidationError(f"{record.blueprint}.{record.type}.{record.key} is not present after verification")
            before = baseline.get((record.blueprint, record.type, record.key))
            if before and before.id and record.type in {"flight", "dive", "guide"} and before.id != record.id:
                raise ValidationError(f"{record.blueprint}.{record.type}.{record.key} changed identity: {before.id} -> {record.id}")
            desired_status = record.desired_status
            if before and record.type == "dive" and desired_status is None:
                desired_status = before.current_status or ("draft" if before.action == "create" else None)
            if desired_status and record.current_status != desired_status:
                raise ValidationError(
                    f"{record.blueprint}.{record.key} status is {record.current_status}, expected {desired_status}"
                )
        return [
            replace(record, action="verified", notes="live identity and dependencies verified")
            if record.action not in {"validated_only", "skipped"} else record
            for record in actual
        ]

    def deploy(
        self, *, target: str, branch: str | None, names: list[str] | None, verify: bool = True,
    ) -> None:
        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "deploy")
        self._preflight_rbac(rendered)
        self._preflight_flight_instance_types(rendered)
        records = self._build_deploy_plan(rendered)
        self.ensure_plan_succeeds(records)
        plan_index = self._index_by_resource(records)

        for blueprint, key, role in self._role_deployment_order(rendered):
            self._deploy_role(role, plan_index[(blueprint.name, "role", key)])

        sections: list[str] = []
        verified: list[PlanRecord] | None = None
        try:
            for blueprint in rendered:
                if section := self._deploy_blueprint(blueprint, target, plan_index):
                    sections.append(section)
            if verify:
                try:
                    verified = self._verify_rendered(rendered, records)
                except (ValidationError, CommandError) as exc:
                    raise CommandError(
                        f"Deployment applied, but verification failed: {exc}. No rollback was attempted."
                    ) from exc
        except BaseException:
            # Keep links to the packages that did deploy in the log.
            if sections:
                print("\n\n".join(sections))
            raise
        if verified is not None:
            summary = self._verification_summary(verified, names)
            if target != "preview":
                print(summary)
        if target == "preview":
            print(self._preview_report(names, rendered, sections, verified))

    def cleanup_plan(self, *, target: str, branch: str | None, names: list[str] | None) -> list[PlanRecord]:
        if target != "preview":
            raise ValidationError("cleanup is only supported for preview target")
        policies = self.project.target_config(target).get("policies", {})
        if not isinstance(policies, dict) or policies.get("cleanup") is not True:
            raise ValidationError("cleanup is disabled by the preview target policy")

        rendered = self._validate_and_render(target, branch, names)
        self._prepare_live_command(target, "cleanup")
        rendered_names = [blueprint.name for blueprint in rendered]
        stable_target = self.project.preview_stable_target()
        # Compare against every stable target, not only the one previews promote to.
        stable_renders = {
            name: {
                blueprint.name: blueprint
                for blueprint in self.project.render_all(name, names=rendered_names)
            }
            for name in self.project.target_names()
            if name != "preview"
        }
        current_slug = branch_slug(branch or "")
        records = self._build_cleanup_plan(
            rendered,
            current_slug,
            branch=branch,
            production=stable_renders.get(stable_target),
            stable_target=stable_target,
            stable_renders=stable_renders,
        )
        legacy_slug = legacy_branch_slug(branch or "")
        if legacy_slug == current_slug:
            return records
        # Previews created before long slugs were hashed used the plain truncation.
        # Plan and deploy never use it; cleanup removes what it finds and nothing else.
        legacy_rendered = self.project.render_all(
            target, branch=branch, names=rendered_names, slug_override=legacy_slug,
        )
        legacy_records = self._build_cleanup_plan(
            legacy_rendered,
            legacy_slug,
            branch=branch,
            production=stable_renders.get(stable_target),
            stable_target=stable_target,
            stable_renders=stable_renders,
        )
        return records + self._legacy_cleanup_records(records, legacy_records)

    def _legacy_cleanup_records(
        self, records: list[PlanRecord], legacy_records: list[PlanRecord],
    ) -> list[PlanRecord]:
        """Keep only legacy-slug records that remove something that exists.

        Safety errors and missing resources are dropped: the legacy pass must never
        block cleanup of current previews, and it never writes unless a resource matches.
        """
        seen = {(record.type, record.name, record.id) for record in records}
        kept: list[PlanRecord] = []
        for record in legacy_records:
            identity = (record.type, record.name, record.id)
            if identity in seen:
                continue
            if record.action in {"delete", "drop_share"}:
                pass
            elif record.action == "drop_database" and self._database_exists(record.name):
                record.notes = "legacy preview slug; database exists"
            else:
                continue
            if not record.notes:
                record.notes = "legacy preview slug from before long branch slugs were hashed"
            seen.add(identity)
            kept.append(record)
        return kept

    def _database_exists(self, name: str) -> bool:
        try:
            rows = self._query_rows(
                "SELECT alias FROM MD_ALL_DATABASES() "
                f"WHERE lower(alias) = lower({sql_string(name)}) AND type = 'motherduck'"
            )
        except CommandError:
            return False
        return bool(rows)

    def cleanup(self, *, target: str, branch: str | None, names: list[str] | None) -> None:
        records = self.cleanup_plan(target=target, branch=branch, names=names)
        self.ensure_plan_succeeds(records)
        self._apply_cleanup_plan(records)

    def ensure_plan_succeeds(self, records: list[PlanRecord]) -> None:
        identities: set[tuple[str, str]] = set()
        for record in records:
            if record.id and record.action == "update":
                identity = (record.type, record.id)
                if identity in identities:
                    raise ValidationError(f"Multiple resources would update the same {record.type} id {record.id}")
                identities.add(identity)
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
        self.target = target
        expanded_names = set(self.project.deployment_blueprint_names(target, names))
        self.rendered_by_name = {
            blueprint.name: blueprint
            for blueprint in self.project.render_all(target, branch=branch)
        }
        return [blueprint for name, blueprint in self.rendered_by_name.items() if name in expanded_names]

    def _prepare_live_command(self, target: str, operation: str) -> None:
        deployment = self.project.target_config(target).get("deployment", {})
        token_env_var = "MOTHERDUCK_TOKEN"
        if isinstance(deployment, dict):
            token_env_var = str(deployment.get("tokenEnvVar", token_env_var))
        token = os.environ.get(token_env_var, "")
        if not token:
            if (
                operation == "import" and token_env_var == "MOTHERDUCK_TOKEN"
                and not os.environ.get("CI") and not os.environ.get("GITHUB_ACTIONS")
                and sql_backend() == "motherduck"
            ):
                # Local read-only export can use `motherduck login`. CI and all other
                # live commands still require the selected target's token.
                self.sql_env = {}
                return
            environment = self.project.target_config(target).get("environment", target)
            raise ValidationError(
                f"{token_env_var} is required to {operation} target {target}.\n"
                f"Next: in GitHub Settings > Environments > {environment}, add the {token_env_var} "
                "secret using a service-account read/write token. Ensure the job selects that environment. "
                f"For local commands, provide {token_env_var} through your secret manager."
            )
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
            blueprint.name: any(
                flight.get("runOnDeploy") is True and flight.get("deploy") is not False
                for flight in blueprint.flights.values()
            )
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
                role_notes = (
                    "included role(s) do not exist and are not selected for deployment: "
                    f"{', '.join(missing_roles)}"
                    if missing_roles
                    else ""
                )
                if not missing_roles and role.get("mode") == "authoritative":
                    role_notes = self._authoritative_role_note(role, exists)
                records.append(
                    PlanRecord(
                        blueprint.name,
                        "role",
                        key,
                        name,
                        "error" if missing_roles else ("update" if exists else "create"),
                        exists,
                        name if exists else None,
                        role_notes,
                    )
                )

            for key, flight in blueprint.flights.items():
                if flight.get("deploy") is False:
                    records.append(PlanRecord(
                        blueprint.name, "flight", key, str(flight["name"]), "validated_only",
                        None, str(flight["id"]) if flight.get("id") else None,
                        "set deploy: true in the intended target after reviewing the import",
                    ))
                    continue
                if flight.get("id"):
                    records.append(self._bound_resource_record(blueprint, "flight", key, flight))
                    continue
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
                    if isinstance(grants, dict) and grants.get("mode") == "authoritative":
                        notes = f"{notes}; {self._authoritative_share_note(share)}"
                elif url:
                    action = "present"
                    notes = "share is available"
                elif can_produce[blueprint.name]:
                    action = "pending"
                    notes = "will be produced by a Flight configured with runOnDeploy"
                else:
                    action = "error"
                    notes = (
                        "share is missing and no Flight in this blueprint is configured with runOnDeploy. "
                        "Next: run the data-producing Flight first, or set runOnDeploy: true in its manifest"
                    )
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
                        "with runOnDeploy. Next: run the producer first, or set runOnDeploy: true on its Flight"
                    )
                else:
                    action = "error"
                    notes = (
                        f"required production output {producer}.{output} is not available. "
                        f"Next: deploy producer {producer!r} to the same target first, "
                        "or include it in --blueprints so its data is created before this dashboard"
                    )
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
                        notes=(
                            "resources.context is deprecated and never deploys. "
                            "Next: move this file to resources.guides"
                        ),
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
        stable_target: str = "prod",
        stable_renders: dict[str, dict[str, RenderedBlueprint]] | None = None,
    ) -> list[PlanRecord]:
        if stable_renders is None:
            stable_renders = {stable_target: production} if production else {}

        def stable_names(blueprint_name: str, group: str, key: str, field: str) -> list[tuple[str, str]]:
            names: list[tuple[str, str]] = []
            for target_name, blueprints in stable_renders.items():
                stable_blueprint = blueprints.get(blueprint_name)
                resources = getattr(stable_blueprint, group) if stable_blueprint else {}
                value = resources.get(key, {}).get(field) if isinstance(resources, dict) else None
                if value is not None:
                    names.append((target_name, str(value)))
            return names

        def scope_error(resource_type: str, name: str, blueprint_name: str, group: str, key: str, field: str) -> str | None:
            return self._preview_scope_error(
                resource_type,
                name,
                branch,
                rendered_branch_slug,
                None,
                stable_target,
                stable_names=stable_names(blueprint_name, group, key, field),
            )

        records: list[PlanRecord] = []
        dependency_safe = list(reversed(rendered))
        for blueprint in dependency_safe:
            for key in reversed(self._guide_deployment_order(blueprint)):
                guide = blueprint.guides[key]
                if not guide.get("deploy") or not guide.get("cleanup", True):
                    continue
                title = str(guide["title"])
                safety_error = scope_error("Guide", title, blueprint.name, "guides", key, "title")
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
            for key, dive in blueprint.dives.items():
                if dive.get("deploy") is False:
                    continue
                title = str(dive["title"])
                safety_error = scope_error("Dive", title, blueprint.name, "dives", key, "title")
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
            for key, flight in blueprint.flights.items():
                if flight.get("deploy") is False:
                    continue
                name = str(flight["name"])
                safety_error = scope_error("Flight", name, blueprint.name, "flights", key, "name")
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
            for key, share in blueprint.shares.items():
                if not share.get("cleanup", True):
                    continue

                share_name = str(share["name"])
                database_name = str(share["database"])
                share_safety_error = scope_error("share", share_name, blueprint.name, "shares", key, "name")
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

                database_safety_error = scope_error(
                    "database", database_name, blueprint.name, "shares", key, "database"
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
        stable_target: str = "prod",
        *,
        stable_names: list[tuple[str, str]] | None = None,
    ) -> str | None:
        candidates = list(stable_names or [])
        if production_name is not None:
            candidates.insert(0, (stable_target, production_name))
        for target_name, stable_name in candidates:
            if name == stable_name:
                stable_label = "production" if target_name == "prod" else target_name
                return f"refusing to delete preview {resource_type} because it matches {stable_label}: {name}"
        branch_markers = {rendered_branch_slug}
        if branch:
            branch_markers.add(branch)
        # The marker must be a whole delimited token so e.g. branch "main" never
        # authorizes deleting "domain_data".
        if not any(contains_branch_marker(name, marker) for marker in branch_markers):
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
            return PlanRecord(
                blueprint.name, type_name, key, name, "update", True, ids[0],
                self._name_match_note(type_name.title(), name),
            )
        return PlanRecord(blueprint.name, type_name, key, name, "error", True, ",".join(ids), duplicate_note)

    def _name_match_note(self, type_label: str, name: str, existing: str = "") -> str:
        """Explain name-based adoption on stable targets, where ``id`` binding is available."""
        if self.target == "preview":
            return existing
        note = (
            f"matched existing {type_label} '{name}' by name; bind it with `id` "
            "(see make export / md-blueprints import) so another tool cannot own it silently"
        )
        return f"{existing}; {note}" if existing else note

    def _bound_resource_record(
        self, blueprint: RenderedBlueprint, kind: str, key: str, resource: dict[str, object],
    ) -> PlanRecord:
        resource_id = str(resource["id"])
        name = str(resource.get("name", resource.get("title", key)))
        record = PlanRecord(blueprint.name, kind, key, name, "error", False, resource_id)
        id_column = "flight_id" if kind == "flight" else "id"
        status_column = ", status" if kind == "dive" else ""
        try:
            rows = self._query_rows(
                f"SELECT {id_column}, owner_name{status_column} FROM MD_GET_{kind.upper()}("
                f"{id_column} := {sql_string(resource_id)}::UUID)"
            )
        except CommandError:
            record.notes = f"configured {kind.title()} id is missing or inaccessible; refusing to create a replacement"
            return record
        if len(rows) != 1 or str(rows[0][0]) != resource_id:
            record.notes = f"configured {kind.title()} id does not exist; refusing to create a replacement"
            return record
        record.exists = True
        live_owner = str(rows[0][1]) if len(rows[0]) > 1 and rows[0][1] is not None else ""
        if resource.get("owner") and str(resource["owner"]) != live_owner:
            record.notes = "live owner differs from the imported owner; review identity before deployment"
            return record
        if kind == "flight":
            current = self._sql("SELECT current_user").strip()
            if not live_owner or current != live_owner:
                record.notes = "only the Flight creator can update it; use its owner's deployment identity"
                return record
        record.action = "update"
        record.notes = "bound to existing id; no name-based fallback"
        if kind == "dive":
            record.current_status = str(rows[0][2]).lower() if rows[0][2] is not None else None
            record.desired_status = str(resource["status"]) if resource.get("status") else None
        return record

    def _dive_plan_record(
        self,
        blueprint: RenderedBlueprint,
        key: str,
        dive: dict[str, object],
    ) -> PlanRecord:
        title = str(dive["title"])
        if dive.get("deploy") is False:
            return PlanRecord(
                blueprint.name, "dive", key, title, "validated_only", None,
                str(dive["id"]) if dive.get("id") else None,
                "set deploy: true in the intended target after reviewing the import",
            )
        if dive.get("id"):
            return self._bound_resource_record(blueprint, "dive", key, dive)
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
            notes = self._name_match_note("Dive", title, notes)
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
        if guide.get("id"):
            return self._bound_resource_record(blueprint, "guide", key, guide)
        ids = self._list_guide_ids(title, str(guide.get("topic", "")))
        if not ids:
            return PlanRecord(blueprint.name, "guide", key, title, "create", False, None)
        if len(ids) == 1:
            return PlanRecord(
                blueprint.name, "guide", key, title, "update", True, ids[0], self._name_match_note("Guide", title),
            )
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
            group = {"flight": producer.flights, "dive": producer.dives, "guide": producer.guides}[reference_type]
            selected_resource_will_deploy = selected_resource_will_deploy and bool(
                group[resource_key].get("deploy", reference_type != "guide")
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
            rows = self._query_rows(f"SELECT id FROM MD_GET_DIVE(id := {uuid_sql})")
        elif reference_type == "flight":
            rows = self._query_rows(
                f"SELECT flight_id FROM MD_GET_FLIGHT(flight_id := {uuid_sql})"
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
        group = {"flight": producer.flights, "dive": producer.dives, "guide": producer.guides}[reference_type]
        if group[resource_key].get("id"):
            return self._resource_ids_by_uuid(reference_type, str(group[resource_key]["id"]))
        if reference_type == "dive":
            return [
                state[0]
                for state in self._list_dive_states(str(producer.dives[resource_key]["title"]))
            ]
        if reference_type == "flight":
            return self._list_flight_ids(str(producer.flights[resource_key]["name"]))

        referenced_guide = producer.guides[resource_key]
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
    ) -> str | None:
        """Deploy one package and return its preview links as Markdown."""
        print(f"Deploying blueprint '{blueprint.name}' to {target}...", file=sys.stderr)
        flight_rows: list[str] = []
        share_rows: list[str] = []
        dive_rows: list[str] = []
        guide_rows: list[str] = []

        for key, flight in blueprint.flights.items():
            if flight.get("deploy") is False:
                continue
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
            if dive.get("deploy") is False:
                continue
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
            return None

        sections = [
            self._format_section("Flights", "| Flight | ID | Run started |", "|--------|----|-------------|", flight_rows),
            self._format_section("Shares", "| Share | Link |", "|-------|------|", share_rows),
            self._format_section("Dives", "| Dive | Status | Link |", "|------|--------|------|", dive_rows),
            self._format_section("Guides", "| Guide | ID |", "|-------|----|", guide_rows),
        ]
        body = [section for section in sections if section]
        return "\n\n".join([f"#### {blueprint.title}", *body]) if body else None

    @staticmethod
    def _format_section(title: str, header: str, separator: str, rows: list[str]) -> str:
        if not rows:
            return ""
        return "\n".join([f"##### {title}", "", header, separator, *rows])

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
        if flight.get("manageSchedule") is False and plan.action == "update":
            common_args.remove(schedule_arg)
        access_token_name = str(flight.get("accessTokenName", ""))
        if access_token_name:
            common_args.insert(3, f'"access_token_name" => {sql_string(access_token_name)}')
        if "maxRuntimeSec" in flight:
            common_args.insert(3, f'"max_runtime_sec" => {int(str(flight["maxRuntimeSec"]))}::UINTEGER')
        # Omitted means the plan default on create and the current size on update.
        if instance_type := str(flight.get("instanceType", "")):
            common_args.insert(3, f'"instance_type" => {sql_string(instance_type)}')
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

        plan.id = flight_id
        run_started = False
        if flight.get("runOnDeploy", False):
            print(f"  Starting flight run for '{name}'...", file=sys.stderr)
            submitted_run = self._sql(
                f"SELECT run_number FROM MD_RUN_FLIGHT(\"config\" => {config_sql}, \"flight_id\" => '{flight_id}'::UUID);"
            ).strip()
            if not submitted_run.isdecimal() or int(submitted_run) < 1:
                raise CommandError("Flight run was submitted but returned no valid run number. No retry was attempted.")
            run_number = int(submitted_run)
            run_started = True
            if flight.get("waitForRun", False) == "success":
                max_runtime = flight.get("maxRuntimeSec")
                self._wait_for_flight_run_success(
                    flight_id,
                    run_number,
                    max_runtime_sec=max_runtime if isinstance(max_runtime, int) else None,
                    name=name,
                )

        return f"| {name} | {flight_id} | {str(run_started).lower()} |" if target == "preview" else None

    def _flight_run_status(self, flight_id: str, run_number: int) -> str:
        # MD_GET_FLIGHT_RUN is unavailable before DuckDB 1.5.5. The paginated
        # listing works on both runtimes and must match the submitted run exactly.
        offset = 0
        previous_last: int | None = None
        while True:
            rows = self._query_rows(
                "SELECT run_number, status FROM MD_LIST_FLIGHT_RUNS("
                f"flight_id := '{flight_id}'::UUID, \"limit\" := 100, \"offset\" := {offset})"
            )
            for number, status in rows:
                if int(str(number)) == run_number:
                    return str(status).removeprefix("RUN_STATUS_")
            if len(rows) < 100:
                return ""
            last = int(str(rows[-1][0]))
            if previous_last is not None and last >= previous_last:
                raise CommandError("Flight run pagination did not advance. No new run was submitted.")
            previous_last = last
            offset += len(rows)

    @staticmethod
    def _flight_run_poll_attempts(sleep_seconds: int, max_runtime_sec: int | None) -> int:
        override = os.environ.get("FLIGHT_RUN_POLL_ATTEMPTS")
        if override is not None:
            return max(1, int(override))
        attempts = FLIGHT_RUN_DEFAULT_POLL_ATTEMPTS
        if max_runtime_sec and max_runtime_sec > 0:
            # Allow the Flight's own runtime cap plus time to queue and start.
            derived = math.ceil((max_runtime_sec + FLIGHT_RUN_START_GRACE_SECONDS) / max(1, sleep_seconds))
            attempts = max(attempts, derived)
        return attempts

    def _wait_for_flight_run_success(
        self,
        flight_id: str,
        run_number: int,
        *,
        max_runtime_sec: int | None = None,
        name: str | None = None,
    ) -> None:
        sleep_seconds = int(os.environ.get("FLIGHT_RUN_POLL_SLEEP_SECONDS", "10"))
        attempts = self._flight_run_poll_attempts(sleep_seconds, max_runtime_sec)

        for index in range(attempts):
            status = self._flight_run_status(flight_id, run_number)
            if status == "SUCCEEDED":
                return
            if status in {"FAILED", "CANCELLED"}:
                try:
                    records = [
                        json.loads(str(row[0])) for row in self._query_rows(
                            "SELECT to_json(entry) FROM MD_GET_FLIGHT_LOGS("
                            f"flight_id := '{flight_id}'::UUID, run_number := {run_number}) entry"
                        )
                    ]
                    records.sort(key=lambda entry: entry.get("line_number") or 0)
                    # DuckDB <1.5.5 returns one `logs` field. Newer runtimes return
                    # one `line` per row. Keep the failure message bounded in both.
                    logs = "\n".join(str(entry.get("line", entry.get("logs")) or "") for entry in records)[-4000:]
                except (CommandError, ValueError, TypeError, AttributeError) as exc:
                    logs = f"Logs unavailable: {exc}"
                raise CommandError(f"Flight run {run_number} ended with {status}. Log tail: {logs}")
            if index < attempts - 1:
                time.sleep(sleep_seconds)

        label = f"Flight '{name}' ({flight_id})" if name else f"Flight {flight_id}"
        waited = attempts * max(0, sleep_seconds) if attempts > 1 else 0
        raise CommandError(
            f"Timed out after about {waited}s waiting for {label} run {run_number} to succeed "
            "(waitForRun: success). Already applied: roles, earlier blueprints and resources in this "
            f"deployment, and this Flight's source and settings; run {run_number} was started and was not "
            "cancelled. Not applied: the shares, Dives, and Guides that follow this Flight, and the postcheck. "
            f"Next: check run {run_number} in MotherDuck and rerun the deployment once it succeeds. If the "
            "run legitimately takes longer, set maxRuntimeSec on the Flight (the wait follows it) or raise "
            "FLIGHT_RUN_POLL_ATTEMPTS / FLIGHT_RUN_POLL_SLEEP_SECONDS."
        )

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
        content_sql = self._dive_content_sql(str(dive["sourcePath"]))
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

        plan.id = dive_id
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

    @staticmethod
    def _dive_content_sql(source_path: str) -> str:
        legacy_sql = (
            "(SELECT regexp_replace(content, 'export const REQUIRED_DATABASES[^\\n]*\\n', '', 'g') "
            f"FROM read_text({sql_string(source_path)}))"
        )
        try:
            source = Path(source_path).read_text(encoding="utf-8")
        except OSError:
            return legacy_sql
        stripped = strip_required_databases_export(source)
        if stripped == _LEGACY_REQUIRED_DATABASES_LINE.sub("", source):
            # Single-line exports keep the exact server-side stripping used before.
            return legacy_sql
        return f"({sql_string(stripped)})"

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

    def _preflight_flight_instance_types(self, rendered: list[RenderedBlueprint]) -> None:
        """Fail before any write when the SQL backend cannot send a Flight instance size."""
        sized = [
            f"{blueprint.name}.{key}"
            for blueprint in rendered
            for key, flight in blueprint.flights.items()
            if flight.get("instanceType") and flight.get("deploy") is not False
        ]
        if not sized:
            return
        version = self._sql("SELECT library_version FROM pragma_version()")
        match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
        if match and tuple(int(part) for part in match.groups()) >= FLIGHT_INSTANCE_TYPE_MIN_DUCKDB:
            return
        minimum = ".".join(str(part) for part in FLIGHT_INSTANCE_TYPE_MIN_DUCKDB)
        raise ValidationError(
            f"instanceType on {', '.join(sized)} needs DuckDB {minimum} or newer, but the "
            f"{sql_backend()} SQL backend runs {version or 'an unknown version'}. Install md-blueprints[deploy] "
            "and set MD_BLUEPRINTS_SQL_BACKEND=duckdb, or remove instanceType to keep the current size."
        )

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

        # SHOW ROLES TO USER needs a literal name and lists inherited roles too.
        user = self._sql("SELECT current_user").strip()
        rows = self._query_rows(f"SHOW ROLES TO USER {quote_name(user)}")
        roles = {str(row[0]).lower() for row in rows}
        if "admin" not in roles:
            reasons = "; ".join(admin_reasons)
            raise ValidationError(
                f"RBAC preflight failed: target requires the admin role ({reasons}); "
                f"the deployment identity has: {', '.join(sorted(roles)) or 'no roles'}. "
                "Next: use a service account with the admin role, or disable the resources "
                "that require organization administration."
            )

    def _current_role_grants(self, name: str) -> tuple[set[str], set[str]]:
        name_sql = quote_name(name)
        current_roles = {
            str(row[0])
            for row in self._query_rows(f"SHOW ROLES TO ROLE {name_sql}")
            if len(row) >= 3 and bool(row[2])
        }
        current_users = {str(row[0]) for row in self._query_rows(f"SHOW USERS OF ROLE {name_sql}")}
        return current_roles, current_users

    def _current_share_grantees(self, name: str) -> tuple[set[str], set[str]]:
        rows = self._query_rows(
            "SELECT grantee_name, grantee_type "
            f"FROM md_list_share_grantees({sql_string(name)})"
        )
        roles = {str(row[0]) for row in rows if str(row[1]).lower() == "role"}
        users = {str(row[0]) for row in rows if str(row[1]).lower() == "user"}
        return roles, users

    @staticmethod
    def _revocation_summary(roles: set[str], users: set[str]) -> str:
        revocations = [f"role {value}" for value in sorted(roles)] + [f"user {value}" for value in sorted(users)]
        return f"will revoke: {', '.join(revocations)}" if revocations else "nothing to revoke today"

    def _authoritative_role_note(self, role: dict[str, object], exists: bool) -> str:
        if not exists:
            return f"{AUTHORITATIVE_NOTE}; nothing to revoke today (new role)"
        included = role.get("includedRoles", [])
        members = role.get("members", [])
        desired_roles = {str(value) for value in included} if isinstance(included, list) else set()
        desired_users = {str(value) for value in members} if isinstance(members, list) else set()
        try:
            current_roles, current_users = self._current_role_grants(str(role["name"]))
        except CommandError:
            return f"{AUTHORITATIVE_NOTE}; current grants could not be read at plan time"
        return (
            f"{AUTHORITATIVE_NOTE}; "
            f"{self._revocation_summary(current_roles - desired_roles, current_users - desired_users)}"
        )

    def _authoritative_share_note(self, share: dict[str, object]) -> str:
        grants = share.get("grants")
        assert isinstance(grants, dict)
        desired_roles = {str(value) for value in grants.get("roles", [])}
        desired_users = {str(value) for value in grants.get("users", [])}
        try:
            current_roles, current_users = self._current_share_grantees(str(share["name"]))
        except CommandError:
            return f"{AUTHORITATIVE_NOTE}; current grants could not be read at plan time"
        return (
            f"{AUTHORITATIVE_NOTE}; "
            f"{self._revocation_summary(current_roles - desired_roles, current_users - desired_users)}"
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
            current_roles, current_users = self._current_role_grants(name)

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
        current_roles, current_users = self._current_share_grantees(name)

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

        plan.id = guide_id
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
                ids = self._resource_ids_for_reference(reference_type, producer, resource_key)
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
                # Same quoting as shares and roles: any name the Flight could create can be dropped.
                self._sql(f"DROP DATABASE IF EXISTS {quote_name(record.name)};")

    def _delete_if_present(self, statement: str, label: str) -> None:
        try:
            self._sql(statement)
        except CommandError as exc:
            message = str(exc).lower()
            if "does not exist" not in message and "not found" not in message:
                raise
            print(f"Skipping {label}; it was already removed by another cleanup run")

    def _list_all(self, function: str, columns: str, extra_args: str = "") -> list[tuple[object, ...]]:
        """Read every page of an MD_LIST_* function; a single call returns only one page."""
        rows: list[tuple[object, ...]] = []
        seen: set[str] = set()
        offset = 0
        while True:
            page = self._query_rows(
                f'SELECT {columns} FROM {function}("limit" := {LIST_PAGE_SIZE}::UINTEGER, '
                f'"offset" := {offset}::UINTEGER{extra_args})'
            )
            if not page:
                return rows
            ids = {str(row[0]) for row in page}
            if len(ids) != len(page) or seen.intersection(ids):
                raise CommandError(f"{function} repeated an ID while paging; the catalog changed, so retry")
            seen.update(ids)
            rows.extend(page)
            offset += len(page)

    def _list_flight_ids(self, name: str) -> list[str]:
        return [
            str(row[0])
            for row in self._list_all("MD_LIST_FLIGHTS", "flight_id, flight_name")
            if row[1] == name
        ]

    def _list_dive_ids(self, title: str) -> list[str]:
        return [dive_id for dive_id, _ in self._list_dive_states(title)]

    def _list_dive_states(self, title: str) -> list[tuple[str, str | None]]:
        return [
            (str(row[0]), str(row[2]).lower() if row[2] is not None else None)
            for row in self._list_all("MD_LIST_DIVES", "id, title, status")
            if row[1] == title
        ]

    def _list_guide_ids(self, title: str, topic: str) -> list[str]:
        return [
            str(row[0])
            for row in self._list_all("MD_LIST_GUIDES", "id, title, topic")
            if row[1] == title and (row[2] or "") == topic
        ]

    def _find_share_url(self, name: str) -> str:
        lines = self._sql(f"SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = {sql_string(name)}").splitlines()
        return lines[0].strip() if lines else ""

    def _sql(self, statement: str) -> str:
        return format_sql_rows(self._query_rows(statement)).strip()

    def _query_rows(self, statement: str) -> list[tuple[object, ...]]:
        if self.sql_env is None:
            raise ValidationError("MotherDuck token was not prepared for live command")
        if sql_backend() == "motherduck":
            token = self.sql_env.get("motherduck_token")
            return cli_query_rows(statement, token=str(token) if token is not None else None)
        try:
            import duckdb
            # Timestamp decoding can otherwise fail after a mutating query ran.
            importlib.import_module("pytz")
        except ModuleNotFoundError as exc:
            raise CommandError(
                "Install the MotherDuck CLI with make install-deploy. "
                "For the legacy Python backend, install md-blueprints[deploy]."
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
