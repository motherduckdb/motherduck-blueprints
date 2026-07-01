#!/usr/bin/env bash
#
# Build the md-blueprints distribution and smoke test the installed wheel.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"
DIST_DIR="${1:-${TMP_DIR}/dist}"
INSTALL_VENV="${TMP_DIR}/install"
PYTHON_BIN="${PYTHON:-python3}"

create_venv() {
  local path="$1"
  if "$PYTHON_BIN" -m venv "$path" 2>/dev/null; then
    return
  fi
  if command -v uv >/dev/null 2>&1; then
    rm -rf "$path"
    uv venv --seed --python "$PYTHON_BIN" "$path"
    return
  fi
  "$PYTHON_BIN" -m venv "$path"
}

cleanup() {
  rm -rf "$TMP_DIR"
  rm -rf "$REPO_ROOT/build" "$REPO_ROOT/src/md_blueprints.egg-info"
  find "$REPO_ROOT/src/md_blueprints" -name __pycache__ -type d -prune -exec rm -rf {} +
}
trap cleanup EXIT

cd "$REPO_ROOT"

export PYTHONDONTWRITEBYTECODE=1

create_venv "${TMP_DIR}/build"
"${TMP_DIR}/build/bin/python" -m pip install --upgrade pip build
"${TMP_DIR}/build/bin/python" -m build --outdir "$DIST_DIR"

WHEEL="$(find "$DIST_DIR" -maxdepth 1 -name 'md_blueprints-*.whl' | sort | tail -n 1)"
SDIST="$(find "$DIST_DIR" -maxdepth 1 -name 'md_blueprints-*.tar.gz' | sort | tail -n 1)"
test -n "$WHEEL" || { echo "md-blueprints wheel not found in $DIST_DIR" >&2; exit 1; }
test -n "$SDIST" || { echo "md-blueprints sdist not found in $DIST_DIR" >&2; exit 1; }

create_venv "$INSTALL_VENV"
"$INSTALL_VENV/bin/python" -m pip install "$WHEEL"

CLI_VERSION="$("$INSTALL_VENV/bin/md-blueprints" --version)"
echo "$CLI_VERSION"
if [ -n "${EXPECTED_VERSION:-}" ] && [ "$CLI_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "md-blueprints --version mismatch: expected ${EXPECTED_VERSION}, got ${CLI_VERSION}" >&2
  exit 1
fi

"$INSTALL_VENV/bin/md-blueprints" validate --root "$REPO_ROOT"
"$INSTALL_VENV/bin/md-blueprints" doctor --root "$REPO_ROOT"
"$INSTALL_VENV/bin/md-blueprints" migrate --root "$REPO_ROOT" --to latest
"$INSTALL_VENV/bin/md-blueprints" init "$TMP_DIR/generated-template"
"$INSTALL_VENV/bin/md-blueprints" validate --root "$TMP_DIR/generated-template"
grep -q "CLI_VERSION := ${CLI_VERSION}" "$TMP_DIR/generated-template/Makefile"
grep -q "motherduckdb/motherduck-blueprints@v${CLI_VERSION%%.*}" "$TMP_DIR/generated-template/.github/workflows/deploy_blueprints.yaml"
test -f "$TMP_DIR/generated-template/.dive-preview/.env.example"
test -f "$TMP_DIR/generated-template/context/policies/.gitkeep"
test -f "$TMP_DIR/generated-template/context/schemas/.gitkeep"
test ! -e "$TMP_DIR/generated-template/src"
test ! -e "$TMP_DIR/generated-template/pyproject.toml"
test ! -e "$TMP_DIR/generated-template/CHANGELOG.md"

"$INSTALL_VENV/bin/python" - "$CLI_VERSION" <<'PY'
import importlib.metadata
import json
import sys
from importlib import resources

cli_version = sys.argv[1]
version = importlib.metadata.version("md-blueprints")
if version != cli_version:
    raise SystemExit(f"installed metadata version {version} does not match md-blueprints --version {cli_version}")
package = resources.files("md_blueprints")
for schema in ["motherduck-root.schema.json", "blueprint.schema.json"]:
    payload = package.joinpath("schemas", "v1", schema).read_text(encoding="utf-8")
    json.loads(payload)
template = package.joinpath("template_repo", "Makefile").read_text(encoding="utf-8")
if "__MD_BLUEPRINTS_VERSION__" not in template:
    raise SystemExit("template package data did not include unstamped Makefile")
print(f"installed md-blueprints package OK: {version}")
PY

echo "Package smoke test passed."
