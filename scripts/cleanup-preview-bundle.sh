#!/usr/bin/env bash
#
# Delete preview resources for a Blueprint bundle.
#
# Usage:
#   ./scripts/cleanup-preview-bundle.sh <bundle-name> <branch-name>
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUNDLE_NAME="${1:?Usage: cleanup-preview-bundle.sh <bundle-name> <branch-name>}"
PREVIEW_BRANCH="${2:?Usage: cleanup-preview-bundle.sh <bundle-name> <branch-name>}"
BUNDLE_DIR="${REPO_ROOT}/bundles/${BUNDLE_NAME}"
BLUEPRINT_FILE="${BUNDLE_DIR}/blueprint.json"

if [ ! -f "$BLUEPRINT_FILE" ]; then
  echo "Bundle blueprint not found: $BLUEPRINT_FILE" >&2
  exit 1
fi

if [ "$(jq -er '.preview.cleanup // true' "$BLUEPRINT_FILE")" != "true" ]; then
  echo "Preview cleanup disabled for bundle '${BUNDLE_NAME}'; skipping."
  exit 0
fi

while IFS= read -r dive; do
  dive_path=$(jq -r '.path // ("dives/" + .name)' <<< "$dive")
  dive_slug="$(basename "$dive_path")"
  "${SCRIPT_DIR}/cleanup-preview-dive.sh" "$dive_slug" "$PREVIEW_BRANCH"
done < <(jq -c '.dives[]' "$BLUEPRINT_FILE")

while IFS= read -r flight; do
  flight_path=$(jq -r '.path // ("flights/" + .name)' <<< "$flight")
  flight_slug="$(basename "$flight_path")"
  "${SCRIPT_DIR}/cleanup-preview-flight.sh" "$flight_slug" "$PREVIEW_BRANCH"
done < <(jq -c '.flights[]' "$BLUEPRINT_FILE")

