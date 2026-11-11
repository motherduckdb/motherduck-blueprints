from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import duckdb
import pytest

from e2e_support import Cli


REPO_ROOT = Path(__file__).resolve().parents[1]
# Example directory, and the package root it is copied into to enable it.
EXAMPLES = {
    "pageviews-weekly-trends": "projects",
    "data-freshness-monitor": "flights",
    "pageviews-guide": "guides",
    "ncs-field-recovery": "projects",
}


def load_flight(example: str) -> ModuleType:
    name = f"example_{example.replace('-', '_')}_flight"
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "examples" / example / "src/flight.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def enable(starter: Path, example: str) -> None:
    shutil.copytree(starter / "examples" / example, starter / EXAMPLES[example] / example)


def test_every_example_is_shipped_documented_and_listed_in_the_index() -> None:
    asset_map = json.loads((REPO_ROOT / "src/md_blueprints/asset-map.json").read_text(encoding="utf-8"))
    index = (REPO_ROOT / "docs/examples/README.md").read_text(encoding="utf-8")
    on_disk = sorted(path.name for path in (REPO_ROOT / "examples").iterdir() if path.is_dir())
    assert on_disk == sorted(EXAMPLES)
    for example, root in EXAMPLES.items():
        files = [
            path for path in (REPO_ROOT / "examples" / example).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        ]
        for path in files:
            relative = path.relative_to(REPO_ROOT).as_posix()
            assert asset_map.get(f"template_repo/{relative}") == relative
        assert (REPO_ROOT / "examples" / example / "README.md").is_file()
        assert f"examples/{example}" in index
        assert f"cp -R examples/{example} {root}/{example}" in index
    assert not [source for source in asset_map.values() if "__pycache__" in source or source.endswith(".pyc")]
    shipped = {source for source in asset_map.values() if source.startswith("examples/")}
    assert shipped == {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "examples").rglob("*") if path.is_file() and "__pycache__" not in path.parts
    }


@pytest.mark.parametrize("example", sorted(EXAMPLES))
def test_example_validates_once_copied_into_its_package_root(starter: Path, md_cli: Cli, example: str) -> None:
    enable(starter, example)
    md_cli.ok("validate", "--root", str(starter))
    assert example in md_cli.ok("changed", "--root", str(starter), "--all").stdout.split()


def test_all_examples_validate_together(starter: Path, md_cli: Cli) -> None:
    for example in EXAMPLES:
        enable(starter, example)
    md_cli.ok("validate", "--root", str(starter))


@pytest.mark.parametrize(
    ("example", "flight", "config_key", "expected"),
    [
        ("pageviews-weekly-trends", "transform", "source_database", "wikipedia_pageviews_preview_feature_x"),
        ("data-freshness-monitor", "monitor", "checks", "wikipedia_pageviews_preview_feature_x.main.pageviews_daily"),
    ],
)
def test_example_preview_reads_the_preview_copy_of_its_input(
    starter: Path, md_cli: Cli, example: str, flight: str, config_key: str, expected: str,
) -> None:
    enable(starter, example)
    rendered = md_cli.ok("render", "--root", str(starter), "--branch", "feature/x", "--blueprints", example).json()
    # The producer is added to the preview and deploys first.
    assert [blueprint["name"] for blueprint in rendered] == ["wikipedia-pageviews-ingest", example]
    config = rendered[1]["flights"][flight]["config"]
    assert expected in config[config_key]
    assert config["database"].endswith("_preview_feature_x")
    assert rendered[1]["flights"][flight]["scheduleCron"] == ""


def test_guide_example_references_the_table_the_flight_and_the_dive(starter: Path, md_cli: Cli) -> None:
    enable(starter, "pageviews-guide")
    rendered = md_cli.ok("render", "--root", str(starter), "--blueprints", "pageviews-guide").json()
    guide = next(blueprint for blueprint in rendered if blueprint["name"] == "pageviews-guide")["guides"]["pageviews"]
    assert guide["topic"] == "data-sources/wikipedia-pageviews"
    assert sorted(reference["type"] for reference in guide["references"]) == ["catalog", "catalog", "dive", "flight"]
    # Every column the Guide documents exists in the table the ingest Flight creates.
    flight_source = (REPO_ROOT / "flights/wikipedia-pageviews-ingest/src/flight.py").read_text(encoding="utf-8")
    body = (REPO_ROOT / "examples/pageviews-guide/guide.md").read_text(encoding="utf-8")
    for column in ("project", "article", "access", "agent", "granularity", "viewed_on", "views", "loaded_at_utc"):
        assert f"| `{column}` |" in body and f"{column} " in flight_source
    assert "pageviews_article_summary" in body and "pageviews_article_summary" in flight_source


def local_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute("ATTACH ':memory:' AS src")
    con.execute("ATTACH ':memory:' AS tgt")
    con.execute("USE tgt")
    return con


