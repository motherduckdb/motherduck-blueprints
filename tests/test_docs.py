from __future__ import annotations

import json
import re
from pathlib import Path

from md_blueprints import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_PIN = re.compile(r"motherduckdb/motherduck-blueprints@v(\d+\.\d+\.\d+)")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _customer_docs() -> list[Path]:
    mapping = json.loads((REPO_ROOT / "src/md_blueprints/asset-map.json").read_text(encoding="utf-8"))
    shipped = [REPO_ROOT / source for destination, source in mapping.items() if destination.startswith("template_repo/") and source.endswith(".md")]
    template = REPO_ROOT / "src/md_blueprints/template_repo"
    return shipped + sorted(template.glob("*.md"))


def test_documented_action_pins_match_package_version() -> None:
    documents = [REPO_ROOT / "README.md", *_customer_docs()]
    stale = {
        f"{path.relative_to(REPO_ROOT)}@v{version}"
        for path in documents
        for version in ACTION_PIN.findall(path.read_text(encoding="utf-8"))
        if version != __version__
    }
    assert not stale, f"Update documented action pins to v{__version__}: {sorted(stale)}"


def test_customer_docs_do_not_link_to_tooling_only_paths() -> None:
    tooling_only = ("src/", "tests/", "scripts/", "MAINTAINING.md", "CONTRIBUTING.md")
    offenders = [
        f"{path.relative_to(REPO_ROOT)} -> {target}"
        for path in _customer_docs()
        for target in LINK.findall(path.read_text(encoding="utf-8"))
        if not target.startswith(("http://", "https://", "mailto:"))
        and any(part in target for part in tooling_only)
    ]
    assert not offenders, offenders
