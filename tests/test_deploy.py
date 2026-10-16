from __future__ import annotations

import copy
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from md_blueprints import deploy as deploy_module
from md_blueprints.deploy import OTHER_BRANCH_PREVIEW, Deployer, PlanRecord, quote_ident
from md_blueprints.project import CommandError, Project, RenderedBlueprint, branch_slug
from md_blueprints.schema import ValidationError


FIXTURES = Path(__file__).parent / "fixtures"


def test_cleanup_plan_refuses_share_without_branch_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: [])
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/prod/123")
    blueprint = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={
            "prod": {
                "name": "prod_share",
                "database": "prod_database",
                "cleanup": True,
                "dropDatabase": True,
            }
        },
        flights={},
        dives={},
        contexts={},
    )

    records = deployer._build_cleanup_plan([blueprint], "feature_branch")

    assert [record.type for record in records] == ["share"]
    assert records[0].action == "error"
    assert "refusing to drop preview share without branch slug feature_branch" in records[0].notes
    with pytest.raises(ValidationError, match="Plan contains errors"):
        deployer.ensure_plan_succeeds(records)


def test_cleanup_plan_refuses_database_without_branch_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: [])
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/preview/123")
    blueprint = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={
            "prod": {
                "name": "safe_feature_branch_share",
                "database": "prod_database",
                "cleanup": True,
                "dropDatabase": True,
            }
        },
        flights={},
        dives={},
        contexts={},
    )

    records = deployer._build_cleanup_plan([blueprint], "feature_branch")

    assert [(record.type, record.action) for record in records] == [
        ("share", "drop_share"),
        ("database", "error"),
    ]
    assert "refusing to drop preview database without branch slug feature_branch" in records[1].notes
    with pytest.raises(ValidationError, match="Plan contains errors"):
        deployer.ensure_plan_succeeds(records)


def test_cleanup_plan_refuses_flight_and_dive_names_that_match_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_dive_ids", lambda title: pytest.fail("unsafe Dive lookup"))
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: pytest.fail("unsafe Flight lookup"))
    preview = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={},
        flights={"loader": {"name": "production-loader"}},
        dives={"dashboard": {"title": "Production Dashboard"}},
        contexts={},
    )
    production = RenderedBlueprint(
        name="ops",
        title="Ops",
        description="",
        shares={},
        flights={"loader": {"name": "production-loader"}},
        dives={"dashboard": {"title": "Production Dashboard"}},
        contexts={},
    )

    records = deployer._build_cleanup_plan(
        [preview],
        "prod",
        branch="prod",
        production={"ops": production},
    )

    assert [(record.type, record.action) for record in records] == [
        ("dive", "error"),
        ("flight", "error"),
    ]
    assert all("matches production" in record.notes for record in records)
    with pytest.raises(ValidationError, match="Plan contains errors"):
        deployer.ensure_plan_succeeds(records)


def test_cleanup_plan_accepts_validation_only_production_guide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_guide_ids", lambda title, topic: ["guide-id"])
    preview = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={
            "runbook": {
                "title": "Runbook:feature/docs (Preview)",
                "sourcePath": "runbook.md",
                "deploy": True,
            }
        },
    )
    production = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={"runbook": {"sourcePath": "runbook.md", "deploy": False}},
    )

    records = deployer._build_cleanup_plan(
        [preview],
        "feature_docs",
        branch="feature/docs",
        production={"knowledge": production},
    )

    assert [(record.type, record.action) for record in records] == [("guide", "delete")]


