#!/usr/bin/env bash
#
# Run local validation and deployment tests without contacting MotherDuck.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"
FAKE_BIN="${TMP_DIR}/bin"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$FAKE_BIN"

cat > "${FAKE_BIN}/duckdb" <<'MOCK_DUCKDB'
#!/usr/bin/env bash
set -euo pipefail

query="$*"
state_dir="${MOCK_DUCKDB_STATE_DIR:?MOCK_DUCKDB_STATE_DIR is required}"
flight_state="${state_dir}/flight_id"
run_state="${state_dir}/run_number"
dive_state="${state_dir}/dive_id"
share_url="md:_share/mock/00000000-0000-0000-0000-000000000003"
run_status="${MOCK_FLIGHT_RUN_STATUS:-RUN_STATUS_SUCCEEDED}"

echo "$query" >> "${state_dir}/queries.log"

if [[ "$query" == *"MD_LIST_DATABASE_SHARES"* ]]; then
  echo "$share_url"
elif [[ "$query" == *"MD_LIST_FLIGHT_RUNS"* ]]; then
  if [[ "$query" == *"COALESCE(MAX(run_number)"* ]]; then
    if [ -f "$run_state" ]; then
      cat "$run_state"
    else
      echo "0"
    fi
  elif [ -f "$run_state" ]; then
    echo "$(cat "$run_state")|${run_status}"
  fi
elif [[ "$query" == *"MD_LIST_FLIGHTS"* ]]; then
  if [ -f "$flight_state" ]; then
    cat "$flight_state"
  fi
elif [[ "$query" == *"MD_CREATE_FLIGHT"* ]]; then
  echo "00000000-0000-0000-0000-000000000001" > "$flight_state"
elif [[ "$query" == *"MD_UPDATE_FLIGHT"* ]]; then
  echo "00000000-0000-0000-0000-000000000001" > "$flight_state"
elif [[ "$query" == *"MD_RUN_FLIGHT"* ]]; then
  current_run_number=0
  if [ -f "$run_state" ]; then
    current_run_number="$(cat "$run_state")"
  fi
  echo "$((current_run_number + 1))" > "$run_state"
  exit 0
elif [[ "$query" == *"MD_GET_FLIGHT_LOGS"* ]]; then
  echo "mock failure log tail"
elif [[ "$query" == *"MD_DELETE_FLIGHT"* ]]; then
  rm -f "$flight_state"
  rm -f "$run_state"
elif [[ "$query" == *"MD_DROP_DATABASE_SHARE"* ]]; then
  exit 0
elif [[ "$query" == *"DROP DATABASE IF EXISTS"* ]]; then
  exit 0
elif [[ "$query" == *"MD_LIST_DIVES"* ]]; then
  if [ -f "$dive_state" ]; then
    cat "$dive_state"
  fi
elif [[ "$query" == *"MD_CREATE_DIVE"* ]]; then
  echo "00000000-0000-0000-0000-000000000002" > "$dive_state"
  cat "$dive_state"
elif [[ "$query" == *"MD_UPDATE_DIVE"* ]]; then
  echo "00000000-0000-0000-0000-000000000002" > "$dive_state"
elif [[ "$query" == *"MD_DELETE_DIVE"* ]]; then
  rm -f "$dive_state"
else
  echo "Unexpected fake duckdb query: $query" >&2
  exit 1
fi
MOCK_DUCKDB

chmod +x "${FAKE_BIN}/duckdb"

export PATH="${FAKE_BIN}:${PATH}"
export MOCK_DUCKDB_STATE_DIR="$TMP_DIR"
export SHARE_RESOLVE_ATTEMPTS=1
export SHARE_RESOLVE_SLEEP_SECONDS=0
export FLIGHT_RUN_POLL_ATTEMPTS=1
export FLIGHT_RUN_POLL_SLEEP_SECONDS=0

cd "$REPO_ROOT"

