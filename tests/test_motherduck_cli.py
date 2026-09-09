from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from md_blueprints import motherduck_cli
from md_blueprints.deploy import Deployer
from md_blueprints.init import run_init
from md_blueprints.project import CommandError, Project
from md_blueprints.schema import ValidationError


def test_query_uses_private_file_target_token_and_json_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: '/bin/motherduck')
    monkeypatch.setenv('MOTHERDUCK_TOKEN', 'wrong-ambient-token')
    monkeypatch.setenv('motherduck_token', 'wrong-lowercase-token')
    monkeypatch.delenv('MOTHERDUCK_HOME', raising=False)
    statement = "SELECT 'source with $(shell syntax) and secrets'"
    paths: list[Path] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert argv[:3] == ['/bin/motherduck', 'query', '--file']
        assert argv[4:] == ['--output', 'json']
        assert statement not in argv and 'target-token' not in argv
        path = Path(argv[3])
        paths.append(path)
        assert path.read_text() == statement
        assert path.parent.stat().st_mode & 0o077 == 0
        assert kwargs['env']['MOTHERDUCK_TOKEN'] == 'target-token'
        assert 'motherduck_token' not in kwargs['env']
        assert Path(kwargs['env']['MOTHERDUCK_HOME']).is_absolute()
        assert not kwargs.get('shell')
        return subprocess.CompletedProcess(argv, 0, '[{"a":null,"b":true,"c":[1,2],"d":"text"}]')

    monkeypatch.setattr(subprocess, 'run', run)
    assert motherduck_cli.query_rows(statement, token='target-token') == [(None, True, [1, 2], 'text')]
    assert paths and not paths[0].exists()
    assert os.environ['MOTHERDUCK_TOKEN'] == 'wrong-ambient-token'


@pytest.mark.parametrize('payload', ['not json', '{"success":false,"error":"failed"}', '[1]'])
def test_invalid_cli_json_fails_closed(monkeypatch: pytest.MonkeyPatch, payload: str) -> None:
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: '/bin/motherduck')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, payload))
    with pytest.raises(CommandError, match='JSON'):
        motherduck_cli.query_rows('SELECT 1', token='token')


def test_failed_query_does_not_retry_or_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: '/bin/motherduck')
    calls = []

    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, '', 'bad token secret-token in UPDATE resource')

    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(CommandError) as error:
        motherduck_cli.query_rows('UPDATE resource', token='secret-token')
    assert 'secret-token' not in str(error.value) and 'UPDATE resource' not in str(error.value)
    assert len(calls) == 1


def test_missing_cli_reports_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: None)
    with pytest.raises(CommandError, match='make install-deploy'):
        motherduck_cli.query_rows('SELECT 1', token='token')
    assert motherduck_cli.sql_backend() == 'duckdb'
    monkeypatch.setenv('MD_BLUEPRINTS_SQL_BACKEND', 'motherduck')
    assert motherduck_cli.sql_backend() == 'motherduck'


def test_only_local_default_token_import_can_use_saved_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_init(tmp_path)
    monkeypatch.setenv('MD_BLUEPRINTS_SQL_BACKEND', 'motherduck')
    for name in ('MOTHERDUCK_TOKEN', 'CI', 'GITHUB_ACTIONS'):
        monkeypatch.delenv(name, raising=False)
    deployer = Deployer(Project(tmp_path))
    deployer._prepare_live_command('prod', 'import')
    assert deployer.sql_env == {}
    for operation in ('deploy', 'plan', 'cleanup', 'verify'):
        with pytest.raises(ValidationError, match='MOTHERDUCK_TOKEN is required'):
            deployer._prepare_live_command('prod', operation)
    monkeypatch.setenv('CI', 'true')
    with pytest.raises(ValidationError, match='MOTHERDUCK_TOKEN is required'):
        deployer._prepare_live_command('prod', 'import')


def test_target_token_is_forwarded_to_native_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import md_blueprints.deploy as deploy

    run_init(tmp_path)
    manifest = tmp_path / 'motherduck.yml'
    manifest.write_text(manifest.read_text().replace('tokenEnvVar: MOTHERDUCK_TOKEN', 'tokenEnvVar: TARGET_TOKEN'))
    monkeypatch.setenv('MD_BLUEPRINTS_SQL_BACKEND', 'motherduck')
    monkeypatch.delenv('TARGET_TOKEN', raising=False)
    deployer = Deployer(Project(tmp_path))
    with pytest.raises(ValidationError, match='TARGET_TOKEN is required'):
        deployer._prepare_live_command('prod', 'import')
    monkeypatch.setenv('TARGET_TOKEN', 'selected-token')
    deployer._prepare_live_command('prod', 'plan')
    tokens: list[str | None] = []

    def query(statement: str, *, token: str | None) -> list[tuple[object, ...]]:
        tokens.append(token)
        return [(1,)]

    monkeypatch.setattr(deploy, 'cli_query_rows', query)
    assert deployer._query_rows('SELECT 1') == [(1,)]
    assert tokens == ['selected-token']


