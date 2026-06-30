"""Load public Wikimedia pageview data and publish it as a MotherDuck share."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import duckdb


PAGEVIEWS_ENDPOINT = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
)

DEFAULT_CONFIG = {
    "project": "en.wikipedia.org",
    "articles": "DuckDB,MotherDuck,Wikipedia",
    "access": "all-access",
    "agent": "user",
    "granularity": "daily",
    "days_back": "30",
    "database": "wikipedia_pageviews",
    "schema": "main",
    "share": "wikipedia_pageviews",
    "share_access": "ORGANIZATION",
    "share_visibility": "DISCOVERABLE",
    "user_agent": (
        "motherduck-blueprints-wikipedia-pageviews/1.0 "
        "(https://github.com/motherduckdb/motherduck-blueprints)"
    ),
}

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_runtime_config() -> dict[str, str]:
    """Accept config from common Flight/env shapes, falling back to defaults."""
    raw = (
        os.getenv("MOTHERDUCK_FLIGHT_CONFIG")
        or os.getenv("FLIGHT_CONFIG")
        or os.getenv("CONFIG")
    )
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


RUNTIME_CONFIG = load_runtime_config()


def setting(name: str) -> str:
    env_keys = (
        f"WIKIPEDIA_PAGEVIEWS_{name.upper()}",
        name.upper(),
        name,
    )
    for key in env_keys:
        if os.getenv(key):
            return os.environ[key]

    for key in (name, name.lower(), name.upper()):
        if key in RUNTIME_CONFIG and RUNTIME_CONFIG[key]:
            return RUNTIME_CONFIG[key]

    return DEFAULT_CONFIG[name]


def quote_ident(value: str) -> str:
    if not SAFE_IDENTIFIER.match(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def pageview_url(
    project: str,
    access: str,
    agent: str,
    article: str,
    granularity: str,
    start: dt.date,
    end: dt.date,
) -> str:
    encoded_article = urllib.parse.quote(article.replace(" ", "_"), safe="")
    return (
        f"{PAGEVIEWS_ENDPOINT}/{project}/{access}/{agent}/"
        f"{encoded_article}/{granularity}/{start:%Y%m%d}00/{end:%Y%m%d}00"
    )


def fetch_json(url: str, user_agent: str, retries: int = 3) -> dict[str, Any]:
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    request = urllib.request.Request(url, headers=headers)

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == retries:
                raise
            time.sleep(attempt * 2)
        except urllib.error.URLError:
            if attempt == retries:
                raise
            time.sleep(attempt * 2)

    raise RuntimeError(f"Failed to fetch {url}")


def fetch_pageviews() -> list[tuple[str, str, str, str, str, dt.date, int, dt.datetime]]:
    project = setting("project")
    access = setting("access")
    agent = setting("agent")
    granularity = setting("granularity")
    days_back = int(setting("days_back"))
    user_agent = setting("user_agent")
    articles = [a.strip() for a in setting("articles").split(",") if a.strip()]

    if not articles:
        raise ValueError("At least one article must be configured")

    end = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days_back - 1)
    loaded_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    rows: list[tuple[str, str, str, str, str, dt.date, int, dt.datetime]] = []

    for article in articles:
        url = pageview_url(project, access, agent, article, granularity, start, end)
        payload = fetch_json(url, user_agent)
        for item in payload.get("items", []):
            viewed_on = dt.datetime.strptime(item["timestamp"][:8], "%Y%m%d").date()
            rows.append(
                (
                    item["project"],
                    article,
                    item["access"],
                    item["agent"],
                    item["granularity"],
                    viewed_on,
                    int(item["views"]),
                    loaded_at,
                )
            )

    return rows


def ensure_schema(con: duckdb.DuckDBPyConnection, database: str, schema: str) -> None:
    database_ident = quote_ident(database)
    schema_ident = quote_ident(schema)

    con.execute(f"CREATE DATABASE IF NOT EXISTS {database_ident}")
    con.execute(f"USE {database_ident}")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_ident}")
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {schema_ident}.pageviews_daily (
          project TEXT NOT NULL,
          article TEXT NOT NULL,
          access TEXT NOT NULL,
          agent TEXT NOT NULL,
          granularity TEXT NOT NULL,
          viewed_on DATE NOT NULL,
          views BIGINT NOT NULL,
          loaded_at_utc TIMESTAMPTZ NOT NULL,
          PRIMARY KEY (project, article, access, agent, viewed_on)
        )
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW {schema_ident}.pageviews_article_summary AS
        SELECT
          project,
          article,
          min(viewed_on) AS first_viewed_on,
          max(viewed_on) AS last_viewed_on,
          sum(views)::BIGINT AS total_views,
          avg(views)::DOUBLE AS avg_daily_views,
          sum(CASE WHEN viewed_on >= current_date - INTERVAL 7 DAY THEN views ELSE 0 END)::BIGINT AS views_last_7_days,
          max(loaded_at_utc) AS loaded_at_utc
        FROM {schema_ident}.pageviews_daily
        GROUP BY project, article
        """
    )


def upsert_rows(
    con: duckdb.DuckDBPyConnection,
    schema: str,
    rows: list[tuple[str, str, str, str, str, dt.date, int, dt.datetime]],
) -> None:
    if not rows:
        raise RuntimeError("Wikimedia returned no pageview rows")

    schema_ident = quote_ident(schema)

    con.execute(
        """
        CREATE TEMP TABLE incoming_pageviews (
          project TEXT,
          article TEXT,
          access TEXT,
          agent TEXT,
          granularity TEXT,
          viewed_on DATE,
          views BIGINT,
          loaded_at_utc TIMESTAMPTZ
        )
        """
    )
    con.executemany(
        "INSERT INTO incoming_pageviews VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    con.execute(
        f"""
        DELETE FROM {schema_ident}.pageviews_daily AS target
        USING incoming_pageviews AS incoming
        WHERE target.project = incoming.project
          AND target.article = incoming.article
          AND target.access = incoming.access
          AND target.agent = incoming.agent
          AND target.viewed_on = incoming.viewed_on
        """
    )
    con.execute(
        f"""
        INSERT INTO {schema_ident}.pageviews_daily
        SELECT
          project,
          article,
          access,
          agent,
          granularity,
          viewed_on,
          views,
          loaded_at_utc
        FROM incoming_pageviews
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
    row = con.execute(f"DESCRIBE SHARE {share_ident}").fetchone()
    if not row:
        raise RuntimeError(f"Share {share!r} was not found after creation")
    return str(row[1])


def main() -> None:
    database = setting("database")
    schema = setting("schema")
    share = setting("share")

    rows = fetch_pageviews()
    con = duckdb.connect("md:")
    con.execute("SET TimeZone='UTC'")
    ensure_schema(con, database, schema)
    upsert_rows(con, schema, rows)
    share_url = publish_share(con, database, share)

    print(f"Loaded {len(rows)} rows into md:{database}.{schema}.pageviews_daily")
    print(f"Published share {share}: {share_url}")


if __name__ == "__main__":
    main()
