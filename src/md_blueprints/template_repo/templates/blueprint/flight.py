"""Starter Flight for the __BLUEPRINT_NAME__ blueprint.

This creates a project-owned database with daily metrics, publishes it as a
share, and gives the starter Dive something real to query.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import duckdb


# Local-run defaults only. Deployments pass config from blueprint.yml, which
# MotherDuck exposes to the Flight as environment variables named after each key.
DEFAULT_CONFIG = {
    "database": "__DATABASE_NAME__",
    "schema": "main",
    "share": "__DATABASE_NAME__",
    "share_access": "ORGANIZATION",
    "share_visibility": "DISCOVERABLE",
}

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONFIG_JSON_VARIABLES = ("MOTHERDUCK_FLIGHT_CONFIG", "FLIGHT_CONFIG", "CONFIG")


def load_runtime_config() -> dict[str, str]:
    """Read optional JSON config. Present but invalid config fails the run."""
    for variable in CONFIG_JSON_VARIABLES:
        raw = os.getenv(variable)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{variable} is not valid JSON ({exc.msg}); refusing to fall back to defaults") from exc
        if not isinstance(parsed, dict):
            raise SystemExit(f"{variable} must be a JSON object; refusing to fall back to defaults")
        return {str(key): str(value) for key, value in parsed.items()}
    return {}


RUNTIME_CONFIG = load_runtime_config()


def setting(name: str) -> str:
    # Flight config keys arrive as environment variables, so check them first.
    for key in (name.upper(), name):
        if os.getenv(key):
            return os.environ[key]
    for key in (name, name.lower(), name.upper()):
        if key in RUNTIME_CONFIG and RUNTIME_CONFIG[key]:
            return RUNTIME_CONFIG[key]
    print(f"Config {name!r} is not set; using the local default {DEFAULT_CONFIG[name]!r}", file=sys.stderr)
    return DEFAULT_CONFIG[name]


def quote_ident(value: str) -> str:
    if not SAFE_IDENTIFIER.match(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def load_starter_data(con: duckdb.DuckDBPyConnection, database: str, schema: str) -> None:
    database_ident = quote_ident(database)
    schema_ident = quote_ident(schema)
    loaded_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    con.execute(f"CREATE DATABASE IF NOT EXISTS {database_ident}")
    con.execute(f"USE {database_ident}")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_ident}")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {schema_ident}.starter_daily_metrics AS
        WITH days AS (
          SELECT
            (current_date - (13 - day_index)::INTEGER)::DATE AS measured_on,
            day_index
          FROM range(14) AS days(day_index)
        ),
        metric_seed(metric, base_value, daily_step) AS (
          VALUES
            ('active_accounts', 118, 2),
            ('daily_queries', 3910, 185),
            ('shared_databases', 4, 1)
        )
        SELECT
          metric,
          measured_on,
          (base_value + day_index * daily_step)::BIGINT AS value,
          ? AS loaded_at_utc
        FROM days
        CROSS JOIN metric_seed
        ORDER BY measured_on, metric
        """,
        [loaded_at],
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW {schema_ident}.starter_metric_summary AS
        SELECT
          metric,
          arg_max(value, measured_on)::BIGINT AS current_value,
          min(value)::BIGINT AS min_value,
          max(value)::BIGINT AS max_value,
          round(avg(value), 2)::DOUBLE AS avg_value,
          sum(value)::BIGINT AS total_value,
          min(measured_on) AS first_measured_on,
          max(measured_on) AS last_measured_on,
          max(loaded_at_utc) AS loaded_at_utc
        FROM {schema_ident}.starter_daily_metrics
        GROUP BY metric
        """
    )


def publish_share(con: duckdb.DuckDBPyConnection, database: str, share: str) -> str:
    share_access = setting("share_access").upper()
    share_visibility = setting("share_visibility").upper()
    if share_access not in {"ORGANIZATION", "UNRESTRICTED", "RESTRICTED"}:
        raise ValueError("share_access must be ORGANIZATION, UNRESTRICTED, or RESTRICTED")
    if share_visibility not in {"DISCOVERABLE", "HIDDEN"}:
        raise ValueError("share_visibility must be DISCOVERABLE or HIDDEN")
    if share_visibility == "HIDDEN" and share_access != "RESTRICTED":
        raise ValueError("HIDDEN shares must use RESTRICTED access")

    database_ident = quote_ident(database)
    share_ident = quote_ident(share)

    con.execute(
        f"""
        CREATE SHARE IF NOT EXISTS {share_ident}
        FROM {database_ident}
        (ACCESS {share_access}, VISIBILITY {share_visibility})
        """
    )
    con.execute(f"UPDATE SHARE {share_ident}")
    row = con.execute(f"SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = {sql_string(share)}").fetchone()
    if not row:
        raise RuntimeError(f"Share {share!r} was not found after creation")
    return str(row[0])


def main() -> None:
    database = setting("database")
    schema = setting("schema")
    share = setting("share")

    con = duckdb.connect("md:")
    load_starter_data(con, database, schema)
    share_url = publish_share(con, database, share)

    print(f"Loaded starter metrics into md:{database}.{schema}.starter_daily_metrics")
    print(f"Published share {share}: {share_url}")


if __name__ == "__main__":
    main()
