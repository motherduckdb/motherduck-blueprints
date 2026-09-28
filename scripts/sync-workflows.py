"""Generate repository test jobs from the released workflow implementations.

Event triggers stay repository-specific. Only the action reference changes so CI
exercises the current checkout, while customers keep their versioned action.
Reusable inputs that the repository header does not declare are replaced with
their workflow_call defaults, because repository events have no such inputs.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '# Generated jobs: edit reusable workflows, then run make sync-workflows.\n'


def declared_inputs(workflow: str, event: str) -> dict[str, str | None]:
    """Return input names and raw YAML default scalars for one event.

    This reads the fixed layout of the repository's workflow headers so the
    script keeps working with only the standard library.
    """
    block = re.search(rf'^  {event}:\n    inputs:\n((?:(?: {{6,}}.*)?\n)*)', workflow, re.MULTILINE)
    if not block:
        return {}
    inputs: dict[str, str | None] = {}
    current = None
    for line in block.group(1).splitlines():
        if name := re.fullmatch(r' {6}([\w-]+):', line):
            current = name.group(1)
            inputs[current] = None
        elif current and (default := re.fullmatch(r' {8}default: (.+)', line)):
            inputs[current] = default.group(1)
    return inputs


def apply_defaults(jobs: str, provider: dict[str, str | None], header: str) -> str:
    local = set(declared_inputs(header + '\n', 'workflow_dispatch'))
    for name, default in provider.items():
        if name in local:
            continue
        if default is None:
            raise SystemExit(f'Reusable input {name} needs a default to generate repository jobs.')
        pattern = re.compile(r'\$\{\{[^}]*\binputs\.' + re.escape(name) + r'\b[^}]*\}\}')
        jobs = pattern.sub(lambda _: default, jobs)
        if re.search(r'\binputs\.' + re.escape(name) + r'\b', jobs):
            raise SystemExit(f'Could not replace every inputs.{name} reference in generated jobs.')
    return jobs


def sync(*, check: bool) -> None:
    for name in ('deploy_blueprints', 'cleanup_preview_blueprints', 'blueprints_doctor', 'prepare_guide_context'):
        directory = ROOT / '.github/workflows'
        target = directory / f'{name}.yaml'
        source = (directory / f'reusable_{name}.yaml').read_text()
        jobs = source.split('\njobs:\n', 1)[1]
        jobs = re.sub(r'uses: motherduckdb/motherduck-blueprints@v[\d.]+', 'uses: ./', jobs)
        original = target.read_text()
        header = original.split('\njobs:\n', 1)[0].replace(MARKER, '').rstrip()
        jobs = apply_defaults(jobs, declared_inputs(source, 'workflow_call'), header)
        updated = header + '\n' + MARKER + '\njobs:\n' + jobs
        if check and original != updated:
            raise SystemExit(f'{target.relative_to(ROOT)} is stale. Run make sync-workflows.')
        if not check:
            target.write_text(updated)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sync(check=parser.parse_args().check)
