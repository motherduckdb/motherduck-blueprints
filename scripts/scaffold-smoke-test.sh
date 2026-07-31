#!/usr/bin/env bash
#
# Create, validate, build, and destroy a generated blueprint package.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"
SCAFFOLD_ROOT="${TMP_DIR}/repo"
EXAMPLE_NAME="${1:-ci-generated-example}"
DATABASE_NAME="${EXAMPLE_NAME//-/_}"
BRANCH_NAME="feature/generated-example"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

rsync -a \
  --exclude .git \
  --exclude .venv \
  --exclude .dive-preview/.env \
  --exclude .dive-preview/dist \
  --exclude .dive-preview/node_modules \
  "$REPO_ROOT/" "$SCAFFOLD_ROOT/"

echo "==> Creating generated blueprint example"
make -C "$SCAFFOLD_ROOT" new-blueprint "$EXAMPLE_NAME"
test -f "$SCAFFOLD_ROOT/projects/$EXAMPLE_NAME/README.md"
test -f "$SCAFFOLD_ROOT/projects/$EXAMPLE_NAME/guide.md"

echo "==> Creating typed and edge-case blueprint examples"
make -C "$SCAFFOLD_ROOT" new-flight true
make -C "$SCAFFOLD_ROOT" new-dive 1-dashboard INPUT=true.data
make -C "$SCAFFOLD_ROOT" new-guide on
make -C "$SCAFFOLD_ROOT" new-role null
make -C "$SCAFFOLD_ROOT" new-project 123

if grep -R \
  "__BLUEPRINT_NAME__\|__BLUEPRINT_TITLE__\|__DATABASE_NAME__" \
  "$SCAFFOLD_ROOT/projects/$EXAMPLE_NAME" \
  "$SCAFFOLD_ROOT/flights/true" \
  "$SCAFFOLD_ROOT/dives/1-dashboard" \
  "$SCAFFOLD_ROOT/guides/on" \
  "$SCAFFOLD_ROOT/roles/null" \
  "$SCAFFOLD_ROOT/projects/123"; then
  echo "Generated blueprint still contains template placeholders" >&2
  exit 1
fi

echo "==> Validating generated blueprint example"
make -C "$SCAFFOLD_ROOT" validate
"$SCAFFOLD_ROOT/tools/md_blueprints" render \
  --root "$SCAFFOLD_ROOT" \
  --target preview \
  --branch "$BRANCH_NAME" \
  --blueprints "$EXAMPLE_NAME" > "$TMP_DIR/render.out"
grep -q "${DATABASE_NAME}_preview_feature_generated_example" "$TMP_DIR/render.out"
grep -q "\"alias\": \"${DATABASE_NAME}\"" "$TMP_DIR/render.out"
grep -q '"scheduleCron": ""' "$TMP_DIR/render.out"
"$SCAFFOLD_ROOT/tools/md_blueprints" render \
  --root "$SCAFFOLD_ROOT" \
  --target preview \
  --branch "$BRANCH_NAME" \
  --blueprints "123" > "$TMP_DIR/numeric-render.out"
grep -q "_123_preview_feature_generated_example" "$TMP_DIR/numeric-render.out"
grep -q '"alias": "_123"' "$TMP_DIR/numeric-render.out"

echo "==> Building generated blueprint Dive"
make -C "$SCAFFOLD_ROOT" preview-smoke "$EXAMPLE_NAME"

echo "==> Building generated external-share Dive"
"$SCAFFOLD_ROOT/tools/md_blueprints" new dive "external-share-example" \
  --root "$SCAFFOLD_ROOT" \
  --url "md:_share/example/00000000-0000-0000-0000-000000000000"
make -C "$SCAFFOLD_ROOT" preview-smoke "external-share-example"

echo "==> Building generated input-backed Dive"
make -C "$SCAFFOLD_ROOT" preview-smoke "1-dashboard"

echo "==> Building generated numeric-leading project Dive"
make -C "$SCAFFOLD_ROOT" preview-smoke "123"

echo "==> Destroying generated blueprint example"
rm -rf "$SCAFFOLD_ROOT/projects/$EXAMPLE_NAME"
rm -rf "$SCAFFOLD_ROOT/dives/external-share-example"
rm -rf "$SCAFFOLD_ROOT/flights/true"
rm -rf "$SCAFFOLD_ROOT/dives/1-dashboard"
rm -rf "$SCAFFOLD_ROOT/guides/on"
rm -rf "$SCAFFOLD_ROOT/roles/null"
rm -rf "$SCAFFOLD_ROOT/projects/123"
test ! -e "$SCAFFOLD_ROOT/projects/$EXAMPLE_NAME"
test ! -e "$SCAFFOLD_ROOT/dives/external-share-example"
make -C "$SCAFFOLD_ROOT" validate

echo "Generated blueprint example smoke test passed."