echo "==> Parsing workflow YAML"
ruby -e 'require "yaml"; Dir[".github/workflows/*.yaml"].each { |f| YAML.load_file(f); puts "ok #{f}" }'

echo "==> Checking shell and Ruby syntax"
bash -n scripts/*.sh
ruby -c tools/md_blueprints

echo "==> Validating root and fixture manifests"
make validate
./tools/md_blueprints validate --root tests/fixtures/simple
./tools/md_blueprints validate --root tests/fixtures/medium
./tools/md_blueprints validate --root tests/fixtures/complex
if ./tools/md_blueprints validate --root tests/fixtures/invalid-preview > "${TMP_DIR}/invalid.out" 2>&1; then
  echo "Invalid preview fixture unexpectedly passed" >&2
  exit 1
fi
grep -q "must include branch slug" "${TMP_DIR}/invalid.out"

echo "==> Smoke testing blueprint template scaffold"
SCAFFOLD_ROOT="${TMP_DIR}/scaffold"
rsync -a \
  --exclude .git \
  --exclude .dive-preview/node_modules \
  "$REPO_ROOT/" "$SCAFFOLD_ROOT/"
make -C "$SCAFFOLD_ROOT" new-blueprint smoke-template
make -C "$SCAFFOLD_ROOT" validate
"$SCAFFOLD_ROOT/tools/md_blueprints" render --root "$SCAFFOLD_ROOT" --target preview --branch feature/template --blueprints smoke-template > "${TMP_DIR}/scaffold-render.out"
grep -q "smoke_template_preview_feature_template" "${TMP_DIR}/scaffold-render.out"
grep -q '"scheduleCron": ""' "${TMP_DIR}/scaffold-render.out"

echo "==> Rendering preview target"
./tools/md_blueprints render --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/render.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/render.out"
grep -q '"scheduleCron": ""' "${TMP_DIR}/render.out"

echo "==> Mock deploying preview blueprint"
./tools/md_blueprints deploy --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/preview.out"
grep -q "#### Wikipedia Pageviews" "${TMP_DIR}/preview.out"
grep -q "wikipedia-pageviews:feature/mock-test (Preview)" "${TMP_DIR}/preview.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/preview.out"
grep -q "Wikipedia Pageviews:feature/mock-test (Preview)" "${TMP_DIR}/preview.out"

echo "==> Mock deploying production blueprint"
./tools/md_blueprints deploy --target prod --blueprints wikipedia-pageviews > "${TMP_DIR}/production.out"

echo "==> Verifying empty access token is not sent"
if grep -q "\"access_token_name\" => ''" "${TMP_DIR}/queries.log"; then
  echo "Empty access_token_name argument was sent to MotherDuck" >&2
  exit 1
fi

echo "==> Mock cleaning preview blueprint"
./tools/md_blueprints cleanup --target preview --branch feature/mock-test --blueprints wikipedia-pageviews > "${TMP_DIR}/cleanup.out"
grep -q "Deleting preview Dive" "${TMP_DIR}/cleanup.out"
grep -q "Deleting preview Flight" "${TMP_DIR}/cleanup.out"
grep -q "Dropping preview share wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/cleanup.out"
grep -q "Dropping preview database wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/cleanup.out"

echo "==> Mocking failed Flight run"
if MOCK_FLIGHT_RUN_STATUS=RUN_STATUS_FAILED ./tools/md_blueprints deploy --target preview --branch feature/failed --blueprints wikipedia-pageviews > "${TMP_DIR}/failed.out" 2>&1; then
  echo "Failed Flight run unexpectedly passed" >&2
  exit 1
fi
grep -q "Log tail: mock failure log tail" "${TMP_DIR}/failed.out"

echo "==> Verifying no Python bytecode artifacts"
if find . -name __pycache__ -o -name '*.pyc' | grep -q .; then
  echo "Generated Python bytecode artifacts found" >&2
  find . -name __pycache__ -o -name '*.pyc' >&2
  exit 1
fi

echo "Mock test passed."
