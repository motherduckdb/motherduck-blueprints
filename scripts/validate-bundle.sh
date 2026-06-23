#!/usr/bin/env bash
#
# Validate a Blueprint bundle without contacting MotherDuck.
#
# Usage:
#   ./scripts/validate-bundle.sh <bundle-name>
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUNDLE_NAME="${1:?Usage: validate-bundle.sh <bundle-name>}"
BUNDLE_DIR="${REPO_ROOT}/bundles/${BUNDLE_NAME}"
BLUEPRINT_FILE="${BUNDLE_DIR}/blueprint.json"

if [ ! -f "$BLUEPRINT_FILE" ]; then
  echo "Bundle blueprint not found: $BLUEPRINT_FILE" >&2
  exit 1
fi

jq -e '
  (.name | type == "string" and length > 0)
  and (.title | type == "string" and length > 0)
  and ((.description // "") | type == "string")
  and ((.preview // {}) | type == "object")
  and ((.preview.enabled // false) | type == "boolean")
  and ((.preview.cleanup // true) | type == "boolean")
  and (.flights | type == "array")
  and (.dives | type == "array")
  and ((.flights | length) + (.dives | length) > 0)
  and (.flights | all((.name | type == "string" and length > 0) and ((.path // "") | type == "string")))
  and (.dives | all((.name | type == "string" and length > 0) and ((.path // "") | type == "string")))
' "$BLUEPRINT_FILE" >/dev/null

while IFS= read -r flight; do
  flight_path=$(jq -r '.path // ("flights/" + .name)' <<< "$flight")
  flight_slug="$(basename "$flight_path")"
  if [ ! -d "${REPO_ROOT}/${flight_path}" ]; then
    echo "Bundle references missing Flight path: ${flight_path}" >&2
    exit 1
  fi
  "${SCRIPT_DIR}/validate-flight.sh" "$flight_slug"
done < <(jq -c '.flights[]' "$BLUEPRINT_FILE")

while IFS= read -r dive; do
  dive_path=$(jq -r '.path // ("dives/" + .name)' <<< "$dive")
  dive_slug="$(basename "$dive_path")"
  if [ ! -d "${REPO_ROOT}/${dive_path}" ]; then
    echo "Bundle references missing Dive path: ${dive_path}" >&2
    exit 1
  fi
  if [ ! -f "${REPO_ROOT}/${dive_path}/dive_metadata.json" ]; then
    echo "Dive metadata not found: ${dive_path}/dive_metadata.json" >&2
    exit 1
  fi
  if [ ! -f "${REPO_ROOT}/${dive_path}/${dive_slug}.tsx" ]; then
    echo "Dive source not found: ${dive_path}/${dive_slug}.tsx" >&2
    exit 1
  fi
  jq empty "${REPO_ROOT}/${dive_path}/dive_metadata.json"
done < <(jq -c '.dives[]' "$BLUEPRINT_FILE")