@pytest.mark.parametrize(("topic", "action"), [("docs_feature_docs", "delete"), ("docs", "error")])
def test_cleanup_plan_accepts_guide_scoped_by_topic(
    monkeypatch: pytest.MonkeyPatch, topic: str, action: str,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_list_guide_ids", lambda title, topic: ["guide-id"])

    def guides(topic: str) -> RenderedBlueprint:
        return RenderedBlueprint(
            name="knowledge", title="Knowledge", description="", shares={}, flights={}, dives={}, contexts={},
            guides={"runbook": {"title": "Runbook", "topic": topic, "sourcePath": "runbook.md", "deploy": True}},
        )

    records = deployer._build_cleanup_plan(
        [guides(topic)], "feature_docs", branch="feature/docs", production={"knowledge": guides("docs")},
    )

    assert [(record.type, record.action) for record in records] == [("guide", action)]


def _access_blueprint(members: list[str], grant_users: list[str]) -> RenderedBlueprint:
    return RenderedBlueprint(
        name="access",
        title="Access",
        description="",
        shares={"finance": {"name": "finance", "database": "finance", "grants": {"users": grant_users}}},
        flights={},
        dives={},
        contexts={},
        roles={"team": {"name": "finance-team", "members": members, "deploy": True}},
    )


def test_plan_rejects_members_and_grantees_missing_from_the_organization(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    deployer.sql_env = {"motherduck_token": "token"}
    monkeypatch.setattr(deployer, "_live_role_names", lambda: {"finance-team"})
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/example/id")
    monkeypatch.setattr(deploy_module, "list_org_users", lambda token: {"Alice": False, "bob": True})

    records = deployer._build_deploy_plan([_access_blueprint(["alice", "bob", "alcie"], ["ALICE", "carol"])])

    role_record = next(record for record in records if record.type == "role")
    share_record = next(record for record in records if record.type == "share")
    assert role_record.action == "error"
    assert role_record.notes == "member(s) are not users in this organization: alcie"
    assert share_record.action == "error"
    assert share_record.notes == "grant user(s) are not users in this organization: carol"
    assert "deprovisioned user(s) are still declared as members or share grantees: bob" in capsys.readouterr().err


@pytest.mark.parametrize(("name", "problem"), [
    ("finance", None), ("data_team_2", None), ("Équipe", None), ("a" * 255, None),
    ("finance-team", "may contain only letters, digits, and underscores"),
    ("_analysts", "must start with a letter"), ("27", "must start with a letter"),
    ("", "must be 1 to 255 characters long"), ("a" * 256, "must be 1 to 255 characters long"),
])
def test_role_name_problem_matches_motherduck_rules(name: str, problem: str | None) -> None:
    assert deploy_module.role_name_problem(name) == problem


def test_plan_skips_username_check_when_users_cannot_be_listed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    deployer.sql_env = {"motherduck_token": "token"}
    monkeypatch.setattr(deployer, "_live_role_names", lambda: {"finance-team"})
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/example/id")

    def forbidden(token: str) -> dict[str, bool]:
        raise urllib.error.HTTPError("https://api.motherduck.com/v1/users", 403, "Forbidden", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(deploy_module, "list_org_users", forbidden)

    records = deployer._build_deploy_plan([_access_blueprint(["alice"], ["carol"])])

    assert {record.type: record.action for record in records} == {"role": "update", "share": "update"}
    assert "could not list organization users (HTTP Error 403: Forbidden)" in capsys.readouterr().err


def test_plan_lists_users_only_when_usernames_are_declared(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    deployer.sql_env = {"motherduck_token": "token"}
    monkeypatch.setattr(deployer, "_live_role_names", lambda: {"finance-team"})
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: "md:_share/example/id")

    def unexpected(token: str) -> dict[str, bool]:
        raise AssertionError("users were listed without declared usernames")

    monkeypatch.setattr(deploy_module, "list_org_users", unexpected)

    deployer._build_deploy_plan([_access_blueprint([], [])])


def test_list_org_users_follows_page_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        None: {"users": [{"username": "alice", "is_deprovisioned": False}], "next_page_token": "p2"},
        "p2": {"users": [{"username": "bob", "is_deprovisioned": True}], "next_page_token": None},
    }
    requests: list[urllib.request.Request] = []

    class Response(io.BytesIO):
        def __enter__(self) -> "Response":
            return self

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        requests.append(request)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        return Response(json.dumps(pages[query.get("page_token", [None])[0]]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("motherduck_host", raising=False)
    monkeypatch.setenv("MOTHERDUCK_HOST", "api.example-region.motherduck.com")

    assert deploy_module.list_org_users("secret") == {"alice": False, "bob": True}
    assert [request.full_url for request in requests] == [
        "https://api.example-region.motherduck.com/v1/users?limit=1000",
        "https://api.example-region.motherduck.com/v1/users?limit=1000&page_token=p2",
    ]
    assert requests[0].get_header("Authorization") == "Bearer secret"


def test_authoritative_role_keeps_members_that_differ_only_in_case(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    def rows(statement: str) -> list[tuple[object, ...]]:
        if "SHOW ROLES" in statement:
            return []
        return [("alice@example.com", "alice@example.com", False, None)]

    monkeypatch.setattr(deployer, "_query_rows", rows)
    deployer._deploy_role(
        {"name": "finance", "includedRoles": [], "members": ["Alice@Example.com"], "mode": "authoritative"},
        PlanRecord("access", "role", "finance", "finance", "update", True, "finance"),
    )

    assert calls == ['CREATE ROLE IF NOT EXISTS "finance";']


@pytest.mark.parametrize(("current", "desired", "blocked"), [
    ("ready", "endorsed", True),
    (None, "endorsed", True),
    ("endorsed", "endorsed", False),
    ("draft", "ready", False),
])
def test_endorsing_a_dive_requires_admin_before_any_write(
    monkeypatch: pytest.MonkeyPatch, current: str | None, desired: str, blocked: bool,
) -> None:
    project = Project(FIXTURES / "simple")
    deployer = Deployer(project)
    record = PlanRecord(
        "simple-dive", "dive", "dashboard", "Dashboard", "update" if current else "create", bool(current),
        "dive-id" if current else None, current_status=current, desired_status=desired,
    )
    monkeypatch.setattr(deployer, "_query_rows", lambda statement: [("builder",)])
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda target, operation: None)
    monkeypatch.setattr(deployer, "_preflight_rbac", lambda rendered: None)
    monkeypatch.setattr(deployer, "_preflight_flight_instance_types", lambda rendered: None)
    monkeypatch.setattr(deployer, "_build_deploy_plan", lambda rendered: [record])
    writes: list[str] = []

    def deploy_blueprint(*args: object) -> None:
        writes.append("deploy")

    monkeypatch.setattr(deployer, "_deploy_blueprint", deploy_blueprint)

    if blocked:
        with pytest.raises(ValidationError, match="requires the admin role.*endorses Dive Dashboard"):
            deployer.deploy(target="prod", branch=None, names=None, verify=False)
        assert writes == []
    else:
        deployer.deploy(target="prod", branch=None, names=None, verify=False)
        assert writes


def test_guide_deploy_uses_version_metadata_and_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""
    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [
            (
                "old content",
                "old-sha",
                "[]",
                "[]",
                "Old title",
                "old-topic",
                "Old description",
                "user",
            )
        ],
    )
    guide_source = tmp_path / "guide.md"
    guide_source.write_text("# Revenue\n", encoding="utf-8")
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
    )

    deployer._deploy_guide(
        blueprint,
        {
            "title": "Revenue definitions",
            "topic": "finance/revenue",
            "description": "Canonical metrics",
            "sourcePath": str(guide_source),
            "access": "organization",
            "references": [],
            "changeComment": "sync definitions",
            "externalId": "abc123",
        },
        "prod",
        PlanRecord("knowledge", "guide", "revenue", "Revenue definitions", "update", True, "guide-id"),
    )

    statement = calls[0]
    assert "MD_UPDATE_GUIDE" in statement
    assert "MD_UPDATE_GUIDE_METADATA" in statement
    assert "MD_SET_GUIDE_ACCESS" in statement
    assert "'sync definitions'" in statement
    assert "'abc123'" in statement


def test_guide_deploy_does_not_append_unchanged_reference_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)
    guide_id = "00000000-0000-0000-0000-000000000042"
    current_references = (
        '[{"type":"guide","url":null,"schema":null,"table":null,"column":null,'
        f'"view":null,"macro":null,"guide_id":"{guide_id}","dive_id":null,'
        '"flight_id":null,"description":null}]'
    )
    desired_references = (
        '[{"type":"guide","url":null,"schema":null,"table":null,"column":null,'
        '"view":null,"macro":null,"uuid":"'
        + guide_id
        + '","description":null}]'
    )
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [
            (
                "# Revenue\n",
                "abc123",
                current_references,
                desired_references,
                "Revenue definitions",
                None,
                None,
                "user",
            )
        ],
    )
    guide_source = tmp_path / "guide.md"
    guide_source.write_text("# Revenue\n", encoding="utf-8")
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
    )

    deployer._deploy_guide(
        blueprint,
        {
            "title": "Revenue definitions",
            "sourcePath": str(guide_source),
            "references": [{"type": "guide", "uuid": guide_id}],
            "externalId": "abc123",
        },
        "prod",
        PlanRecord("knowledge", "guide", "revenue", "Revenue definitions", "update", True, "guide-id"),
    )

    assert calls == []


