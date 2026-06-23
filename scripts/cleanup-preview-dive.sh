#!/usr/bin/env bash
#
# Delete a branch-scoped preview MotherDuck Dive.
#
# Usage:
#   ./scripts/cleanup-preview-dive.sh <dive-folder-name> <branch-name>
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DIVE_NAME="${1:?Usage: cleanup-preview-dive.sh <dive-folder-name> <branch-name>}"
PREVIEW_BRANCH="${2:?Usage: cleanup-preview-dive.sh <dive-folder-name> <branch-name>}"
DIVE_DIR="${REPO_ROOT}/dives/${DIVE_NAME}"
METADATA_FILE="${DIVE_DIR}/dive_metadata.json"

sql_string_literal() {
  local escaped
  escaped=$(printf "%s" "$1" | sed "s/'/''/g")
  printf "'%s'" "$escaped"
}

if [ ! -f "$METADATA_FILE" ]; then
  echo "Dive metadata not found: $METADATA_FILE" >&2
  exit 1
fi

TITLE=$(jq -er '.title | select(type == "string" and length > 0)' "$METADATA_FILE")
PREVIEW_TITLE="${TITLE}:${PREVIEW_BRANCH} (Preview)"
PREVIEW_TITLE_SQL=$(sql_string_literal "$PREVIEW_TITLE")

PREVIEW_DIVE_IDS=$(duckdb md: -csv -noheader -c "SELECT id FROM MD_LIST_DIVES() WHERE title = ${PREVIEW_TITLE_SQL}")
if [ -z "$PREVIEW_DIVE_IDS" ]; then
  echo "No preview Dive found for '${PREVIEW_TITLE}'"
  exit 0
fi

while IFS= read -r DIVE_ID; do
  echo "Deleting preview Dive ${DIVE_ID} (${PREVIEW_TITLE})"
  duckdb md: -csv -noheader -c "FROM MD_DELETE_DIVE(id='${DIVE_ID}'::UUID)"
done <<< "$PREVIEW_DIVE_IDS"

