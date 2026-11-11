"""Check that tables are fresh and non-empty, record the results, and fail the run on a problem.

Each check is one aggregate query, so the Flight stays cheap enough to run hourly.
A failed check ends the run with a non-zero exit code, which marks the run as failed
in MotherDuck. The results table keeps the history for a Dive or an agent to read.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass

import duckdb


# Local-run defaults only. Deployments pass config from blueprint.yml, which
# MotherDuck exposes to the Flight as environment variables named after each key.
DEFAULT_CONFIG = {
    "database": "data_monitoring",
    "schema": "main",
    "share": "data_monitoring",
    "share_access": "ORGANIZATION",
    "share_visibility": "DISCOVERABLE",
    "fail_on_alert": "true",
    "checks": (
        '[{"table": "wikipedia_pageviews.main.pageviews_daily", '
        '"timestamp_column": "loaded_at_utc", "max_age_hours": 30, "min_rows": 1}]'
    ),
}

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Flight secret `alert_webhook` with key `URL`. Secrets arrive as <secret_name>_<KEY>.
WEBHOOK_VARIABLE = "alert_webhook_URL"


@dataclass(frozen=True)
class Check:
    database: str
    schema: str
    table: str
    timestamp_column: str | None
    max_age_hours: float | None
    min_rows: int | None

    @property
    def name(self) -> str:
        return f"{self.database}.{self.schema}.{self.table}"


@dataclass(frozen=True)
class Result:
    check: Check
    row_count: int
    age_hours: float | None
    problems: tuple[str, ...]

    @property
    def status(self) -> str:
        return "failed" if self.problems else "ok"


def setting(name: str) -> str:
    for key in (name.upper(), name):
        if os.getenv(key):
            return os.environ[key]
    print(f"Config {name!r} is not set; using the local default {DEFAULT_CONFIG[name]!r}", file=sys.stderr)
    return DEFAULT_CONFIG[name]


def quote_ident(value: str) -> str:
    if not SAFE_IDENTIFIER.match(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def step(node: str, status: str, **fields: object) -> None:
    """Report progress for the run chart in src/chart.mmd."""
    extra = "".join(f" {key}={value}" for key, value in fields.items())
    print(f"@flight-run {node} {status}{extra}", flush=True)


def parse_checks(raw: str) -> list[Check]:
    """Validate the `checks` config. It is input from whoever starts the run, so nothing is trusted."""
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"checks is not valid JSON ({exc.msg})") from exc
    if not isinstance(items, list) or not items:
        raise SystemExit("checks must be a non-empty JSON array")
    checks = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("table"), str):
            raise SystemExit('each check needs a "table" written as database.schema.table')
        parts = item["table"].split(".")
        if len(parts) != 3:
            raise SystemExit(f"check table {item['table']!r} must be written as database.schema.table")
        column = item.get("timestamp_column")
        for identifier in [*parts, *([column] if column is not None else [])]:
            if not SAFE_IDENTIFIER.match(str(identifier)):
                raise SystemExit(f"check {item['table']!r} uses the unsafe identifier {identifier!r}")
        max_age = item.get("max_age_hours")
        min_rows = item.get("min_rows")
        if max_age is not None and column is None:
            raise SystemExit(f"check {item['table']!r} sets max_age_hours without timestamp_column")
        checks.append(Check(
            parts[0], parts[1], parts[2], str(column) if column is not None else None,
            float(max_age) if max_age is not None else None,
            int(min_rows) if min_rows is not None else None,
        ))
    return checks


def run_check(con: duckdb.DuckDBPyConnection, check: Check) -> Result:
    table = ".".join(quote_ident(part) for part in (check.database, check.schema, check.table))
    age = (
        # Compare in UTC whatever the column type is; the session time zone is set to UTC in main().
        f"date_diff('minute', max({quote_ident(check.timestamp_column)})::TIMESTAMP, "
        "(now() AT TIME ZONE 'UTC')::TIMESTAMP) / 60.0"
        if check.timestamp_column else "NULL"
    )
    try:
        row = con.execute(f"SELECT count(*), {age} FROM {table}").fetchone()
    except duckdb.Error as exc:
        return Result(check, 0, None, (f"query failed: {str(exc).splitlines()[0]}",))
    row_count = int(row[0]) if row else 0
    age_hours = float(row[1]) if row and row[1] is not None else None
    problems = []
    if check.min_rows is not None and row_count < check.min_rows:
        problems.append(f"{row_count} rows, expected at least {check.min_rows}")
    if check.max_age_hours is not None:
        if age_hours is None:
            problems.append(f"no value in {check.timestamp_column}")
        elif age_hours > check.max_age_hours:
            problems.append(f"newest row is {age_hours:.1f} hours old, limit is {check.max_age_hours:g}")
    return Result(check, row_count, age_hours, tuple(problems))


def record(con: duckdb.DuckDBPyConnection, schema: str, results: list[Result]) -> None:
    """Append one row per check in a single statement. The history is what a Dive or an agent reads."""
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.check_results (
          checked_at_utc TIMESTAMP, checked_table VARCHAR, status VARCHAR,
          row_count BIGINT, age_hours DOUBLE, problems VARCHAR, flight_run_id VARCHAR
        )
        """
    )
    run_id = os.getenv("MOTHERDUCK_FLIGHT_RUN_ID", "")
    values = ", ".join("((now() AT TIME ZONE 'UTC')::TIMESTAMP, ?, ?, ?, ?, ?, ?)" for _ in results)
    parameters: list[object] = []
    for result in results:
        parameters += [
            result.check.name, result.status, result.row_count, result.age_hours, "; ".join(result.problems), run_id,
        ]
    con.execute(f"INSERT INTO {schema}.check_results VALUES {values}", parameters)
    con.execute(
        f"""
        CREATE OR REPLACE VIEW {schema}.latest_check_results AS
        SELECT * FROM {schema}.check_results
        QUALIFY row_number() OVER (PARTITION BY checked_table ORDER BY checked_at_utc DESC) = 1
        """
    )


