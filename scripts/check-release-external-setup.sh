#!/usr/bin/env bash
#
# Verify the generated-template repository before publishing a tagged release.
#
set -euo pipefail

TEMPLATE_REPOSITORY="${TEMPLATE_REPOSITORY:-motherduckdb/blueprints-template}"

if [ -z "${TEMPLATE_PUSH_TOKEN:-}" ]; then
  echo "BLUEPRINTS_TEMPLATE_PUSH_TOKEN is not configured." >&2
  echo "Create ${TEMPLATE_REPOSITORY}, mark it as a template repository, and add a token that can force-push to it." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required to verify ${TEMPLATE_REPOSITORY}." >&2
  exit 1
fi

repo_json="$(GH_TOKEN="$TEMPLATE_PUSH_TOKEN" gh api "repos/${TEMPLATE_REPOSITORY}" 2>/dev/null)" || {
  echo "Could not read ${TEMPLATE_REPOSITORY} with BLUEPRINTS_TEMPLATE_PUSH_TOKEN." >&2
  echo "Create the repository and grant the token access before publishing." >&2
  exit 1
}

python3 - "$TEMPLATE_REPOSITORY" "$repo_json" <<'PY'
from __future__ import annotations

import json
import sys

repository = sys.argv[1]
payload = json.loads(sys.argv[2])
if payload.get("is_template") is not True:
    raise SystemExit(f"{repository} exists but is not marked as a GitHub template repository")
if payload.get("permissions", {}).get("push") is not True:
    raise SystemExit(
        f"BLUEPRINTS_TEMPLATE_PUSH_TOKEN can read {repository}, but cannot push to it. "
        "Grant Contents: Read and write access to the template repository and approve any pending org request."
    )
print(f"Template repository OK: {repository}")
PY
