from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from md_blueprints.cli import main
from md_blueprints.guides import run_guides
from md_blueprints.init import run_init
from md_blueprints.scaffold import run_new


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def write_dbt(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "dbt_project.yml").write_text("name: warehouse\nmodel-paths: [transformations]\ntarget-path: generated\n")
    models = root / "transformations" / "revenue"
    models.mkdir(parents=True)
    (models / "orders.sql").write_text("select * from {{ source('billing', 'orders') }}\n")
    (models / "schema.yaml").write_text("""version: 2
models:
  - name: orders
    description: One row per completed order, excluding test accounts.
    config: {alias: fact_orders, schema: analytics, materialized: table, secret: NEVER_COPY}
    meta: {token: NEVER_COPY}
    columns:
      - name: customer_id
        description: Customer key.
        data_tests:
          - not_null
          - relationships:
              arguments: {to: "ref('customers')", field: id}
              config: {password: NEVER_COPY}
sources:
  - name: billing
    database: raw
    schema: billing
    tables:
      - name: orders
        identifier: order_events
        description: "{{ doc('order_events') }}"
semantic_models:
  - name: revenue
    model: ref('orders')
    measures:
      - name: net_revenue
        expr: amount - refunded_amount
""")
    (root / "profiles.yml").write_text("!!python/object/apply:INVALID NEVER_COPY")
    for folder in ("target", "dbt_packages", ".git", "generated"):
        (root / folder).mkdir()
        (root / folder / "private.yml").write_text("!!python/object/apply:INVALID NEVER_COPY")


@pytest.mark.parametrize("action", ["context", "init", "update"])
def test_discovery_is_read_only_and_preserves_existing_guide_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], action: str,
) -> None:
    run_init(tmp_path)
    guide = run_new(tmp_path, "guide", "repository-overview")
    (guide / "guide.md").write_text("# Curated context\nHandwritten rules and an edited legacy generated section.\n")
    (guide / ".guide-state.json").write_text("obsolete state is intentionally ignored")
    capsys.readouterr()
    before = snapshot(tmp_path)
    run_guides(tmp_path, action)
    output = capsys.readouterr().out
    assert snapshot(tmp_path) == before
    assert "Claude, ChatGPT, or Codex" in output
    assert "wikipedia-pageviews-ingest.pageviews" in output
    assert "flights/wikipedia-pageviews-ingest/src/flight.py" in output
    assert "guides/repository-overview/guide.md" in output
    assert "examples/ncs-field-recovery" not in output
    assert "No files or live resources were changed" in output


def test_external_dbt_yaml_enriches_blueprints_without_copying_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "blueprints"
    run_init(repo)
    dbt = tmp_path / "warehouse dbt"
    write_dbt(dbt)
    before = snapshot(tmp_path)
    capsys.readouterr()
    assert main(["guides", "update", "--root", str(repo), "--dbt", str(dbt)]) == 0
    output = capsys.readouterr().out
    assert "One row per completed order" in output
    assert "fact_orders" in output and "order_events" in output
    assert "ref('customers')" in output and "field: id" in output
    assert "net_revenue" in output
    assert "transformations/revenue/orders.sql" in output
    excerpt = yaml.safe_load(output.rsplit("```yaml\n", 1)[1].split("```", 1)[0])
    assert excerpt["sources"][0]["tables"][0]["description"] == "{{ doc('order_events') }}"
    assert "Jinja is unresolved" in output
    assert "NEVER_COPY" not in output
    assert "private.yml" not in output
    assert snapshot(tmp_path) == before


def test_standalone_dbt_and_project_file_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dbt = tmp_path / "dbt"
    write_dbt(dbt)
    before = snapshot(dbt)
    for args in (["--root", str(dbt)], ["--root", str(dbt), "--dbt", str(dbt / "dbt_project.yml")]):
        assert main(["guides", *args]) == 0
        output = capsys.readouterr().out
        assert "No motherduck.yml" in output
        assert "One row per completed order" in output
        assert "private.yml" not in output
    assert snapshot(dbt) == before


def test_plain_sql_repository_needs_no_blueprints_or_native_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "query.sql").write_text("select 1\n")
    before = snapshot(tmp_path)
    assert main(["guides", "--root", str(tmp_path), "--dry-run"]) == 0
    assert "query.sql" in capsys.readouterr().out
    assert snapshot(tmp_path) == before


def test_large_dbt_context_is_explicitly_shortened(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from md_blueprints.guides import MAX_EXCERPT

    (tmp_path / "dbt_project.yml").write_text("name: large\n")
    (tmp_path / "a.yml").write_text(yaml.safe_dump({"models": [{"name": "large", "description": "x" * (MAX_EXCERPT + 1)}]}))
    (tmp_path / "b.yaml").write_text("models: [{name: next_model}]\n")
    assert main(["guides", "--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Excerpt shortened" in output
    assert "YAML excerpt limit reached" in output
    assert "b.yaml" in output
    assert "next_model" not in output


def test_dbt_symlinks_are_not_followed_and_invalid_yaml_is_reported_without_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    write_dbt(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.yml").write_text("models: [{name: DO_NOT_READ}]")
    (repo / "linked").symlink_to(outside, target_is_directory=True)
    (repo / "linked.yml").symlink_to(outside / "private.yml")
    assert main(["guides", "--root", str(repo)]) == 0
    output = capsys.readouterr().out
    assert "DO_NOT_READ" not in output and "linked.yml" not in output
    (repo / "broken.yml").write_text("models: [SECRET_PARSE_ERROR\n")
    before = snapshot(repo)
    assert main(["guides", "--root", str(repo)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Cannot parse YAML" in captured.err
    assert "SECRET_PARSE_ERROR" not in captured.err
    assert snapshot(repo) == before


@pytest.mark.parametrize("args", [["guides", "delete"], ["guides", "init", "unexpected"], ["guides", "--dbt", "/missing-dbt-project"], ["guides", "--dbt", ""], ["validate", "--dbt", "."]])
def test_invalid_requests_fail(args: list[str], tmp_path: Path) -> None:
    assert main([*args, "--root", str(tmp_path)]) == 1