def publish_share(con: duckdb.DuckDBPyConnection, database: str, share: str) -> None:
    share_access = setting("share_access").upper()
    share_visibility = setting("share_visibility").upper()
    if share_access not in {"ORGANIZATION", "UNRESTRICTED", "RESTRICTED"}:
        raise ValueError("share_access must be ORGANIZATION, UNRESTRICTED, or RESTRICTED")
    if share_visibility not in {"DISCOVERABLE", "HIDDEN"}:
        raise ValueError("share_visibility must be DISCOVERABLE or HIDDEN")
    con.execute(
        f"""
        CREATE SHARE IF NOT EXISTS {quote_ident(share)}
        FROM {quote_ident(database)}
        (ACCESS {share_access}, VISIBILITY {share_visibility})
        """
    )
    con.execute(f"UPDATE SHARE {quote_ident(share)}")


def send_alert(failed: list[Result]) -> None:
    """Post to a webhook when the optional secret is configured. The message format suits Slack."""
    url = os.getenv(WEBHOOK_VARIABLE)
    if not url:
        return
    lines = [f"{result.check.name}: {'; '.join(result.problems)}" for result in failed]
    body = json.dumps({"text": "Data freshness checks failed\n" + "\n".join(lines)}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=15).close()
    except OSError as exc:
        # The run still fails below, so a webhook outage does not hide the problem.
        print(f"Alert webhook failed: {exc}", file=sys.stderr)


def main() -> None:
    database = setting("database")
    schema = quote_ident(setting("schema"))
    checks = parse_checks(setting("checks"))

    quote_ident(database)
    try:
        con = duckdb.connect(f"md:{database}?attach_mode=single")
    except duckdb.Error as exc:
        if "no database/share named" not in str(exc):
            raise
        con = duckdb.connect("md:")  # first run: the results database does not exist yet
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"CREATE DATABASE IF NOT EXISTS {quote_ident(database)}")
    con.execute(f"USE {quote_ident(database)}")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for monitored in sorted({check.database for check in checks} - {database}):
        try:
            con.execute(f"ATTACH IF NOT EXISTS 'md:{monitored}'")
        except duckdb.Error as exc:
            # run_check reports the missing database as a failed check.
            print(f"Could not attach {monitored}: {str(exc).splitlines()[0]}", file=sys.stderr)

    step("run_checks", "running")
    results = [run_check(con, check) for check in checks]
    failed = [result for result in results if result.problems]
    step("run_checks", "ok", rows=len(results))

    step("record", "running")
    record(con, schema, results)
    publish_share(con, database, setting("share"))
    step("record", "ok", rows=len(results))

    for result in results:
        print(f"{result.status.upper():6} {result.check.name} {'; '.join(result.problems)}".rstrip())
    if failed:
        send_alert(failed)
        step("alert", "failed", error=f'"{len(failed)} check(s) failed"')
        if setting("fail_on_alert").lower() == "true":
            raise SystemExit(f"{len(failed)} of {len(results)} checks failed")
    else:
        step("alert", "ok")


if __name__ == "__main__":
    main()