def test_guide_deploy_appends_version_when_references_are_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []

    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)
    monkeypatch.setattr(
        deployer,
        "_query_rows",
        lambda statement: [
            (
                "# Revenue\n",
                "abc123",
                '[{"type":"catalog","url":"md:analytics"}]',
                "[]",
                "Revenue definitions",
                None,
                None,
                "user",
            )
        ],
    )
    guide_source = tmp_path / "guide.md"
    guide_source.write_text("# Revenue\n", encoding="utf-8")
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
    )

    deployer._deploy_guide(
        blueprint,
        {
            "title": "Revenue definitions",
            "sourcePath": str(guide_source),
            "references": [],
            "externalId": "abc123",
        },
        "prod",
        PlanRecord("knowledge", "guide", "revenue", "Revenue definitions", "update", True, "guide-id"),
    )

    assert "FROM MD_UPDATE_GUIDE(" in calls[0]
    assert "MD_UPDATE_GUIDE_METADATA" not in calls[0]
    assert "MD_SET_GUIDE_ACCESS" not in calls[0]


def test_guide_resource_reference_uses_explicit_managed_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    guide_id = "00000000-0000-0000-0000-000000000042"
    blueprint = RenderedBlueprint(
        name="knowledge",
        title="Knowledge",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={
            "canonical": {
                "id": guide_id,
                "sourcePath": "guide.md",
                "deploy": False,
            }
        },
    )
    deployer.rendered_by_name = {"knowledge": blueprint}
    monkeypatch.setattr(
        deployer,
        "_get_guide_rows_by_id",
        lambda resource_id: [(resource_id,)],
    )

    references_sql = deployer._guide_references_sql(
        blueprint,
        [{"type": "guide", "resource": "canonical"}],
    )

    assert f"'{guide_id}'::UUID" in references_sql


