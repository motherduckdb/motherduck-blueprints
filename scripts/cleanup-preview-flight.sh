#!/usr/bin/env bash
#
# Delete a branch-scoped preview MotherDuck Flight and optional preview data.
#
# Usage:
#   ./scripts/cleanup-preview-flight.sh <flight-folder-name> <branch-name>
#
# Environment:
#   MOTHERDUCK_TOKEN required by the MotherDuck DuckDB extension
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FLIGHT_NAME="${1:?Usage: cleanup-preview-flight.sh <flight-folder-name> <branch-name>}"
PREVIEW_BRANCH="${2:?Usage: cleanup-preview-flight.sh <flight-folder-name> <branch-name>}"
FLIGHT_DIR="${REPO_ROOT}/flights/${FLIGHT_NAME}"
METADATA_FILE="${FLIGHT_DIR}/flight_metadata.json"

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

quote_ident() {
  case "$1" in
    (*[!A-Za-z0-9_]*|""|[0-9]*)
      echo "Unsafe SQL identifier: $1" >&2
      exit 1
      ;;
  esac
  printf '"%s"' "$1"
}

if [ ! -f "$METADATA_FILE" ]; then
  echo "Flight metadata not found: $METADATA_FILE" >&2
  exit 1
fi

if [ "$(jq -er '.preview.enabled // false' "$METADATA_FILE")" != "true" ]; then
  echo "Preview Flights disabled for '${FLIGHT_NAME}'; skipping cleanup."
  exit 0
fi

BASE_NAME=$(jq -er '.name | select(type == "string" and length > 0)' "$METADATA_FILE")
BRANCH_SLUG=$(branch_slug "$PREVIEW_BRANCH")
PREVIEW_NAME="${BASE_NAME}:${PREVIEW_BRANCH} (Preview)"
PREVIEW_NAME_SQL=$(sql_string_literal "$PREVIEW_NAME")

PREVIEW_FLIGHT_IDS=$(duckdb md: -csv -noheader -c "SELECT flight_id FROM MD_LIST_FLIGHTS(\"offset\" => 0::UINTEGER, \"limit\" => 1000::UINTEGER) WHERE flight_name = ${PREVIEW_NAME_SQL}")
if [ -z "$PREVIEW_FLIGHT_IDS" ]; then
  echo "No preview Flight found for '${PREVIEW_NAME}'"
else
  while IFS= read -r FLIGHT_ID; do
    echo "Deleting preview Flight ${FLIGHT_ID} (${PREVIEW_NAME})"
    if ! duckdb md: -csv -noheader -c "FROM MD_DELETE_FLIGHT(\"flight_id\" => '${FLIGHT_ID}'::UUID);"; then
      echo "Preview Flight ${FLIGHT_ID} was already deleted or could not be deleted"
    fi
  done <<< "$PREVIEW_FLIGHT_IDS"
fi

CLEANUP_SHARE=$(jq -er '.preview.cleanupShare // true' "$METADATA_FILE")
CLEANUP_DATABASE=$(jq -er '.preview.cleanupDatabase // false' "$METADATA_FILE")

PREVIEW_CONFIG=$(jq -c \
  --arg preview_branch "$PREVIEW_BRANCH" \
  --arg branch_slug "$BRANCH_SLUG" '
  def template:
    gsub("\\$\\{PREVIEW_BRANCH\\}"; $preview_branch)
    | gsub("\\$\\{BRANCH_SLUG\\}"; $branch_slug);
  ((.config // {}) + (.preview.config // {}))
  | with_entries(.value |= (tostring | template))
' "$METADATA_FILE")

SHARE_NAME=$(jq -r '.share // ""' <<< "$PREVIEW_CONFIG")
DATABASE_NAME=$(jq -r '.database // ""' <<< "$PREVIEW_CONFIG")

if [ "$CLEANUP_SHARE" = "true" ] && [ -n "$SHARE_NAME" ]; then
  if [[ "$SHARE_NAME" != *"_preview_"* && "$SHARE_NAME" != *"$BRANCH_SLUG"* ]]; then
    echo "Refusing to drop non-preview-looking share '${SHARE_NAME}'" >&2
    exit 1
  fi
  SHARE_URL=$(duckdb md: -csv -noheader -c "SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = $(sql_string_literal "$SHARE_NAME")")
  if [ -n "$SHARE_URL" ]; then
    echo "Dropping preview share ${SHARE_NAME}"
    if ! duckdb md: -csv -noheader -c "FROM MD_DROP_DATABASE_SHARE($(sql_string_literal "$SHARE_NAME"));"; then
      echo "Preview share ${SHARE_NAME} was already dropped or could not be dropped"
    fi
  else
    echo "No preview share found for '${SHARE_NAME}'"
  fi
fi

if [ "$CLEANUP_DATABASE" = "true" ] && [ -n "$DATABASE_NAME" ]; then
  if [[ "$DATABASE_NAME" != *"_preview_"* && "$DATABASE_NAME" != *"$BRANCH_SLUG"* ]]; then
    echo "Refusing to drop non-preview-looking database '${DATABASE_NAME}'" >&2
    exit 1
  fi
  echo "Dropping preview database ${DATABASE_NAME}"
  duckdb md: -csv -noheader -c "DROP DATABASE IF EXISTS $(quote_ident "$DATABASE_NAME");"
fi