def test_installer_pins_runtime_without_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    installed = tmp_path / '.motherduck/bin/motherduck'
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: str(installed) if installed.exists() else None)
    monkeypatch.setattr(motherduck_cli, 'urlopen', lambda *a, **kw: BytesIO(b'# official installer fixture\n'))
    monkeypatch.setenv('MOTHERDUCK_TOKEN', 'do-not-pass-to-installer')
    monkeypatch.setenv('motherduck_token', 'also-private')
    monkeypatch.setenv('MD_API_HOST', 'not-the-public-release-server')
    downloads = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == 'sh':
            script = Path(argv[1])
            downloads.append(script)
            assert script.read_text() == '# official installer fixture\n'
            assert kwargs['env']['MOTHERDUCK_VERSION'] == motherduck_cli.SUPPORTED_VERSION
            assert kwargs['env']['SKIP_DUCKDB_CLI'] == '1'
            assert kwargs['env']['MOTHERDUCK_NONINTERACTIVE'] == '1'
            assert not {'MOTHERDUCK_TOKEN', 'motherduck_token', 'MD_API_HOST'} & kwargs['env'].keys()
            installed.parent.mkdir(parents=True)
            installed.touch()
            return subprocess.CompletedProcess(argv, 0, '')
        assert argv == [str(installed), '--version']
        return subprocess.CompletedProcess(argv, 0, motherduck_cli.SUPPORTED_VERSION + '\n')

    monkeypatch.setattr(subprocess, 'run', run)
    motherduck_cli.install_cli()
    assert len(downloads) == 1 and not downloads[0].exists()
    motherduck_cli.install_cli()
    assert len(downloads) == 1


def test_legacy_python_backend_is_still_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    import duckdb

    run_init(tmp_path)
    deployer = Deployer(Project(tmp_path))
    deployer.sql_env = {'motherduck_token': 'test-only'}
    monkeypatch.setenv('MD_BLUEPRINTS_SQL_BACKEND', 'duckdb')
    queries: list[str] = []
    closed: list[bool] = []

    def execute(statement: str) -> Any:
        queries.append(statement)
        return SimpleNamespace(fetchall=lambda: [(1,)])

    monkeypatch.setattr(duckdb, 'connect', lambda *a, **kw: SimpleNamespace(
        execute=execute, close=lambda: closed.append(True),
    ))
    assert deployer._query_rows('SELECT 1') == [(1,)]
    assert queries == ['SELECT 1'] and closed == [True]


@pytest.mark.parametrize('payload,expected', [
    ('[{"first":1}]\n[{"second":2}]\n', [(2,)]),
    ('[{"id":"created"}]\n[]\n', []),
])
def test_query_accepts_every_statement_result_and_returns_last(
    monkeypatch: pytest.MonkeyPatch, payload: str, expected: list[tuple[object, ...]],
) -> None:
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: '/bin/motherduck')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, payload))
    assert motherduck_cli.query_rows('SELECT 1; SELECT 2;', token='test-only') == expected


@pytest.mark.parametrize('payload', ['[{"first":1}]\nnot json', '[{"first":1}]\n{"success":false}'])
def test_query_does_not_hide_a_broken_second_result(monkeypatch: pytest.MonkeyPatch, payload: str) -> None:
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: '/bin/motherduck')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, payload))
    with pytest.raises(CommandError, match='JSON'):
        motherduck_cli.query_rows('SELECT 1; SELECT 2;', token='test-only')


def test_successful_ddl_has_no_json_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(motherduck_cli, 'executable', lambda: '/bin/motherduck')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, ''))
    assert motherduck_cli.query_rows('CREATE TEMP TABLE test (x INT)', token='test-only') == []


def test_python_backend_checks_timestamp_dependency_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib
    import duckdb

    run_init(tmp_path)
    deployer = Deployer(Project(tmp_path))
    deployer.sql_env = {'motherduck_token': 'test-only'}
    monkeypatch.setenv('MD_BLUEPRINTS_SQL_BACKEND', 'duckdb')

    def missing(name: str) -> None:
        assert name == 'pytz'
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(importlib, 'import_module', missing)
    monkeypatch.setattr(duckdb, 'connect', lambda *a, **kw: pytest.fail('Connection opened before dependency check'))
    with pytest.raises(CommandError, match=r'md-blueprints\[deploy\]'):
        deployer._query_rows('CREATE TABLE example (x INT)')
