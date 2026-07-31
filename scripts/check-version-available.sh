#!/usr/bin/env bash
# Fail when an unreleased branch reuses a package version that is already public.
set -euo pipefail

REPOSITORY="${GITHUB_REPOSITORY:-motherduckdb/motherduck-blueprints}"
PYPI_JSON_BASE_URL="${PYPI_JSON_BASE_URL:-https://pypi.org/pypi}"
PYPI_PROJECT="${PYPI_PROJECT:-md-blueprints}"

version="$(python3 - <<'PY'
import pathlib
import tomllib

payload = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
print(payload["project"]["version"])
PY
)"

set +e
release_result="$(gh api "repos/${REPOSITORY}/releases/tags/v${version}" 2>&1)"
release_status=$?
set -e
if [ "$release_status" -eq 0 ]; then
  echo "Version ${version} already has a GitHub Release; bump the package version before merging more changes." >&2
  exit 1
fi
if [[ "$release_result" != *"HTTP 404"* ]]; then
  echo "Could not verify GitHub Release availability for v${version}: ${release_result}" >&2
  exit 1
fi

status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${PYPI_JSON_BASE_URL%/}/${PYPI_PROJECT}/${version}/json")"
case "$status" in
  404)
    ;;
  200)
    echo "Version ${version} is already published on PyPI; bump the package version before merging more changes." >&2
    exit 1
    ;;
  *)
    echo "Could not verify md-blueprints ${version} availability on PyPI (HTTP ${status})." >&2
    exit 1
    ;;
esac

echo "Version available for future release: ${version}"
