#!/usr/bin/env bash
#
# Run local validation and deployment tests without contacting MotherDuck.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"
# The fake MotherDuck runtime (duckdb module, CLI, and network guard) is shared with the e2e tests.
FAKE_MOTHERDUCK="${REPO_ROOT}/tests/fixtures/fake_motherduck"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

export MD_BLUEPRINTS_SQL_BACKEND=motherduck
export PATH="${FAKE_MOTHERDUCK}:${PATH}"
export PYTHONPATH="${FAKE_MOTHERDUCK}${PYTHONPATH:+:${PYTHONPATH}}"
export MOCK_DUCKDB_STATE_DIR="$TMP_DIR"
export SHARE_RESOLVE_ATTEMPTS=1
export SHARE_RESOLVE_SLEEP_SECONDS=0
export FLIGHT_RUN_POLL_ATTEMPTS=1
export FLIGHT_RUN_POLL_SLEEP_SECONDS=0
export MOTHERDUCK_TOKEN=mock-token
export TARGET_MD_TOKEN=target-mock-token
export PYTHONDONTWRITEBYTECODE=1

cd "$REPO_ROOT"

echo "==> Parsing workflow YAML"
python3 - <<'PY'
from pathlib import Path

import yaml

paths = sorted(Path(".github/workflows").glob("*.yaml")) + [Path("action.yml")]
for path in paths:
    yaml.safe_load(path.read_text())
    print(f"ok {path}")
PY

