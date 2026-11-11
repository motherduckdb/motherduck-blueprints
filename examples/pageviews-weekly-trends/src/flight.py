"""Rebuild weekly pageview reporting tables from the daily Wikipedia pageviews.

This is a SQL transformation Flight: it reads one database, writes another, and
keeps all heavy work in MotherDuck. Each run replaces the reporting tables as a
whole, so a rerun gives the same result and a failed run leaves the previous
tables in place.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys

import duckdb


# Local-run defaults only. Deployments pass config from blueprint.yml, which
# MotherDuck exposes to the Flight as environment variables named after each key.
DEFAULT_CONFIG = {
    "source_database": "wikipedia_pageviews",
    "source_schema": "main",
    "database": "pageviews_trends",
    "schema": "main",
    "share": "pageviews_trends",
    "share_access": "ORGANIZATION",
    "share_visibility": "DISCOVERABLE",
}

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def step(node: str, status: str, **fields: object) -> None:
    """Report progress for the run chart in src/chart.mmd."""
    extra = "".join(f" {key}={value}" for key, value in fields.items())
    print(f"@flight-run {node} {status}{extra}", flush=True)


def connect(database: str) -> duckdb.DuckDBPyConnection:
    """Attach only this Flight's database, which starts faster than the whole workspace.

    The first run creates the database, so it opens the workspace when the database is missing.
    """
    quote_ident(database)
    try:
        return duckdb.connect(f"md:{database}?attach_mode=single")
    except duckdb.Error as exc:
        if "no database/share named" not in str(exc):
            raise
    return duckdb.connect("md:")


def source_row_count(con: duckdb.DuckDBPyConnection, source: str) -> int:
    row = con.execute(f"SELECT count(*) FROM {source}.pageviews_daily").fetchone()
    return int(row[0]) if row else 0


def rebuild(con: duckdb.DuckDBPyConnection, source: str, target: str) -> int:
    """Replace the reporting table and view.

    `source` is a quoted `database.schema`. `target` is a quoted schema in the current database:
    the view must not name its own database, because share readers attach it under another name.
    """
    loaded_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    step("weekly", "running")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {target}.weekly_pageviews AS
        SELECT
          project,
          article,
          date_trunc('week', viewed_on)::DATE AS week_start,
          sum(views)::BIGINT AS views,
          count(DISTINCT viewed_on)::INTEGER AS days_loaded,
          count(DISTINCT viewed_on) = 7 AS is_complete_week,
          ?::TIMESTAMP AS transformed_at_utc
        FROM {source}.pageviews_daily
        GROUP BY project, article, date_trunc('week', viewed_on)
        """,
        [loaded_at],
    )
    row = con.execute(f"SELECT count(*) FROM {target}.weekly_pageviews").fetchone()
    weekly_rows = int(row[0]) if row else 0
    step("weekly", "ok", rows=weekly_rows)

    step("trends", "running")
    # Partial weeks would read as a drop in traffic, so trends use complete weeks only.
    con.execute(
        f"""
        CREATE OR REPLACE VIEW {target}.article_trends AS
        SELECT
          project,
          article,
          week_start,
          views,
          lag(views) OVER article_weeks AS previous_week_views,
          round(
            100.0 * (views - lag(views) OVER article_weeks) / nullif(lag(views) OVER article_weeks, 0), 1
          )::DOUBLE AS week_over_week_pct,
          round(avg(views) OVER (
            PARTITION BY project, article ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
          ))::BIGINT AS four_week_average,
          transformed_at_utc
        FROM {target}.weekly_pageviews
        WHERE is_complete_week
        WINDOW article_weeks AS (PARTITION BY project, article ORDER BY week_start)
        """
    )
    step("trends", "ok")
    return weekly_rows


def publish_share(con: duckdb.DuckDBPyConnection, database: str, share: str) -> None:
    share_access = setting("share_access").upper()
    share_visibility = setting("share_visibility").upper()
    if share_access not in {"ORGANIZATION", "UNRESTRICTED", "RESTRICTED"}:
        raise ValueError("share_access must be ORGANIZATION, UNRESTRICTED, or RESTRICTED")
    if share_visibility not in {"DISCOVERABLE", "HIDDEN"}:
        raise ValueError("share_visibility must be DISCOVERABLE or HIDDEN")
    step("publish", "running")
    con.execute(
        f"""
        CREATE SHARE IF NOT EXISTS {quote_ident(share)}
        FROM {quote_ident(database)}
        (ACCESS {share_access}, VISIBILITY {share_visibility})
        """
    )
    # Dive viewers read through the share, so publish the new tables at the end of the run.
    con.execute(f"UPDATE SHARE {quote_ident(share)}")
    step("publish", "ok")


def main() -> None:
    database = setting("database")
    source_database = setting("source_database")
    source = f"{quote_ident(source_database)}.{quote_ident(setting('source_schema'))}"
    target = quote_ident(setting("schema"))

    con = connect(database)
    con.execute(f"CREATE DATABASE IF NOT EXISTS {quote_ident(database)}")
    con.execute(f"USE {quote_ident(database)}")
    # Attach the database this Flight reads. It is not part of a single-attach connection.
    con.execute(f"ATTACH IF NOT EXISTS 'md:{source_database}'")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {target}")

    step("check_source", "running")
    rows = source_row_count(con, source)
    if rows == 0:
        # Never replace good reporting tables with empty ones.
        step("check_source", "failed", error='"source is empty"')
        raise SystemExit(f"{source}.pageviews_daily has no rows; the reporting tables were left unchanged")
    step("check_source", "ok", rows=rows)

    weekly_rows = rebuild(con, source, target)
    publish_share(con, database, setting("share"))
    print(f"Rebuilt md:{database}.{setting('schema')}.weekly_pageviews with {weekly_rows} rows from {rows} daily rows")


if __name__ == "__main__":
    main()
