"""Explicit CI smoke for the real MotherDuck binary. No account or token needed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from md_blueprints.motherduck_cli import SUPPORTED_VERSION, executable


def test_native_cli_contract_and_local_scaffolds(tmp_path: Path) -> None:
    cli = executable()
    assert cli, 'Run make install-deploy first'
    env = {**os.environ, 'MOTHERDUCK_HOME': str(tmp_path / 'home')}
    env.pop('MOTHERDUCK_TOKEN', None)
    env.pop('motherduck_token', None)

    def run(*args: str) -> str:
        return subprocess.check_output([cli, *args], env=env, text=True)

    assert run('--version').strip() == SUPPORTED_VERSION
    query_help = run('query', '--help')
    assert '--file' in query_help and '--output' in query_help
    for kind,option,source in (
        ('dive', '--title', 'index.tsx'),
        ('flight', '--name', 'main.py'),
        ('guide', '--title', 'guide.md'),
    ):
        for command in ('list', 'pull', 'push', 'list-versions', 'delete'):
            assert '--output' in run(kind, command, '--help')
        directory = tmp_path / kind
        result = json.loads(run(kind, 'init', str(directory), option, 'CI smoke', '--output', 'json'))
        assert result['success'] is True
        assert (directory / source).is_file()
        metadata = json.loads((directory / f'{kind}.metadata.json').read_text())
        assert not metadata.get('id')
