#!/usr/bin/env bash
#
# Verify release tags and package metadata agree before publishing artifacts.
#
set -euo pipefail

EXPECTED_TAG="${1:-}"

python3 - "$EXPECTED_TAG" <<'PY'
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import tomllib

expected_tag = sys.argv[1]
root = pathlib.Path.cwd()
pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
package_version = pyproject["project"]["version"]

init_path = root / "src" / "md_blueprints" / "__init__.py"
match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_path.read_text(encoding="utf-8"), re.MULTILINE)
if not match:
    raise SystemExit("Could not find __version__ in src/md_blueprints/__init__.py")
module_version = match.group(1)

if package_version != module_version:
    raise SystemExit(
        f"Version mismatch: pyproject.toml has {package_version}, "
        f"src/md_blueprints/__init__.py has {module_version}"
    )

if expected_tag:
    expected_version = expected_tag.removeprefix("refs/tags/").removeprefix("v")
    if expected_version != package_version:
        raise SystemExit(
            f"Tag mismatch: {expected_tag} implies {expected_version}, "
            f"but package version is {package_version}"
        )

print(f"Release version OK: {package_version}")
PY
