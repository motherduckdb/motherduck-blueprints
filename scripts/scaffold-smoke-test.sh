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
  --exclude .dive-preview/.env \
  --exclude .dive-preview/dist \
  --exclude .dive-preview/node_modules \
  "$REPO_ROOT/" "$SCAFFOLD_ROOT/"

echo "==> Creating generated blueprint example"
make -C "$SCAFFOLD_ROOT" new-blueprint "$EXAMPLE_NAME"
test -f "$SCAFFOLD_ROOT/blueprints/$EXAMPLE_NAME/README.md"

if grep -R "__BLUEPRINT_NAME__\|__DATABASE_NAME__" "$SCAFFOLD_ROOT/blueprints/$EXAMPLE_NAME"; then
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

echo "==> Building generated blueprint Dive"
make -C "$SCAFFOLD_ROOT" preview-smoke "$EXAMPLE_NAME"

echo "==> Destroying generated blueprint example"
rm -rf "$SCAFFOLD_ROOT/blueprints/$EXAMPLE_NAME"
test ! -e "$SCAFFOLD_ROOT/blueprints/$EXAMPLE_NAME"
make -C "$SCAFFOLD_ROOT" validate

echo "Generated blueprint example smoke test passed."