def test_guide_plan_rejects_missing_unselected_reference_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    producer = RenderedBlueprint(
        name="producer",
        title="Producer",
        description="",
        shares={},
        flights={"loader": {"name": "historical-loader"}},
        dives={},
        contexts={},
    )
    consumer = RenderedBlueprint(
        name="consumer",
        title="Consumer",
        description="",
        shares={},
        flights={},
        dives={},
        contexts={},
        guides={
            "runbook": {
                "title": "Runbook",
                "sourcePath": "runbook.md",
                "deploy": True,
                "references": [
                    {
                        "type": "flight",
                        "blueprint": "producer",
                        "resource": "loader",
                    }
                ],
            }
        },
    )
    deployer.rendered_by_name = {"producer": producer}
    monkeypatch.setattr(deployer, "_list_flight_ids", lambda name: [])

    records = deployer._build_deploy_plan([consumer])

    guide_record = next(record for record in records if record.type == "guide")
    assert guide_record.action == "error"
    assert "expected exactly one" in guide_record.notes


def test_sql_identifier_quoting_rejects_unsafe_database_names() -> None:
    assert quote_ident("preview_database_1") == '"preview_database_1"'

    with pytest.raises(ValidationError, match="Unsafe SQL identifier"):
        quote_ident("prod; DROP DATABASE prod")


def test_plan_formatter_escapes_markdown_cells() -> None:
    from md_blueprints.deploy import PlanFormatter

    output = PlanFormatter.format(
        [
            PlanRecord(
                blueprint="bp|name",
                type="flight",
                key="loader",
                name="name with\nnewline",
                action="create",
                exists=False,
                id=None,
                notes="safe",
            )
        ],
        title="Plan",
    )

    assert "bp\\|name" in output
    assert "name with newline" in output



@pytest.mark.parametrize('status', ['SUCCEEDED', 'RUN_STATUS_SUCCEEDED'])
def test_wait_tracks_the_submitted_run_not_the_latest(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    queries: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        queries.append(statement)
        assert 'MD_LIST_FLIGHT_RUNS' in statement
        return [(43, 'FAILED'), (42, status)]

    monkeypatch.setattr(deployer, '_query_rows', rows)
    deployer._wait_for_flight_run_success('00000000-0000-0000-0000-000000000001', 42)
    assert len(queries) == 1


@pytest.mark.parametrize('status', ['FAILED', 'CANCELLED', 'RUN_STATUS_FAILED', 'RUN_STATUS_CANCELLED'])
@pytest.mark.parametrize('record', ['{"line":"test log","line_number":1}', '{"logs":"test log"}'])
def test_wait_recognizes_current_and_legacy_failure_statuses(
    monkeypatch: pytest.MonkeyPatch, status: str, record: str,
) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    queries: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        queries.append(statement)
        if 'MD_GET_FLIGHT_LOGS' in statement:
            assert 'run_number := 42' in statement
            return [(record,)]
        return [(43, 'SUCCEEDED'), (42, status)]

    monkeypatch.setattr(deployer, '_query_rows', rows)
    with pytest.raises(CommandError, match='Flight run 42 ended with .*test log'):
        deployer._wait_for_flight_run_success('00000000-0000-0000-0000-000000000001', 42)
    assert len(queries) == 2


def test_wait_follows_pagination_for_exact_run(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    queries: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        queries.append(statement)
        if '\"offset\" := 0' in statement:
            return [(number, 'SUCCEEDED') for number in range(200, 100, -1)]
        assert '\"offset\" := 100' in statement
        return [(42, 'FAILED')]

    monkeypatch.setattr(deployer, '_query_rows', rows)
    assert deployer._flight_run_status('00000000-0000-0000-0000-000000000001', 42) == 'FAILED'
    assert len(queries) == 2


def test_log_read_failure_does_not_hide_failed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / 'complex'))
    monkeypatch.setattr(deployer, '_flight_run_status', lambda *args: 'FAILED')

    def rows(statement: str) -> list[tuple[object, ...]]:
        raise CommandError('log service unavailable')

    monkeypatch.setattr(deployer, '_query_rows', rows)
    with pytest.raises(CommandError, match='Flight run 42 ended with FAILED.*Logs unavailable'):
        deployer._wait_for_flight_run_success('00000000-0000-0000-0000-000000000001', 42)