def test_weekly_trends_transformation_uses_complete_weeks_and_is_repeatable() -> None:
    flight = load_flight("pageviews-weekly-trends")
    con = local_connection()
    # 2026-09-07 is a Monday: four complete weeks and one partial week of three days.
    con.execute(
        """
        CREATE TABLE src.main.pageviews_daily AS
        SELECT 'en.wikipedia.org' AS project, article, (DATE '2026-09-07' + day::INTEGER) AS viewed_on,
               (100 + day * step)::BIGINT AS views
        FROM range(31) AS days(day), (VALUES ('DuckDB', 3), ('MotherDuck', 1)) AS articles(article, step)
        """
    )
    assert flight.source_row_count(con, '"src"."main"') == 62
    assert flight.rebuild(con, '"src"."main"', '"main"') == 10
    assert flight.rebuild(con, '"src"."main"', '"main"') == 10  # a rerun replaces, it does not append

    rows = con.execute(
        "SELECT week_start::VARCHAR, views, previous_week_views, week_over_week_pct, four_week_average "
        "FROM main.article_trends WHERE article = 'DuckDB' ORDER BY week_start"
    ).fetchall()
    assert rows == [
        ("2026-09-07", 763, None, None, 763),
        ("2026-09-14", 910, 763, 19.3, 837),
        ("2026-09-21", 1057, 910, 16.2, 910),
        ("2026-09-28", 1204, 1057, 13.9, 984),
    ]
    partial = con.execute("SELECT count(*) FROM main.weekly_pageviews WHERE NOT is_complete_week").fetchone()
    assert partial == (2,)
    # Share readers attach the database under another name, so the view must not name its database.
    view_sql = con.execute("SELECT sql FROM duckdb_views() WHERE view_name = 'article_trends'").fetchone()
    assert view_sql is not None and "tgt" not in view_sql[0]


def test_freshness_monitor_reports_stale_empty_and_missing_tables() -> None:
    flight = load_flight("data-freshness-monitor")
    con = local_connection()
    con.execute(
        "CREATE TABLE src.main.fresh AS "
        "SELECT (now() AT TIME ZONE 'UTC')::TIMESTAMP - INTERVAL 2 HOUR AS loaded_at_utc FROM range(3)"
    )
    con.execute("CREATE TABLE src.main.stale AS SELECT now() - INTERVAL 3 DAY AS loaded_at FROM range(3)")
    con.execute("CREATE TABLE src.main.empty (loaded_at TIMESTAMP)")
    checks = flight.parse_checks(json.dumps([
        {"table": "src.main.fresh", "timestamp_column": "loaded_at_utc", "max_age_hours": 30, "min_rows": 1},
        {"table": "src.main.stale", "timestamp_column": "loaded_at", "max_age_hours": 30},
        {"table": "src.main.empty", "timestamp_column": "loaded_at", "max_age_hours": 1, "min_rows": 1},
        {"table": "src.main.missing", "min_rows": 1},
    ]))
    results = [flight.run_check(con, check) for check in checks]

    assert [result.status for result in results] == ["ok", "failed", "failed", "failed"]
    assert results[0].row_count == 3 and results[0].age_hours == pytest.approx(2.0, abs=0.1)
    assert results[1].problems == ("newest row is 72.0 hours old, limit is 30",)
    assert results[2].problems == ("0 rows, expected at least 1", "no value in loaded_at")
    assert results[3].problems[0].startswith("query failed: Catalog Error")

    flight.record(con, '"main"', results)
    flight.record(con, '"main"', results)
    assert con.execute("SELECT count(*) FROM main.check_results").fetchone() == (8,)
    latest = con.execute("SELECT checked_table, status FROM main.latest_check_results ORDER BY 1").fetchall()
    assert latest == [
        ("src.main.empty", "failed"), ("src.main.fresh", "ok"), ("src.main.missing", "failed"),
        ("src.main.stale", "failed"),
    ]


@pytest.mark.parametrize(
    ("checks", "message"),
    [
        ("not json", "not valid JSON"),
        ("{}", "non-empty JSON array"),
        ('[{"table": "a.b"}]', "database.schema.table"),
        ('[{"table": "a.b.c; DROP TABLE x"}]', "unsafe identifier"),
        ('[{"table": "a.b.c", "timestamp_column": "t\\"; --"}]', "unsafe identifier"),
        ('[{"table": "a.b.c", "max_age_hours": 1}]', "without timestamp_column"),
    ],
)
def test_freshness_monitor_rejects_config_it_cannot_trust(checks: str, message: str) -> None:
    flight = load_flight("data-freshness-monitor")
    with pytest.raises(SystemExit, match=message):
        flight.parse_checks(checks)


def test_freshness_monitor_default_config_matches_the_manifest() -> None:
    flight = load_flight("data-freshness-monitor")
    (check,) = flight.parse_checks(flight.DEFAULT_CONFIG["checks"])
    assert check.name == "wikipedia_pageviews.main.pageviews_daily"
    assert (check.timestamp_column, check.max_age_hours, check.min_rows) == ("loaded_at_utc", 30.0, 1)


@pytest.mark.parametrize("example", ["pageviews-weekly-trends", "data-freshness-monitor", "pageviews-guide"])
def test_example_preview_plans_and_deploys_against_the_mock_account(
    starter: Path, md_cli: Cli, example: str,
) -> None:
    enable(starter, example)
    arguments = ("--root", str(starter), "--branch", "feature/x", "--blueprints", example)
    plan = md_cli.ok("plan", *arguments).stdout
    assert example in plan and "wikipedia-pageviews-ingest" in plan
    md_cli.ok("deploy", *arguments)
    md_cli.ok("verify", *arguments)
    md_cli.ok("cleanup", "--root", str(starter), "--branch", "feature/x")
