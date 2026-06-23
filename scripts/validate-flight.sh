#!/usr/bin/env bash
#
# Validate a flight folder without contacting MotherDuck.
#
# Usage:
#   ./scripts/validate-flight.sh <flight-folder-name>
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FLIGHT_NAME="${1:?Usage: validate-flight.sh <flight-folder-name>}"
FLIGHT_DIR="${REPO_ROOT}/flights/${FLIGHT_NAME}"
METADATA_FILE="${FLIGHT_DIR}/flight_metadata.json"
SOURCE_FILE="${FLIGHT_DIR}/flight.py"
REQUIREMENTS_FILE="${FLIGHT_DIR}/requirements.txt"

if [ ! -d "$FLIGHT_DIR" ]; then
  echo "Flight folder not found: $FLIGHT_DIR" >&2
  exit 1
fi

for file in "$METADATA_FILE" "$SOURCE_FILE" "$REQUIREMENTS_FILE"; do
  if [ ! -f "$file" ]; then
    echo "Required file not found: $file" >&2
    exit 1
  fi
done

jq -e '
  (.name | type == "string" and length > 0)
  and (.scheduleCron == null or (.scheduleCron | type == "string"))
  and (.accessTokenName == null or (.accessTokenName | type == "string"))
  and ((.secrets // []) | type == "array")
  and ((.secrets // []) | all(type == "string"))
  and ((.config // {}) | type == "object")
  and ((.config // {}) | to_entries | all(.value | type == "string"))
  and ((.runOnDeploy // false) | type == "boolean")
  and ((.preview // {}) | type == "object")
  and ((.preview.enabled // false) | type == "boolean")
  and ((.preview.runOnDeploy // false) | type == "boolean")
  and ((.preview.cleanupDatabase // false) | type == "boolean")
  and ((.preview.cleanupShare // true) | type == "boolean")
  and ((.preview.config // {}) | type == "object")
  and ((.preview.config // {}) | to_entries | all(.value | type == "string"))
' "$METADATA_FILE" >/dev/null

python3 - "$SOURCE_FILE" <<'PY'
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
ast.parse(path.read_text(), filename=str(path))
PY