echo "==> Checking shell and Python syntax"
bash -n scripts/*.sh
python3 - <<'PY'
import ast
from pathlib import Path

for path in sorted(Path("src").rglob("*.py")):
    ast.parse(path.read_text(), filename=str(path))
    print(f"ok {path}")
PY

echo "==> Checking package entrypoints"
md-blueprints --version
./tools/md_blueprints --version 2> "${TMP_DIR}/wrapper.err"
grep -q "Deprecation: tools/md_blueprints" "${TMP_DIR}/wrapper.err"

echo "==> Validating root and fixture manifests"
make validate
md-blueprints validate --root tests/fixtures/simple
md-blueprints validate --root tests/fixtures/medium
md-blueprints validate --root tests/fixtures/complex
if md-blueprints validate --root tests/fixtures/invalid-preview > "${TMP_DIR}/invalid.out" 2>&1; then
  echo "Invalid preview fixture unexpectedly passed" >&2
  exit 1
fi
grep -q "must include branch slug" "${TMP_DIR}/invalid.out"

echo "==> Rejecting invalid schema fields"
INVALID_SCHEMA_ROOT="${TMP_DIR}/invalid-schema"
rsync -a \
  --exclude .git \
  --exclude .venv \
  --exclude .dive-preview/.env \
  --exclude .dive-preview/dist \
  --exclude .dive-preview/node_modules \
  "$REPO_ROOT/" "$INVALID_SCHEMA_ROOT/"
python3 - "$INVALID_SCHEMA_ROOT/dives/wikipedia-pageviews/blueprint.yml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
needle = "          alias: wikipedia_pageviews\n"
replacement = "          alias: wikipedia_pageviews\n          unexpectedField: should-fail\n"
path.write_text(text.replace(needle, replacement))
PY
if md-blueprints validate --root "$INVALID_SCHEMA_ROOT" > "${TMP_DIR}/invalid-schema.out" 2>&1; then
  echo "Invalid schema field unexpectedly passed" >&2
  exit 1
fi
grep -q "Unknown field 'unexpectedField'" "${TMP_DIR}/invalid-schema.out"

echo "==> Smoke testing blueprint template scaffold"
SCAFFOLD_ROOT="${TMP_DIR}/scaffold"
rsync -a \
  --exclude .git \
  --exclude .venv \
  --exclude .dive-preview/node_modules \
  "$REPO_ROOT/" "$SCAFFOLD_ROOT/"
make -C "$SCAFFOLD_ROOT" new-project NAME=smoke-template
make -C "$SCAFFOLD_ROOT" validate
md-blueprints render --root "$SCAFFOLD_ROOT" --target preview --branch feature/template --blueprints smoke-template > "${TMP_DIR}/scaffold-render.out"
grep -q "smoke_template_preview_feature_template" "${TMP_DIR}/scaffold-render.out"
grep -q '"scheduleCron": ""' "${TMP_DIR}/scaffold-render.out"

echo "==> Rendering preview target"
md-blueprints render --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/render.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/render.out"
grep -q '"scheduleCron": ""' "${TMP_DIR}/render.out"
grep -q '"status": "draft"' "${TMP_DIR}/render.out"

echo "==> Planning preview target"
: > "${TMP_DIR}/queries.log"
md-blueprints plan --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/plan.out"
grep -q "#### Deployment Plan" "${TMP_DIR}/plan.out"
grep -q "wikipedia-pageviews:feature/mock-test (Preview).*create" "${TMP_DIR}/plan.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test.*present" "${TMP_DIR}/plan.out"
grep -q "Wikipedia Pageviews:feature/mock-test (Preview).*create" "${TMP_DIR}/plan.out"
grep -q "Wikipedia Pageviews:feature/mock-test (Preview).*draft" "${TMP_DIR}/plan.out"
if grep -Eq "MD_CREATE_|MD_UPDATE_|MD_DELETE_|MD_DROP_DATABASE_SHARE|DROP DATABASE" "${TMP_DIR}/queries.log"; then
  echo "Plan command issued a mutating query" >&2
  cat "${TMP_DIR}/queries.log" >&2
  exit 1
fi

echo "==> Planning preview target as JSON"
md-blueprints plan --target preview --branch feature/mock-test --blueprints wikipedia-pageviews --json > "${TMP_DIR}/plan.json"
python3 - "${TMP_DIR}/plan.json" <<'PY'
import json
import sys

records = json.loads(open(sys.argv[1]).read())
required = {
    "blueprint", "type", "key", "name", "action", "exists", "id", "notes",
    "current_status", "desired_status",
}
if not all(required <= set(row) for row in records):
    raise SystemExit("missing stable plan fields")
if not any(row["type"] == "flight" and row["action"] == "create" for row in records):
    raise SystemExit("missing flight create plan")
PY

echo "==> Planning missing share"
MOCK_SHARE_MISSING=true md-blueprints plan --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/missing-share.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test.*pending" "${TMP_DIR}/missing-share.out"

echo "==> Rejecting duplicate live resources during plan"
if MOCK_DUPLICATE_FLIGHTS=true md-blueprints plan --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/duplicate-flight.out" 2>&1; then
  echo "Duplicate Flight plan unexpectedly passed" >&2
  exit 1
fi
grep -q "duplicate Flight name" "${TMP_DIR}/duplicate-flight.out"
if MOCK_DUPLICATE_DIVES=true md-blueprints plan --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/duplicate-dive.out" 2>&1; then
  echo "Duplicate Dive plan unexpectedly passed" >&2
  exit 1
fi
grep -q "duplicate Dive title" "${TMP_DIR}/duplicate-dive.out"
: > "${TMP_DIR}/queries.log"
if MOCK_DUPLICATE_FLIGHTS=true md-blueprints deploy --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/duplicate-deploy.out" 2>&1; then
  echo "Duplicate Flight deploy unexpectedly passed" >&2
  exit 1
fi
grep -q "duplicate Flight name" "${TMP_DIR}/duplicate-deploy.out"
if grep -Eq "MD_CREATE_|MD_UPDATE_|MD_DELETE_|MD_DROP_DATABASE_SHARE|DROP DATABASE" "${TMP_DIR}/queries.log"; then
  echo "Duplicate-resource deploy issued a mutating query" >&2
  cat "${TMP_DIR}/queries.log" >&2
  exit 1
fi

echo "==> Verifying target-specific token env var"
env -u MOTHERDUCK_TOKEN TARGET_MD_TOKEN=target-mock-token md-blueprints plan --root tests/fixtures/simple --target preview --branch feature/token --blueprints simple-dive > "${TMP_DIR}/target-token.out"
grep -q "Simple Dive:feature/token (Preview).*create" "${TMP_DIR}/target-token.out"

echo "==> Verifying missing live token fails"
if env -u MOTHERDUCK_TOKEN md-blueprints plan --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/missing-token.out" 2>&1; then
  echo "Missing token plan unexpectedly passed" >&2
  exit 1
fi
grep -q "MOTHERDUCK_TOKEN is required to plan target preview" "${TMP_DIR}/missing-token.out"

echo "==> Mock deploying preview blueprint"
md-blueprints deploy --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/preview.out"
grep -q "#### Wikipedia Pageviews" "${TMP_DIR}/preview.out"
grep -q "wikipedia-pageviews:feature/mock-test (Preview)" "${TMP_DIR}/preview.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/preview.out"
grep -q "Wikipedia Pageviews:feature/mock-test (Preview)" "${TMP_DIR}/preview.out"
head -n 1 "${TMP_DIR}/preview.out" | grep -qxF "**Selected:** \`wikipedia-pageviews\` · **Added by the dependency graph:** \`wikipedia-pageviews-ingest\`"
grep -q "^<summary>Verified [0-9]* resources across 2 blueprints</summary>$" "${TMP_DIR}/preview.out"

echo "==> Mock updating unscheduled preview blueprint"
md-blueprints deploy --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/preview-update.out" 2>&1
grep -q "Updating existing flight 'wikipedia-pageviews:feature/mock-test (Preview)'" "${TMP_DIR}/preview-update.out"

echo "==> Mock deploying production blueprint"
md-blueprints deploy --target prod --blueprints wikipedia-pageviews > "${TMP_DIR}/production.out"
grep -q "MD_UPDATE_DIVE_STATUS.*'ready'" "${TMP_DIR}/queries.log"

echo "==> Verifying empty access token is not sent"
if grep -q "\"access_token_name\" => ''" "${TMP_DIR}/queries.log"; then
  echo "Empty access_token_name argument was sent to MotherDuck" >&2
  exit 1
fi

echo "==> Dry-running preview cleanup"
: > "${TMP_DIR}/queries.log"
md-blueprints cleanup --dry-run --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/cleanup-dry-run.out"
grep -q "Wikipedia Pageviews:feature/mock-test (Preview).*delete" "${TMP_DIR}/cleanup-dry-run.out"
grep -q "wikipedia-pageviews:feature/mock-test (Preview).*delete" "${TMP_DIR}/cleanup-dry-run.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test.*drop_share" "${TMP_DIR}/cleanup-dry-run.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test.*drop_database" "${TMP_DIR}/cleanup-dry-run.out"
if grep -Eq "MD_CREATE_|MD_UPDATE_|MD_DELETE_|MD_DROP_DATABASE_SHARE|DROP DATABASE" "${TMP_DIR}/queries.log"; then
  echo "Cleanup dry-run issued a mutating query" >&2
  cat "${TMP_DIR}/queries.log" >&2
  exit 1
fi

echo "==> Mock cleaning preview blueprint"
md-blueprints cleanup --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/cleanup.out"
grep -q "Deleting preview Dive" "${TMP_DIR}/cleanup.out"
grep -q "Deleting preview Flight" "${TMP_DIR}/cleanup.out"
grep -q "Dropping preview share wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/cleanup.out"
grep -q "Dropping preview database wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/cleanup.out"

echo "==> Mocking failed Flight run"
if MOCK_FLIGHT_RUN_STATUS=RUN_STATUS_FAILED md-blueprints deploy --target preview --branch feature/failed --blueprints wikipedia-pageviews > "${TMP_DIR}/failed.out" 2>&1; then
  echo "Failed Flight run unexpectedly passed" >&2
  exit 1
fi
grep -q "Log tail: mock failure log tail" "${TMP_DIR}/failed.out"

echo "==> Checking schema maintenance commands"
md-blueprints doctor > "${TMP_DIR}/doctor.out"
grep -q "schema status: latest supported schema" "${TMP_DIR}/doctor.out"
md-blueprints migrate --to latest > "${TMP_DIR}/migrate.out"
grep -q "No migration needed" "${TMP_DIR}/migrate.out"
MD_BLUEPRINTS_LATEST_VERSION="$(md-blueprints --version)" md-blueprints check-updates > "${TMP_DIR}/updates.out"
grep -q "latest md-blueprints" "${TMP_DIR}/updates.out"

echo "==> Verifying no Python bytecode artifacts"
find src tests -name __pycache__ -type d -prune -exec rm -rf {} +
PY_ARTIFACT="$(find . \
  -path ./.venv -prune -o \
  -path './src/*.egg-info' -prune -o \
  \( -name __pycache__ -o -name '*.pyc' \) -print -quit)"
if [ -n "$PY_ARTIFACT" ]; then
  echo "Generated Python bytecode artifacts found" >&2
  find . \
    -path ./.venv -prune -o \
    -path './src/*.egg-info' -prune -o \
    \( -name __pycache__ -o -name '*.pyc' \) -print >&2
  exit 1
fi

echo "Mock test passed."
