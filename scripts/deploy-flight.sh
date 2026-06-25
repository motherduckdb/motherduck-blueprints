#!/usr/bin/env bash
#
# Deploy a single MotherDuck Flight from flights/<name>/.
#
# Usage:
#   ./scripts/deploy-flight.sh <flight-folder-name>
#
# Environment:
#   MOTHERDUCK_TOKEN required by the MotherDuck DuckDB extension
#   PREVIEW_BRANCH   optional; deploys an opt-in non-scheduled preview Flight
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FLIGHT_NAME="${1:?Usage: deploy-flight.sh <flight-folder-name>}"
FLIGHT_DIR="${REPO_ROOT}/flights/${FLIGHT_NAME}"
METADATA_FILE="${FLIGHT_DIR}/flight_metadata.json"
SOURCE_FILE="${FLIGHT_DIR}/flight.py"
REQUIREMENTS_FILE="${FLIGHT_DIR}/requirements.txt"

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

"${SCRIPT_DIR}/validate-flight.sh" "$FLIGHT_NAME"

NAME=$(jq -er '.name | select(type == "string" and length > 0)' "$METADATA_FILE")
SCHEDULE_CRON=$(jq -er '.scheduleCron // "" | tostring' "$METADATA_FILE")
ACCESS_TOKEN_NAME=$(jq -er '.accessTokenName // "" | tostring' "$METADATA_FILE")
RUN_ON_DEPLOY=$(jq -er '.runOnDeploy // false' "$METADATA_FILE")
PREVIEW_MODE=false
BRANCH_SLUG=""

if [ -n "${PREVIEW_BRANCH:-}" ]; then
  if [ "$(jq -er '.preview.enabled // false' "$METADATA_FILE")" != "true" ]; then
    echo "  Preview Flights disabled for '${NAME}'; skipping." >&2
    exit 0
  fi
  PREVIEW_MODE=true
  BRANCH_SLUG=$(branch_slug "$PREVIEW_BRANCH")
  NAME="${NAME}:${PREVIEW_BRANCH} (Preview)"
  SCHEDULE_CRON=""
  RUN_ON_DEPLOY=$(jq -er '.preview.runOnDeploy // false' "$METADATA_FILE")
fi