def test_single_line_required_databases_strip_matches_legacy_regex() -> None:
    import re

    from md_blueprints.deploy import strip_required_databases_export

    sources = [
        'export const REQUIRED_DATABASES = [{ alias: "a", path: "md:a" }];\nexport default 1;\n',
        'export const REQUIRED_DATABASES = [] // local\nexport default 1;\n',
        'export default 1;\nexport const REQUIRED_DATABASES = [];',
        '  export const REQUIRED_DATABASES = [];\nexport default 1;\n',
    ]
    for source in sources:
        legacy = re.sub(r"export const REQUIRED_DATABASES[^\n]*(?:\n|$)", "", source)
        assert strip_required_databases_export(source) == legacy


def test_multi_line_required_databases_export_is_removed_whole() -> None:
    from md_blueprints.deploy import strip_required_databases_export

    component = "export default function Dive() { return null; }\n"
    source = (
        "import { useSQLQuery } from '@motherduck/react-sql-query';\n"
        "export const REQUIRED_DATABASES = [\n"
        "  // mounted for local preview\n"
        "  { type: 'share', path: 'md:_share/a/1', alias: 'a' },\n"
        "] as const;\n" + component
    )

    assert strip_required_databases_export(source) == (
        "import { useSQLQuery } from '@motherduck/react-sql-query';\n" + component
    )


def test_typed_multi_line_required_databases_export_is_removed_whole() -> None:
    from md_blueprints.deploy import strip_required_databases_export

    component = "export default function Dive() { return null; }\n"
    source = (
        "export const REQUIRED_DATABASES: Array<{ type: string; path: string; alias: string }> = [\n"
        "  { type: 'share', path: 'md:_share/a/1', alias: 'a' },\n"
        "];\n" + component
    )

    assert strip_required_databases_export(source) == component


def test_non_static_multi_line_required_databases_export_is_rejected() -> None:
    from md_blueprints.deploy import strip_required_databases_export

    source = "export const REQUIRED_DATABASES = [\n  { alias: ALIAS },\n];\nexport default 1;\n"

    with pytest.raises(ValidationError, match="REQUIRED_DATABASES must be a static array"):
        strip_required_databases_export(source)
    # Single-line exports keep the legacy line removal, including brackets in strings and comments.
    for line in (
        'export const REQUIRED_DATABASES = [{url: "md:x", alias: "a"}]; // local preview only (see README',
        'export const REQUIRED_DATABASES = ["a", "(b"].map((x) => x);',
    ):
        assert strip_required_databases_export(line + "\nexport default 1;\n") == "export default 1;\n"
    multi = "export const REQUIRED_DATABASES = [\n  { alias: 'a' },\n]; // local preview\nexport default 1;\n"
    assert strip_required_databases_export(multi) == "export default 1;\n"
    assert strip_required_databases_export("export const REQUIRED_DATABASES = load();\nexport default 1;\n") == (
        "export default 1;\n"
    )


def test_flight_wait_follows_max_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLIGHT_RUN_POLL_ATTEMPTS", raising=False)

    assert Deployer._flight_run_poll_attempts(10, None) == 60
    assert Deployer._flight_run_poll_attempts(10, 60) == 60
    assert Deployer._flight_run_poll_attempts(10, 3600) == 372
    monkeypatch.setenv("FLIGHT_RUN_POLL_ATTEMPTS", "3")
    assert Deployer._flight_run_poll_attempts(10, 3600) == 3


