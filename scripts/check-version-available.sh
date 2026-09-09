#!/usr/bin/env bash
# Fail when an unreleased branch reuses a package version that is already public.
set -euo pipefail

REPOSITORY="${GITHUB_REPOSITORY:-motherduckdb/motherduck-blueprints}"

version="$(python3 - <<'PY'
import pathlib
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

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

set +e
tag_result="$(gh api "repos/${REPOSITORY}/git/ref/tags/v${version}" 2>&1)"
tag_status=$?
set -e
if [ "$tag_status" -eq 0 ]; then
  echo "Version ${version} already has a GitHub tag; choose a new version instead of replacing the tag." >&2
  exit 1
fi
if [[ "$tag_result" != *"HTTP 404"* ]]; then
  echo "Could not verify GitHub tag availability for v${version}: ${tag_result}" >&2
  exit 1
fi

echo "Version available for future release: ${version}"