SECRET_NAMES_SQL=$(jq -r '
  def sq: "'"'"'" + gsub("'"'"'"; "'"'"''"'"'") + "'"'"'";
  "[" + ([(.secrets // [])[] | tostring | sq] | join(", ")) + "]::VARCHAR[]"
' "$METADATA_FILE")

CONFIG_SQL=$(jq -r \
  --arg preview_mode "$PREVIEW_MODE" \
  --arg preview_branch "${PREVIEW_BRANCH:-}" \
  --arg branch_slug "$BRANCH_SLUG" '
  def sq: "'"'"'" + gsub("'"'"'"; "'"'"''"'"'") + "'"'"'";
  def template:
    gsub("\\$\\{PREVIEW_BRANCH\\}"; $preview_branch)
    | gsub("\\$\\{BRANCH_SLUG\\}"; $branch_slug);
  (if $preview_mode == "true" then
    ((.config // {}) + (.preview.config // {}))
  else
    (.config // {})
  end) as $config
  | if ($config | length) == 0 then
      "map([]::VARCHAR[], []::VARCHAR[])"
    else
      "map([" + ([$config | to_entries[] | .key | template | sq] | join(", ")) +
      "], [" + ([$config | to_entries[] | .value | tostring | template | sq] | join(", ")) + "])"
    end
' "$METADATA_FILE")

SHARE_NAME=$(jq -r \
  --arg preview_mode "$PREVIEW_MODE" \
  --arg preview_branch "${PREVIEW_BRANCH:-}" \
  --arg branch_slug "$BRANCH_SLUG" '
  def template:
    gsub("\\$\\{PREVIEW_BRANCH\\}"; $preview_branch)
    | gsub("\\$\\{BRANCH_SLUG\\}"; $branch_slug);
  if $preview_mode == "true" then
    ((.config // {}) + (.preview.config // {})).share // ""
  else
    (.config // {}).share // ""
  end | tostring | template
' "$METADATA_FILE")

latest_run_number() {
  duckdb md: -csv -noheader -c "SELECT COALESCE(MAX(run_number), 0)::VARCHAR FROM MD_LIST_FLIGHT_RUNS(\"flight_id\" => '${FLIGHT_ID}'::UUID, \"offset\" => 0::UINTEGER, \"limit\" => 1000::UINTEGER);"
}

latest_run_summary() {
  duckdb md: -csv -noheader -c "SELECT run_number::VARCHAR || '|' || status::VARCHAR || '|' || COALESCE(exit_code::VARCHAR, '') FROM MD_LIST_FLIGHT_RUNS(\"flight_id\" => '${FLIGHT_ID}'::UUID, \"offset\" => 0::UINTEGER, \"limit\" => 1::UINTEGER);"
}

print_run_logs() {
  local run_number="$1"
  echo "  Flight run ${run_number} logs:" >&2
  duckdb md: -c "SELECT * FROM MD_GET_FLIGHT_LOGS(\"run_number\" => ${run_number}::UBIGINT, \"flight_id\" => '${FLIGHT_ID}'::UUID);" >&2 || true
}

wait_for_flight_run() {
  local previous_run_number="$1"
  local attempts="${FLIGHT_RUN_WAIT_ATTEMPTS:-72}"
  local sleep_seconds="${FLIGHT_RUN_WAIT_SLEEP_SECONDS:-5}"
  local summary=""
  local run_number=""
  local status=""
  local exit_code=""

  for (( attempt = 1; attempt <= attempts; attempt++ )); do
    summary=$(latest_run_summary || true)
    if [ -n "$summary" ]; then
      IFS='|' read -r run_number status exit_code <<< "$summary"
      if [ "${run_number:-0}" -gt "$previous_run_number" ]; then
        case "$status" in
          *SUCCEEDED*|*SUCCESS*|*COMPLETED*)
            echo "  Flight run ${run_number} finished with ${status}." >&2
            return 0
            ;;
          *FAILED*|*CANCELED*|*CANCELLED*|*TIMEOUT*)
            echo "  Flight run ${run_number} finished with ${status} (exit code: ${exit_code:-unknown})." >&2
            print_run_logs "$run_number"
            return 1
            ;;
        esac
      fi
    fi

    if (( attempt < attempts )); then
      echo "  Waiting for flight run to finish (${attempt}/${attempts})..." >&2
      sleep "$sleep_seconds"
    fi
  done

  echo "Timed out waiting for flight run to finish." >&2
  if [ -n "${run_number:-}" ] && [ "${run_number:-0}" -gt "$previous_run_number" ]; then
    print_run_logs "$run_number"
  fi
  return 1
}

NAME_SQL=$(sql_string_literal "$NAME")
SCHEDULE_CRON_SQL=$(sql_string_literal "$SCHEDULE_CRON")
ACCESS_TOKEN_NAME_SQL=$(sql_string_literal "$ACCESS_TOKEN_NAME")
SOURCE_FILE_SQL=$(sql_string_literal "$SOURCE_FILE")
REQUIREMENTS_FILE_SQL=$(sql_string_literal "$REQUIREMENTS_FILE")
ACCESS_TOKEN_NAME_ARG=""
if [ -n "$ACCESS_TOKEN_NAME" ]; then
  ACCESS_TOKEN_NAME_ARG="\"access_token_name\" => ${ACCESS_TOKEN_NAME_SQL}, "
fi
UPDATE_SCHEDULE_ARG=""
if [ -n "$SCHEDULE_CRON" ]; then
  UPDATE_SCHEDULE_ARG="\"schedule_cron\" => ${SCHEDULE_CRON_SQL}, "
fi

EXISTING_FLIGHT_ID=$(duckdb md: -csv -noheader -c "SELECT flight_id FROM MD_LIST_FLIGHTS(\"offset\" => 0::UINTEGER, \"limit\" => 1000::UINTEGER) WHERE flight_name = ${NAME_SQL}")
if [ -z "$EXISTING_FLIGHT_ID" ]; then
  EXISTING_FLIGHT_COUNT=0
else
  EXISTING_FLIGHT_COUNT=$(printf "%s\n" "$EXISTING_FLIGHT_ID" | wc -l | tr -d ' ')
fi

SOURCE_CODE_SQL="(SELECT content FROM read_text(${SOURCE_FILE_SQL}))"
REQUIREMENTS_TXT_SQL="(SELECT content FROM read_text(${REQUIREMENTS_FILE_SQL}))"

if (( EXISTING_FLIGHT_COUNT == 0 )); then
  echo "  Creating new flight '${NAME}'..." >&2
  duckdb md: -csv -noheader -c "SET VARIABLE source_code = ${SOURCE_CODE_SQL}; SET VARIABLE requirements_txt = ${REQUIREMENTS_TXT_SQL}; FROM MD_CREATE_FLIGHT(\"schedule_cron\" => ${SCHEDULE_CRON_SQL}, \"flight_secret_names\" => ${SECRET_NAMES_SQL}, \"config\" => ${CONFIG_SQL}, ${ACCESS_TOKEN_NAME_ARG}\"name\" => ${NAME_SQL}, \"source_code\" => getvariable('source_code'), \"requirements_txt\" => getvariable('requirements_txt'));"
  FLIGHT_ID=$(duckdb md: -csv -noheader -c "SELECT flight_id FROM MD_LIST_FLIGHTS(\"offset\" => 0::UINTEGER, \"limit\" => 1000::UINTEGER) WHERE flight_name = ${NAME_SQL}")
elif (( EXISTING_FLIGHT_COUNT == 1 )); then
  echo "  Updating existing flight '${NAME}' (${EXISTING_FLIGHT_ID})..." >&2
  duckdb md: -csv -noheader -c "SET VARIABLE source_code = ${SOURCE_CODE_SQL}; SET VARIABLE requirements_txt = ${REQUIREMENTS_TXT_SQL}; FROM MD_UPDATE_FLIGHT(\"flight_id\" => '${EXISTING_FLIGHT_ID}'::UUID, ${UPDATE_SCHEDULE_ARG}${ACCESS_TOKEN_NAME_ARG}\"name\" => ${NAME_SQL}, \"config\" => ${CONFIG_SQL}, \"source_code\" => getvariable('source_code'), \"flight_secret_names\" => ${SECRET_NAMES_SQL}, \"requirements_txt\" => getvariable('requirements_txt'));"
  FLIGHT_ID="${EXISTING_FLIGHT_ID}"
else
  echo "Error: found ${EXISTING_FLIGHT_COUNT} flights with name '${NAME}'. Expected 0 or 1." >&2
  exit 1
fi

echo "  Deployed flight: ${FLIGHT_ID}" >&2

if [ "$RUN_ON_DEPLOY" = "true" ]; then
  PREVIOUS_RUN_NUMBER=$(latest_run_number)
  echo "  Starting flight run for '${NAME}'..." >&2
  duckdb md: -csv -noheader -c "FROM MD_RUN_FLIGHT(\"config\" => ${CONFIG_SQL}, \"flight_id\" => '${FLIGHT_ID}'::UUID);"
  wait_for_flight_run "$PREVIOUS_RUN_NUMBER"
fi

if [ "$PREVIEW_MODE" = "true" ]; then
  SHARE_URL=""
  if [ -n "$SHARE_NAME" ]; then
    SHARE_NAME_SQL=$(sql_string_literal "$SHARE_NAME")
    SHARE_URL=$(duckdb md: -csv -noheader -c "SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = ${SHARE_NAME_SQL}" || true)
  fi
  if [ -n "$SHARE_URL" ]; then
    echo "| ${NAME} | ${FLIGHT_ID} | ${RUN_ON_DEPLOY} | [Open Share](${SHARE_URL}) |"
  else
    echo "| ${NAME} | ${FLIGHT_ID} | ${RUN_ON_DEPLOY} | Share pending first successful run |"
  fi
fi