def test_flight_wait_timeout_explains_state_and_next_step(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setenv("FLIGHT_RUN_POLL_ATTEMPTS", "2")
    monkeypatch.setenv("FLIGHT_RUN_POLL_SLEEP_SECONDS", "0")
    monkeypatch.setattr(deployer, "_flight_run_status", lambda *args: "RUNNING")

    with pytest.raises(CommandError) as exc:
        deployer._wait_for_flight_run_success(
            "00000000-0000-0000-0000-000000000001", 7, max_runtime_sec=30, name="loader",
        )

    message = str(exc.value)
    assert "Flight 'loader'" in message
    assert "Already applied:" in message
    assert "was not cancelled" in message
    assert "Next:" in message
    assert "maxRuntimeSec" in message


def test_cleanup_drops_database_names_that_need_quoting(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    calls: list[str] = []
    def fake_sql(statement: str) -> str:
        calls.append(statement)
        return ""

    monkeypatch.setattr(deployer, "_sql", fake_sql)

    deployer._apply_cleanup_plan(
        [PlanRecord("ops", "database", "data", 'my-db_feature_x "v2"', "drop_database", True, None)]
    )

    assert calls == ['DROP DATABASE IF EXISTS "my-db_feature_x ""v2""";']


def test_cleanup_requires_branch_slug_as_whole_token(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: pytest.fail("unsafe share lookup"))
    blueprint = RenderedBlueprint(
        name="ops", title="Ops", description="",
        shares={"data": {"name": "domain_data", "database": "domain_data"}},
        flights={}, dives={}, contexts={},
    )

    records = deployer._build_cleanup_plan([blueprint], "main", branch="main")

    assert [(record.type, record.action) for record in records] == [("share", "error")]
    assert "without branch slug main" in records[0].notes


def test_cleanup_compares_against_every_stable_target(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: pytest.fail("unsafe share lookup"))

    def shares(name: str) -> RenderedBlueprint:
        return RenderedBlueprint(
            name="ops", title="Ops", description="",
            shares={"data": {"name": name, "database": name}},
            flights={}, dives={}, contexts={},
        )

    records = deployer._build_cleanup_plan(
        [shares("data_feature_x")],
        "feature_x",
        branch="feature/x",
        production={"ops": shares("data_staging")},
        stable_target="staging",
        stable_renders={"staging": {"ops": shares("data_staging")}, "prod": {"ops": shares("data_feature_x")}},
    )

    assert records[0].action == "error"
    assert "matches production: data_feature_x" in records[0].notes


def test_cleanup_plan_renders_all_stable_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project(FIXTURES / "simple")
    targets = project.manifest["targets"]
    assert isinstance(targets, dict)
    targets["staging"] = copy.deepcopy(targets["prod"])
    deployer = Deployer(project)
    captured: dict[str, object] = {}
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda target, operation: None)
    monkeypatch.setattr(
        deployer, "_build_cleanup_plan", lambda rendered, slug, **kwargs: captured.update(kwargs) or [],
    )

    deployer.cleanup_plan(target="preview", branch="feature/test", names=None)

    stable_renders = captured["stable_renders"]
    assert isinstance(stable_renders, dict)
    assert set(stable_renders) == {"staging", "prod", OTHER_BRANCH_PREVIEW}


def test_cleanup_refuses_fixed_names_that_contain_the_branch_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "motherduck.yml").write_text(
        "schemaVersion: 1\nrepository: {name: fixed}\ninclude: [projects/*/blueprint.yml]\n"
        "targets:\n  preview:\n    mode: preview\n    policies: {cleanup: true}\n  prod: {mode: production}\n",
        encoding="utf-8",
    )
    package = tmp_path / "projects" / "events"
    package.mkdir(parents=True)
    (package / "blueprint.yml").write_text(
        "schemaVersion: 1\nname: events\ntitle: Events\nresources:\n  shares:\n    data:\n"
        "      name: events\n      database: events\n"
        "      targets:\n        preview: {name: events_dev, database: events_dev, dropDatabase: true}\n",
        encoding="utf-8",
    )
    deployer = Deployer(Project(tmp_path))
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda target, operation: None)
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: pytest.fail("unsafe share lookup"))

    records = deployer.cleanup_plan(target="preview", branch="dev", names=None)

    # The refused share also stops its database from being dropped.
    assert [(record.type, record.action) for record in records] == [("share", "error")]
    assert "does not change with the branch, so other previews share it: events_dev" in records[0].notes


