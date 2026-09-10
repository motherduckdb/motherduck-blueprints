"""Generate repository test jobs from the released workflow implementations.

Event triggers stay repository-specific. Only the action reference changes so CI
exercises the current checkout, while customers keep their versioned action.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '# Generated jobs: edit reusable workflows, then run make sync-workflows.\n'


def sync(*, check: bool) -> None:
    for name in ('deploy_blueprints', 'cleanup_preview_blueprints', 'blueprints_doctor'):
        directory = ROOT / '.github/workflows'
        target = directory / f'{name}.yaml'
        source = (directory / f'reusable_{name}.yaml').read_text()
        jobs = source.split('\njobs:\n', 1)[1]
        jobs = re.sub(r'uses: motherduckdb/motherduck-blueprints@v[\d.]+', 'uses: ./', jobs)
        original = target.read_text()
        header = original.split('\njobs:\n', 1)[0].replace(MARKER, '').rstrip()
        updated = header + '\n' + MARKER + '\njobs:\n' + jobs
        if check and original != updated:
            raise SystemExit(f'{target.relative_to(ROOT)} is stale. Run make sync-workflows.')
        if not check:
            target.write_text(updated)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sync(check=parser.parse_args().check)
