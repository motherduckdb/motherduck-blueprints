from __future__ import annotations

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

class Deployer:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.sql_env: dict[str, DuckDBConfigValue] | None = None

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
        self.sql_env = {"motherduck_token": token}

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
                self._sql(f"FROM MD_DELETE_FLIGHT(\"flight_id\" => '{record.id}'::UUID);")
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
        return format_sql_rows(rows).strip()