def test_context_plan_note_is_a_deprecation() -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    blueprint = RenderedBlueprint(
        name="notes", title="Notes", description="", shares={}, flights={}, dives={},
        contexts={"notes": {"sourcePath": "notes.md", "deploy": False}},
    )

    record = deployer._build_deploy_plan([blueprint])[0]

    assert record.action == "validated_only"
    assert "deprecated" in record.notes and "resources.guides" in record.notes
    assert "not available yet" not in record.notes


def test_legacy_cleanup_pass_drops_unsafe_and_missing_records() -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    current = [PlanRecord("ops", "flight", "loader", "loader_new", "delete", True, "a")]
    legacy = [
        PlanRecord("ops", "flight", "loader", "loader_new", "delete", True, "a"),
        PlanRecord("ops", "share", "data", "data_legacy", "error", None, None, "matches production"),
        PlanRecord("ops", "share", "data", "data_legacy", "missing", False, None),
    ]

    assert deployer._legacy_cleanup_records(current, legacy) == []


def test_name_lookups_read_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr("md_blueprints.deploy.LIST_PAGE_SIZE", 2)
    catalog: dict[str, list[tuple[object, ...]]] = {
        "MD_LIST_FLIGHTS": [("f1", "other"), ("f2", "other"), ("f3", "loader")],
        "MD_LIST_DIVES": [("d1", "Other", "draft"), ("d2", "Sales", None), ("d3", "Sales", "ENDORSED")],
        "MD_LIST_GUIDES": [("g1", "Notes", None), ("g2", "Notes", "finance"), ("g3", "Notes", "")],
    }
    statements: list[str] = []

    def rows(statement: str) -> list[tuple[object, ...]]:
        statements.append(statement)
        function = statement.split(" FROM ")[1].split("(")[0]
        offset = int(statement.split('"offset" := ')[1].split("::")[0])
        return catalog[function][offset:offset + 2]

    monkeypatch.setattr(deployer, "_query_rows", rows)

    assert deployer._list_flight_ids("loader") == ["f3"]
    assert deployer._list_dive_ids("Sales") == ["d2", "d3"]
    assert deployer._list_dive_states("Sales") == [("d2", None), ("d3", "endorsed")]
    assert deployer._list_guide_ids("Notes", "") == ["g1", "g3"]
    assert deployer._list_guide_ids("Notes", "finance") == ["g2"]
    assert statements[:3] == [
        'SELECT flight_id, flight_name FROM MD_LIST_FLIGHTS("limit" := 2::UINTEGER, "offset" := 0::UINTEGER)',
        'SELECT flight_id, flight_name FROM MD_LIST_FLIGHTS("limit" := 2::UINTEGER, "offset" := 2::UINTEGER)',
        'SELECT flight_id, flight_name FROM MD_LIST_FLIGHTS("limit" := 2::UINTEGER, "offset" := 3::UINTEGER)',
    ]


def test_name_lookup_rejects_pages_that_repeat_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    # A server that ignores "offset" would otherwise loop forever.
    monkeypatch.setattr(deployer, "_query_rows", lambda statement: [("f1", "loader")])

    with pytest.raises(CommandError, match="repeated an ID"):
        deployer._list_flight_ids("loader")


def test_cleanup_for_non_ascii_branch_leaves_the_shared_legacy_preview_slug_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "motherduck.yml").write_text(
        "schemaVersion: 1\nrepository: {name: slugs}\ninclude: [projects/*/blueprint.yml]\n"
        "targets:\n  preview:\n    mode: preview\n    policies: {cleanup: true, requireBranchSlugInDataResources: true}\n"
        "  prod: {mode: production}\n",
        encoding="utf-8",
    )
    package = tmp_path / "projects" / "events"
    package.mkdir(parents=True)
    (package / "blueprint.yml").write_text(
        "schemaVersion: 1\nname: events\ntitle: Events\nresources:\n  shares:\n    data:\n"
        "      name: events\n      database: events\n      targets:\n        preview:\n"
        "          {name: 'events_${target.branch_slug}', database: 'events_${target.branch_slug}', dropDatabase: true}\n",
        encoding="utf-8",
    )
    deployer = Deployer(Project(tmp_path))
    monkeypatch.setattr(deployer, "_prepare_live_command", lambda target, operation: None)
    monkeypatch.setattr(deployer, "_find_share_url", lambda name: f"md:_share/{name}/1")
    monkeypatch.setattr(deployer, "_database_exists", lambda name: True)

    records = deployer.cleanup_plan(target="preview", branch="日本", names=None)

    assert {record.name for record in records} == {f"events_{branch_slug('日本')}"}


