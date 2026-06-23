#!/usr/bin/env bash
#
# Run a local mock deployment test without contacting MotherDuck.
#
# This script shadows `duckdb` with a tiny fake CLI and exercises:
#   - workflow YAML parsing
#   - shell syntax
#   - bundle validation
#   - preview bundle deploy
#   - production bundle deploy
#   - preview bundle cleanup
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
dive_state="${state_dir}/dive_id"
share_url="md:_share/mock/00000000-0000-0000-0000-000000000003"

echo "$query" >> "${state_dir}/queries.log"

if [[ "$query" == *"MD_LIST_DATABASE_SHARES"* ]]; then
  echo "$share_url"
elif [[ "$query" == *"MD_LIST_FLIGHTS"* ]]; then
  if [ -f "$flight_state" ]; then
    cat "$flight_state"
  fi
elif [[ "$query" == *"MD_CREATE_FLIGHT"* ]]; then
  echo "00000000-0000-0000-0000-000000000001" > "$flight_state"
elif [[ "$query" == *"MD_UPDATE_FLIGHT"* ]]; then
  echo "00000000-0000-0000-0000-000000000001" > "$flight_state"
elif [[ "$query" == *"MD_RUN_FLIGHT"* ]]; then
  exit 0
elif [[ "$query" == *"MD_DELETE_FLIGHT"* ]]; then
  rm -f "$flight_state"
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

cd "$REPO_ROOT"

echo "==> Parsing workflow YAML"
ruby -e 'require "yaml"; Dir[".github/workflows/*.yaml"].each { |f| YAML.load_file(f); puts "ok #{f}" }'

echo "==> Checking shell syntax"
bash -n scripts/*.sh

echo "==> Validating JSON manifests"
jq empty \
  bundles/wikipedia-pageviews/blueprint.json \
  dives/wikipedia-pageviews/dive_metadata.json \
  flights/wikipedia-pageviews/flight_metadata.json \
  templates/dive/dive_metadata.json \
  templates/flight/flight_metadata.json

echo "==> Validating bundle"
make validate-bundle wikipedia-pageviews

echo "==> Mock deploying preview bundle"
PREVIEW_BRANCH=feature/mock-test ./scripts/deploy-bundle.sh wikipedia-pageviews > "${TMP_DIR}/preview.out"
grep -q "#### Wikipedia Pageviews" "${TMP_DIR}/preview.out"
grep -q "wikipedia-pageviews:feature/mock-test (Preview)" "${TMP_DIR}/preview.out"
grep -q "wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/preview.out"
grep -q "Wikipedia Pageviews:feature/mock-test (Preview)" "${TMP_DIR}/preview.out"

echo "==> Mock deploying production bundle"
./scripts/deploy-bundle.sh wikipedia-pageviews > "${TMP_DIR}/production.out"

echo "==> Mock cleaning preview bundle"
./scripts/cleanup-preview-bundle.sh wikipedia-pageviews feature/mock-test > "${TMP_DIR}/cleanup.out"
grep -q "Deleting preview Dive" "${TMP_DIR}/cleanup.out"
grep -q "Deleting preview Flight" "${TMP_DIR}/cleanup.out"
grep -q "Dropping preview share wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/cleanup.out"
grep -q "Dropping preview database wikipedia_pageviews_preview_feature_mock_test" "${TMP_DIR}/cleanup.out"

echo "==> Verifying no Python bytecode artifacts"
if find . -name __pycache__ -o -name '*.pyc' | grep -q .; then
  echo "Generated Python bytecode artifacts found" >&2
  find . -name __pycache__ -o -name '*.pyc' >&2
  exit 1
fi

echo "Mock test passed."

