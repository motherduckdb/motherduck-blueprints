#!/usr/bin/env bash
#
# Deploy a single MotherDuck Dive from dives/<name>/.
#
# Usage:
#   ./scripts/deploy-dive.sh <dive-folder-name>
#
# Environment:
#   MOTHERDUCK_TOKEN  required by the MotherDuck DuckDB extension
#   PREVIEW_BRANCH    optional; deploys as "<Title>:<branch> (Preview)"
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DIVE_NAME="${1:?Usage: deploy-dive.sh <dive-folder-name>}"
DIVE_DIR="${REPO_ROOT}/dives/${DIVE_NAME}"
METADATA_FILE="${DIVE_DIR}/dive_metadata.json"
SOURCE_FILE="${DIVE_DIR}/${DIVE_NAME}.tsx"

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

require_file() {
  if [ ! -f "$1" ]; then
    echo "Required file not found: $1" >&2
    exit 1
  fi
}

require_file "$METADATA_FILE"
require_file "$SOURCE_FILE"

TITLE=$(jq -er '.title | select(type == "string" and length > 0)' "$METADATA_FILE")
DESCRIPTION=$(jq -er '.description // "" | tostring' "$METADATA_FILE")
PREVIEW_MODE=false
BRANCH_SLUG=""

if [ -n "${PREVIEW_BRANCH:-}" ]; then
  PREVIEW_MODE=true
  BRANCH_SLUG=$(branch_slug "$PREVIEW_BRANCH")
fi

RESOURCE_COUNT=$(jq -er '(.requiredResources | select(type == "array") | length)' "$METADATA_FILE")
if (( RESOURCE_COUNT == 0 )); then
  echo "dive_metadata.json must declare at least one requiredResources entry" >&2
  exit 1
fi

resolve_share_url() {
  local share_name="$1"
  local share_name_sql
  local attempts="${SHARE_RESOLVE_ATTEMPTS:-12}"
  local sleep_seconds="${SHARE_RESOLVE_SLEEP_SECONDS:-10}"
  local url=""

  share_name_sql=$(sql_string_literal "$share_name")

  for (( attempt = 1; attempt <= attempts; attempt++ )); do
    url=$(duckdb md: -csv -noheader -c "SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = ${share_name_sql}")
    if [ -n "$url" ]; then
      printf "%s" "$url"
      return 0
    fi
    if (( attempt < attempts )); then
      echo "  Waiting for share '${share_name}' to exist (${attempt}/${attempts})..." >&2
      sleep "$sleep_seconds"
    fi
  done

  echo "Could not resolve shareName '${share_name}' to a MotherDuck share URL. Run the Flight that creates it, then retry this Dive deploy." >&2
  return 1
}