def test_preview_dive_row_escapes_pipes_in_titles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    deployer = Deployer(Project(FIXTURES / "simple"))
    source = tmp_path / "dive.tsx"
    source.write_text("export default function Dive() { return null; }\n", encoding="utf-8")
    monkeypatch.setattr(deployer, "_sql", lambda statement: "")
    title = "Ops | Revenue:feat-x (Preview)"
    dive: dict[str, object] = {"title": title, "sourcePath": str(source), "requiredResources": [], "status": "draft"}
    plan = PlanRecord("ops", "dive", "dashboard", title, "update", True, "dive-id", desired_status="draft")

    row = deployer._deploy_dive(dive, {}, {}, "preview", plan)

    assert row == r"| Ops \| Revenue:feat-x (Preview) | draft | [Open Dive](https://app.motherduck.com/dives/dive-id) |"


@pytest.mark.parametrize(("pattern", "parts"), [
    ("reporting.*, finance.salaries", ["reporting.*", "finance.salaries"]),
    ('reporting."a,b", main.t', ['reporting."a,b"', "main.t"]),
    (" , ,", []),
    ("", []),
])
def test_split_include_pattern_matches_motherduck(pattern: str, parts: list[str]) -> None:
    assert deploy_module.split_include_pattern(pattern) == parts


@pytest.mark.parametrize(("declared", "live", "action"), [
    (None, None, "present"),
    ([], [], "present"),
    ([], None, "update"),
    (["reporting.*"], ["reporting.*"], "present"),
    (['reporting."a,b"'], ['reporting."a,b"'], "present"),
    (["reporting.*"], None, "update"),
])
def test_share_plan_compares_the_live_include_pattern(
    monkeypatch: pytest.MonkeyPatch, declared: list[str] | None, live: list[str] | None, action: str,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_live_include_pattern", lambda name: live)
    assert deployer._managed_share_plan({"name": "events", "includePattern": declared})[0] == action


def test_share_plan_keeps_the_authoritative_warning_when_state_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))

    def unreadable(name: str) -> tuple[set[str], set[str]]:
        raise CommandError("permission denied")

    monkeypatch.setattr(deployer, "_current_share_grantees", unreadable)
    action, notes = deployer._managed_share_plan({"name": "events", "grants": {"roles": [], "mode": "authoritative"}})
    assert action == "update"
    assert "current state could not be read at plan time" in notes
    assert deploy_module.AUTHORITATIVE_NOTE in notes


def test_access_token_check_treats_an_empty_list_as_missing_and_an_unreadable_one_as_unknown(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    deployer = Deployer(Project(FIXTURES / "complex"))
    monkeypatch.setattr(deployer, "_query_rows", lambda statement: [])
    assert "is not an access token of the deployment identity" in str(deployer._access_token_problem("ci", "a.b"))

    deployer = Deployer(Project(FIXTURES / "complex"))

    def unreadable(statement: str) -> list[tuple[object, ...]]:
        raise CommandError("md_access_tokens failed")

    monkeypatch.setattr(deployer, "_query_rows", unreadable)
    assert deployer._access_token_problem("ci", "a.b") is None
    assert "skipping the accessTokenName check" in capsys.readouterr().err


def test_python_backend_reuses_one_connection_and_reconnects_after_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types

    class FakeError(Exception):
        pass

    connects: list[object] = []

    class Connection:
        closed = False

        def execute(self, statement: str) -> "Connection":
            if statement == "fail":
                raise FakeError("boom")
            return self

        def fetchall(self) -> list[tuple[object, ...]]:
            return [(1,)]

        def close(self) -> None:
            self.closed = True

    def connect(database: str, *, config: dict[str, object]) -> Connection:
        connection = Connection()
        connects.append(connection)
        return connection

    monkeypatch.setitem(sys.modules, "duckdb", types.SimpleNamespace(connect=connect, Error=FakeError))
    monkeypatch.setattr(deploy_module, "sql_backend", lambda: "duckdb")
    deployer = Deployer(Project(FIXTURES / "complex"))
    deployer.sql_env = {"motherduck_token": "token"}

    assert deployer._query_rows("SELECT 1") == [(1,)]
    assert deployer._query_rows("SELECT 2") == [(1,)]
    assert len(connects) == 1
    with pytest.raises(CommandError, match="boom"):
        deployer._query_rows("fail")
    assert getattr(connects[0], "closed")
    deployer._query_rows("SELECT 3")
    assert len(connects) == 2
    deployer.close()
    assert getattr(connects[1], "closed")
