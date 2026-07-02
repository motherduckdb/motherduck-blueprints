#!/usr/bin/env bash
#
# Verify one-time external release infrastructure before publishing a tagged release.
#
set -euo pipefail

TEMPLATE_REPOSITORY="${TEMPLATE_REPOSITORY:-motherduckdb/blueprints-template}"
PYPI_PROJECT="${PYPI_PROJECT:-md-blueprints}"
PYPI_JSON_BASE_URL="${PYPI_JSON_BASE_URL:-https://pypi.org/pypi}"
ALLOW_PYPI_PENDING_PUBLISHER="${ALLOW_PYPI_PENDING_PUBLISHER:-1}"
export PYPI_JSON_BASE_URL ALLOW_PYPI_PENDING_PUBLISHER

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
print(f"Template repository OK: {repository}")
PY

python3 - "$PYPI_PROJECT" <<'PY'
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

project = sys.argv[1]
base_url = os.environ["PYPI_JSON_BASE_URL"].rstrip("/")
allow_pending = os.environ["ALLOW_PYPI_PENDING_PUBLISHER"] == "1"
url = f"{base_url}/{project}/json"
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    if exc.code == 404:
        if allow_pending:
            print(
                f"PyPI project {project!r} is not registered yet; assuming a pending trusted publisher "
                "is configured to create it on first publish."
            )
            raise SystemExit(0) from exc
        raise SystemExit(
            f"PyPI project {project!r} is not registered. Register a pending trusted publisher "
            "for this repository, release.yaml, and the pypi environment before tagging a release."
        ) from exc
    raise

print(f"PyPI project OK: {payload['info']['name']}")
PY