RESOURCE_EXPRESSIONS=()
while IFS= read -r resource; do
  ALIAS=$(jq -er \
    --arg preview_branch "${PREVIEW_BRANCH:-}" \
    --arg branch_slug "$BRANCH_SLUG" '
    def template:
      gsub("\\$\\{PREVIEW_BRANCH\\}"; $preview_branch)
      | gsub("\\$\\{BRANCH_SLUG\\}"; $branch_slug);
    .alias | select(type == "string" and length > 0) | template
  ' <<< "$resource")
  URL=$(jq -r \
    --arg preview_mode "$PREVIEW_MODE" \
    --arg preview_branch "${PREVIEW_BRANCH:-}" \
    --arg branch_slug "$BRANCH_SLUG" '
    def template:
      gsub("\\$\\{PREVIEW_BRANCH\\}"; $preview_branch)
      | gsub("\\$\\{BRANCH_SLUG\\}"; $branch_slug);
    if $preview_mode == "true" and ((.previewUrl // "") != "") then
      .previewUrl
    else
      .url // ""
    end | tostring | template
  ' <<< "$resource")
  SHARE_NAME=$(jq -r \
    --arg preview_mode "$PREVIEW_MODE" \
    --arg preview_branch "${PREVIEW_BRANCH:-}" \
    --arg branch_slug "$BRANCH_SLUG" '
    def template:
      gsub("\\$\\{PREVIEW_BRANCH\\}"; $preview_branch)
      | gsub("\\$\\{BRANCH_SLUG\\}"; $branch_slug);
    if $preview_mode == "true" and ((.previewShareName // "") != "") then
      .previewShareName
    else
      .shareName // ""
    end | tostring | template
  ' <<< "$resource")

  if [ -z "$URL" ]; then
    if [ -z "$SHARE_NAME" ]; then
      echo "Each requiredResources entry must include either url or shareName" >&2
      exit 1
    fi
    URL=$(resolve_share_url "$SHARE_NAME")
  fi

  RESOURCE_EXPRESSIONS+=("{'url': $(sql_string_literal "$URL"), 'alias': $(sql_string_literal "$ALIAS")}")
done < <(jq -c '.requiredResources[]' "$METADATA_FILE")

REQUIRED_RESOURCES_SQL="["
for expression in "${RESOURCE_EXPRESSIONS[@]}"; do
  if [ "$REQUIRED_RESOURCES_SQL" != "[" ]; then
    REQUIRED_RESOURCES_SQL+=", "
  fi
  REQUIRED_RESOURCES_SQL+="$expression"
done
REQUIRED_RESOURCES_SQL+="]"

if [ -n "${PREVIEW_BRANCH:-}" ]; then
  DEPLOY_TITLE="${TITLE}:${PREVIEW_BRANCH} (Preview)"
else
  DEPLOY_TITLE="${TITLE}"
fi

DEPLOY_TITLE_SQL=$(sql_string_literal "$DEPLOY_TITLE")
DESCRIPTION_SQL=$(sql_string_literal "$DESCRIPTION")
SOURCE_FILE_SQL=$(sql_string_literal "$SOURCE_FILE")

EXISTING_DIVE_ID=$(duckdb md: -csv -noheader -c "SELECT id FROM MD_LIST_DIVES() WHERE title = ${DEPLOY_TITLE_SQL}")
if [ -z "$EXISTING_DIVE_ID" ]; then
  EXISTING_DIVE_COUNT=0
else
  EXISTING_DIVE_COUNT=$(printf "%s\n" "$EXISTING_DIVE_ID" | wc -l | tr -d ' ')
fi

# The local runtime can export REQUIRED_DATABASES, but the deployed Dive runtime
# declares resources from metadata. Strip a single-line export before deploy.
CONTENT_SQL="(SELECT regexp_replace(content, 'export const REQUIRED_DATABASES[^\n]*\n', '', 'g') FROM read_text(${SOURCE_FILE_SQL}))"

if (( EXISTING_DIVE_COUNT == 0 )); then
  echo "  Creating new dive '${DEPLOY_TITLE}'..." >&2
  DIVE_ID=$(duckdb md: -csv -noheader -c "SET VARIABLE content = ${CONTENT_SQL}; SELECT id FROM MD_CREATE_DIVE(title = ${DEPLOY_TITLE_SQL}, content = getvariable('content'), description = ${DESCRIPTION_SQL}, api_version = 1, required_resources = ${REQUIRED_RESOURCES_SQL})")
elif (( EXISTING_DIVE_COUNT == 1 )); then
  echo "  Updating existing dive '${DEPLOY_TITLE}' (${EXISTING_DIVE_ID})..." >&2
  duckdb md: -csv -noheader -c "SET VARIABLE content = ${CONTENT_SQL}; FROM MD_UPDATE_DIVE_CONTENT(id = '${EXISTING_DIVE_ID}'::UUID, content = getvariable('content'), api_version = 1, required_resources = ${REQUIRED_RESOURCES_SQL}); FROM MD_UPDATE_DIVE_METADATA(id = '${EXISTING_DIVE_ID}'::UUID, title = ${DEPLOY_TITLE_SQL}, description = ${DESCRIPTION_SQL});"
  DIVE_ID="${EXISTING_DIVE_ID}"
else
  echo "Error: found ${EXISTING_DIVE_COUNT} dives with title '${DEPLOY_TITLE}'. Expected 0 or 1." >&2
  exit 1
fi

echo "  Deployed: https://app.motherduck.com/dives/${DIVE_ID}" >&2

if [ -n "${PREVIEW_BRANCH:-}" ]; then
  echo "| ${DEPLOY_TITLE} | [Open Dive](https://app.motherduck.com/dives/${DIVE_ID}) |"
fi
