#!/usr/bin/env bash
#
# Deploy a Blueprint bundle, preserving Flight -> share -> Dive ordering.
#
# Usage:
#   ./scripts/deploy-bundle.sh <bundle-name>
#
# Environment:
#   MOTHERDUCK_TOKEN required by the MotherDuck DuckDB extension
#   PREVIEW_BRANCH   optional; deploys a branch-scoped preview bundle
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUNDLE_NAME="${1:?Usage: deploy-bundle.sh <bundle-name>}"
BUNDLE_DIR="${REPO_ROOT}/bundles/${BUNDLE_NAME}"
BLUEPRINT_FILE="${BUNDLE_DIR}/blueprint.json"

sql_string_literal() {
  local escaped
  escaped=$(printf "%s" "$1" | sed "s/'/''/g")
  printf "'%s'" "$escaped"
}

branch_slug() {
  local slug
  slug=$(printf "%s" "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//; s/_+/_/g' \
    | cut -c1-48)
  if [ -z "$slug" ]; then
    slug="preview"
  fi
  printf "%s" "$slug"
}

render_template() {
  local value="$1"
  value="${value//\$\{PREVIEW_BRANCH\}/${PREVIEW_BRANCH:-}}"
  value="${value//\$\{BRANCH_SLUG\}/${BRANCH_SLUG:-}}"
  printf "%s" "$value"
}

wait_for_share() {
  local share_name="$1"
  local attempts="${SHARE_RESOLVE_ATTEMPTS:-18}"
  local sleep_seconds="${SHARE_RESOLVE_SLEEP_SECONDS:-10}"
  local share_name_sql
  local url=""

  share_name_sql=$(sql_string_literal "$share_name")

  for (( attempt = 1; attempt <= attempts; attempt++ )); do
    url=$(duckdb md: -csv -noheader -c "SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = ${share_name_sql}")
    if [ -n "$url" ]; then
      printf "%s" "$url"
      return 0
    fi
    if (( attempt < attempts )); then
      echo "  Waiting for share '${share_name}' (${attempt}/${attempts})..." >&2
      sleep "$sleep_seconds"
    fi
  done

  echo "Timed out waiting for share '${share_name}'" >&2
  return 1
}

"${SCRIPT_DIR}/validate-bundle.sh" "$BUNDLE_NAME"

PREVIEW_MODE=false
BRANCH_SLUG=""
if [ -n "${PREVIEW_BRANCH:-}" ]; then
  if [ "$(jq -er '.preview.enabled // false' "$BLUEPRINT_FILE")" != "true" ]; then
    echo "  Preview disabled for bundle '${BUNDLE_NAME}'; skipping." >&2
    exit 0
  fi
  PREVIEW_MODE=true
  BRANCH_SLUG=$(branch_slug "$PREVIEW_BRANCH")
fi

BUNDLE_TITLE=$(jq -er '.title' "$BLUEPRINT_FILE")
FLIGHT_ROWS=""
SHARE_ROWS=""
DIVE_ROWS=""

echo "Deploying bundle '${BUNDLE_TITLE}'..." >&2

while IFS= read -r flight; do
  flight_path=$(jq -r '.path // ("flights/" + .name)' <<< "$flight")
  flight_slug="$(basename "$flight_path")"
  echo "Deploying bundle Flight '${flight_slug}'..." >&2
  output="$("${SCRIPT_DIR}/deploy-flight.sh" "$flight_slug")"
  if [ -n "$output" ]; then
    FLIGHT_ROWS="${FLIGHT_ROWS}${output}"$'\n'
  fi

  while IFS= read -r share; do
    if [ "$PREVIEW_MODE" = "true" ]; then
      share_name=$(jq -r '.preview // .production // ""' <<< "$share")
    else
      share_name=$(jq -r '.production // ""' <<< "$share")
    fi
    share_name=$(render_template "$share_name")
    if [ -n "$share_name" ]; then
      share_url=$(wait_for_share "$share_name")
      if [ "$PREVIEW_MODE" = "true" ]; then
        SHARE_ROWS="${SHARE_ROWS}| ${share_name} | [Open Share](${share_url}) |"$'\n'
      fi
    fi
  done < <(jq -c '.waitForShares[]?' <<< "$flight")
done < <(jq -c '.flights[]' "$BLUEPRINT_FILE")

while IFS= read -r dive; do
  dive_path=$(jq -r '.path // ("dives/" + .name)' <<< "$dive")
  dive_slug="$(basename "$dive_path")"
  echo "Deploying bundle Dive '${dive_slug}'..." >&2
  output="$("${SCRIPT_DIR}/deploy-dive.sh" "$dive_slug")"
  if [ -n "$output" ]; then
    DIVE_ROWS="${DIVE_ROWS}${output}"$'\n'
  fi
done < <(jq -c '.dives[]' "$BLUEPRINT_FILE")

if [ "$PREVIEW_MODE" = "true" ]; then
  echo "#### ${BUNDLE_TITLE}"
  echo ""
  if [ -n "$FLIGHT_ROWS" ]; then
    echo "##### Flights"
    echo ""
    echo "| Flight | ID | Run started | Share |"
    echo "|--------|----|-------------|-------|"
    printf "%s" "$FLIGHT_ROWS"
    echo ""
  fi
  if [ -n "$SHARE_ROWS" ]; then
    echo "##### Shares"
    echo ""
    echo "| Share | Link |"
    echo "|-------|------|"
    printf "%s" "$SHARE_ROWS"
    echo ""
  fi
  if [ -n "$DIVE_ROWS" ]; then
    echo "##### Dives"
    echo ""
    echo "| Dive | Link |"
    echo "|------|------|"
    printf "%s" "$DIVE_ROWS"
  fi
fi

