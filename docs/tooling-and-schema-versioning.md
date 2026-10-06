# Tooling and Schema Versioning

MotherDuck Blueprints has two distribution surfaces:

- The template repository gives customer repos a working layout, examples, docs, and customer-facing GitHub workflows.
- Versioned tags in this repository provide both the `md-blueprints` CLI source and the composite action used for schema validation, rendering, planning, deployment, cleanup, update checks, and migrations.

Customers should upgrade the exact CLI, reusable workflow, and any direct action pins together. They should not need to re-copy this template just to receive validator or deployer fixes.

## CLI and Action Pinning

Generated repositories pin the Blueprints CLI version in the `Makefile` `CLI_VERSION` variable. `make setup` installs `md-blueprints` from the matching Git tag in this repository. The wheel and source distribution are attached to the GitHub Release. A PyPI project or publisher is not required to distribute the action or CLI.

For export or live commands, install the supported native MotherDuck CLI:

```bash
make install-deploy
```

The native CLI bundles its DuckDB runtime. Its tested version is maintained inside the Blueprints package, so customers do not need another version pin. `motherduck upgrade` updates a local CLI independently. CI installs the version tested with its Blueprints release.

Run `make upgrade` to update `CLI_VERSION` in `Makefile` and every Blueprints workflow or direct action reference to the same exact release. Review the diff and open a pull request. Customer triggers, permissions, and other workflow settings are preserved.

Customer workflows should pin an immutable release tag:

```yaml
- uses: motherduckdb/motherduck-blueprints@v0.7.5
  with:
    command: validate
```

The action installs Blueprints from the pinned action checkout. Import also installs the native MotherDuck CLI using the official checksum-verifying installer. Deployment, planning, verification, and cleanup install `md-blueprints[deploy]` and use the Python backend, avoiding a CLI process per SQL call. Validation needs neither a token nor the native CLI. Locally, `MD_BLUEPRINTS_SQL_BACKEND=duckdb` explicitly selects the Python backend after installing that extra.

## Customer Upgrade Loop

Blueprints maintains third-party actions inside its reusable workflows. The template keeps Dependabot enabled for any customer-added GitHub Actions and the local preview dependencies. Blueprints Doctor coordinates Blueprints upgrades because workflow and local CLI pins must move together.

For local checks around a bump:

```bash
.venv/bin/md-blueprints doctor --check-updates
.venv/bin/md-blueprints migrate --to latest
make validate
make preview-smoke <blueprint-name>
```

The scheduled `Blueprints Doctor` workflow runs `doctor --check-updates` and opens or updates one tracking issue when a release is stale, action and CLI pins drift, or the project schema needs migration.

Doctor also reports deployment-model drift. Repository-level `MOTHERDUCK_TOKEN` workflows are deprecated: generated workflows now select the GitHub Environment declared by each target and read that environment's `MOTHERDUCK_TOKEN`. Existing pre-1.0 workflows remain executable during the compatibility window, but the legacy secret model is scheduled for removal at the next major release.

## Existing customer workflows

Existing expanded workflows and direct action calls continue to work. `make upgrade` updates their pins but does not replace customer-authored jobs.

To adopt the shorter callers after a release includes them, generate a fresh template in a separate empty directory with that release's CLI. Compare its `.github/workflows/` files with yours. `make upgrade` does not add workflows that are new in a release, such as `prepare_guide_context.yaml`. `make doctor` lists any that are missing. Copy the callers while preserving any custom event filters, branch names, and permissions. Keep customized jobs as direct action workflows if they need extra steps. Review the migration in a pull request, confirm the preview and plan, then merge.

Reusable workflow definitions are released from this tooling repository's `.github/workflows/reusable_*.yaml` files. Their internal action references must match the package release. New reusable definitions are available to customer callers only after that release is published.

## Schema Source of Truth

Runtime validation uses the schemas packaged with the installed `md-blueprints` release. The `schemas/v*/` files in your repository are copies of the same schemas for editors, docs, and agents.

Current constants:

```python
SUPPORTED_SCHEMA_VERSIONS = {1}
LATEST_SCHEMA_VERSION = 1
```

If a project declares a schema version this CLI does not support, validation fails with a message that names the installed CLI version and tells the user whether to bump the action pin or run `migrate --to latest`.

Unknown fields stay invalid, but the validator explains the two likely causes: typo, or field introduced in a newer `md-blueprints` release.

## requiredCliVersion

Root manifests may declare a minimum CLI requirement:

```yaml
schemaVersion: 1
requiredCliVersion: ">=0.4.3"
```

Validation checks this before schema details and fails with a direct pin-bump message when the installed CLI is too old. Use this for behavioral requirements that cannot be expressed as schema shape alone.

## Schema Change Policy

| action / CLI | schemaVersions supported | upgrade path |
| --- | --- | --- |
| v0.x | 1 | Current pre-1.0 contract |
| v1.x | 1 | First stable customer contract |
| v2.x | 1 deprecated, removed in v3; 2 current | Run `doctor` and `migrate --to latest` before bumping |

Minor releases are additive. Add optional fields to the latest packaged schema, keep existing `schemaVersion: 1` manifests valid, and document the field version so old-CLI errors are actionable.

Major releases can introduce a new `schemaVersion`. Keep the previous version supported for a deprecation window, warn in `doctor`, and remove only in the next major.

## Migrations

`md-blueprints migrate` is dry-run by default and writes only with `--write`.

The internal migration contract is:

```python
MIGRATIONS: dict[tuple[int, int], Callable[[dict[str, object]], dict[str, object]]] = {}
```

Each migration is a pure document transform. The command loads `motherduck.yml` and included `blueprint.yml` files, applies the migration path, validates every migrated document against the target schema, and emits a unified diff. With `--write`, files are written only after every document passes validation. Includes stay within the repository, overlapping matches are deduplicated, and every document must declare an integer `schemaVersion`. File writes are sequential; an operating-system write failure can still leave a partial migration.

For `schemaVersion: 1`, `md-blueprints migrate --to latest` prints that no migration is needed.

## Update tooling together

Run `make upgrade` in a generated repository to update `CLI_VERSION` and every MotherDuck Blueprints action pin to the latest stable release. The command prints a diff for review and leaves source code, workflow settings, and other actions intact. Run `make validate` afterward and submit the diff through a pull request.

Use `make upgrade VERSION=X.Y.Z` for a specific release. For a read-only preview, run `.venv/bin/md-blueprints upgrade --to X.Y.Z`; add `--write` to apply it. This updates version pins only, not manifests or workflow structure; check the linked release notes for any migration steps.
