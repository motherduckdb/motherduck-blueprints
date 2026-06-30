# Tooling and Schema Versioning

MotherDuck Blueprints has two separate distribution surfaces:

- The template repository gives new customer repos a working starting layout, examples, docs, and GitHub workflows.
- The `md-blueprints` package is the active contract for schema validation, rendering, planning, deployment, cleanup, and migrations.

After a customer creates a repository from the template, normal upgrades should come from the package or GitHub Action version. Customers should not need to pull a fresh copy of this template just to get new validator behavior or a syntax migration.

## Package and Action Pinning

Until a package index is chosen, pin the local CLI by installing the wheel attached to the matching GitHub Release:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install ./md_blueprints-0.2.0-py3-none-any.whl
.venv/bin/md-blueprints validate
```

The repository also exposes a composite GitHub Action wrapper. Customer workflows should pin the action version. The action installs the matching CLI from the pinned action checkout:

```yaml
- uses: motherduckdb/motherduck-blueprints@v1
  with:
    command: validate
```

If the CLI is later published to PyPI or a private package index, local installs can move to the equivalent package pin, for example `md-blueprints==1.x.y`.

If the CLI and action are later extracted into a dedicated repository, that action can be republished under a narrower name such as `motherduckdb/blueprints-action@v1`.

Live `plan`, `deploy`, and `cleanup` commands still require DuckDB with MotherDuck support and the configured MotherDuck token env var.

## Schema Source of Truth

The packaged CLI is the source of truth for supported schema versions. Repo-local files under `schemas/` are kept as an editor, documentation, and LLM reference mirror. They must stay in sync with the packaged schemas, but the CLI should validate with its packaged schemas so customer behavior follows the pinned package version.

Use:

```bash
md-blueprints doctor
```

`doctor` reports the CLI version, supported schema versions, detected project schema versions, validation status, DuckDB availability, and whether the local `schemas/` mirror matches the packaged schemas.

## Keeping Customer Repos in Sync

Customer repositories should treat their blueprint files as project-owned source and `md-blueprints` as the versioned MotherDuck contract.

Do this:

- Pin the GitHub Action tag used by CI.
- Pin local CLI installs to the same released artifact when reproducing CI locally.
- Keep `schemaVersion` in `motherduck.yml` and `blueprint.yml` files explicit.
- Run `md-blueprints doctor` before and after a CLI/action upgrade.
- Run `md-blueprints migrate --to latest` before accepting a breaking schema change.

Do not do this:

- Do not ask customers to pull a fresh copy of this template just to receive validator or deployer fixes.
- Do not silently change accepted manifest behavior without a package/action version bump.
- Do not require a schema migration for purely additive fields.
- Do not make repo-local `schemas/` files the runtime validation authority.

The normal customer upgrade loop is:

```bash
md-blueprints doctor
md-blueprints migrate --to latest
md-blueprints validate
make preview-smoke <blueprint-name>
```

For customer CI, the equivalent loop is action-version bump, pull request validation, preview deploy, then production deploy after merge.

## Schema Change Policy

Additive MotherDuck features should be backwards compatible:

- Add optional fields to the packaged schema.
- Keep existing `schemaVersion: 1` manifests valid.
- Release as a minor package/action version.

Breaking changes require:

- A new `schemaVersion`.
- A deprecation window where the CLI can still validate the previous schema version.
- A migration command before the new syntax is required.

Run migrations as a dry run first:

```bash
md-blueprints migrate --to latest
```

Apply generated changes only after reviewing the diff:

```bash
md-blueprints migrate --to latest --write
md-blueprints validate
```

CI should fail only when the pinned CLI does not support the repository's declared `schemaVersion`, or when validation fails for that pinned contract.

## Adding an Additive Feature

Use this path when MotherDuck adds a new resource option or target policy that old repos can ignore.

1. Add the optional field to `src/md_blueprints/schemas/*.json`.
2. Mirror the schema change under top-level `schemas/`.
3. Update render/deploy behavior in `src/md_blueprints/cli.py`.
4. Update `docs/blueprint-yml-reference.md` with the field, default, and rendered validation rules.
5. Update fixtures or examples only when the feature needs a concrete example.
6. Add or update mock tests in `scripts/mock-test.sh`.
7. Bump the package minor version.
8. Run:

```bash
make validate
make mock-test
make package-smoke
make example-smoke
make preview-smoke wikipedia-pageviews
```

Existing `schemaVersion: 1` projects should still validate unless the feature intentionally requires a breaking schema.

## Adding a Breaking Schema Version

Use this path when a manifest field is renamed, removed, moved, or given incompatible semantics.

1. Add the new schema version to the packaged schemas.
2. Keep support for the previous schema version for a deprecation window.
3. Teach `md-blueprints migrate --from <old> --to <new>` how to produce a readable diff.
4. Keep migration dry-run by default; write only with `--write`.
5. Add fixtures for old and new schema versions.
6. Add tests for validation, migration diff output, migration write output, and idempotency.
7. Document old syntax, new syntax, and generated migration behavior.
8. Bump the package major version only when customers must make a breaking update.

Migration output must be reviewable in a pull request. Do not mutate Flight or Dive source files unless the schema change cannot be represented in manifests alone.

## Migration Command Contract

`md-blueprints migrate` is intentionally conservative:

- Dry-run by default.
- Emits unified diffs when changes are needed.
- Uses `--write` for filesystem changes.
- Accepts `--from` to guard against migrating an unexpected starting version.
- Accepts `--to latest` for the common upgrade path.
- Leaves customer project code alone unless the migration explicitly documents why code edits are required.

For `schemaVersion: 1`, `md-blueprints migrate --to latest` should print that no migration is needed.

## Update Checks

For controlled rollout environments, set `MD_BLUEPRINTS_LATEST_VERSION` and run:

```bash
md-blueprints check-updates
```

Without that env var, the command reports the installed version but does not contact a package registry. This keeps CI deterministic and lets MotherDuck decide how aggressively to enforce upgrades.

## Publish Target

The first supported publish target is GitHub Releases in this repository.

On a `v*` tag, the release workflow:

1. Verifies the tag version matches `pyproject.toml` and `src/md_blueprints/__init__.py`.
2. Builds the wheel and source distribution.
3. Installs the wheel into a clean virtualenv and validates this repository.
4. Smokes the local GitHub Action wrapper.
5. Uploads the wheel and source distribution as GitHub Actions artifacts.
6. Attaches the wheel and source distribution to a GitHub Release for that tag.

This deliberately avoids a PyPI or private-registry dependency for the first release. PyPI or an internal package registry can be added later once package-name ownership, credentials, and customer installation policy are settled.

Customer repositories should normally use the action tag:

```yaml
- uses: motherduckdb/motherduck-blueprints@v1
  with:
    command: validate
```

For local CLI installation from GitHub Release artifacts, download the wheel from the matching release and install it into a virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install ./md_blueprints-0.2.0-py3-none-any.whl
.venv/bin/md-blueprints validate
```

## Release Artifacts

Internal CI builds the wheel and source distribution, installs the wheel into a clean virtualenv, validates this repository through the installed command, checks packaged schema resources, and smokes the local GitHub Action wrapper. Tagged `v*` pushes publish those same artifacts to GitHub Releases.

## Release Checklist

Before creating a release tag:

1. Update `pyproject.toml` and `src/md_blueprints/__init__.py` to the same version.
2. Update `CHANGELOG.md`.
3. Run the release version check:

```bash
make release-check TAG=v0.2.0
```

4. Run the full local validation set:

```bash
make validate
make mock-test
make package-smoke
make example-smoke
make preview-smoke wikipedia-pageviews
```

5. Create and push a matching tag:

```bash
git tag v0.2.0
git push origin v0.2.0
```

The release workflow refuses mismatched tags, for example `v0.2.1` pointing at package version `0.2.0`.

## Agent Maintenance Map

For future agents, these are the important files:

| Task | Files |
| --- | --- |
| CLI behavior | `src/md_blueprints/cli.py` |
| Packaged schema source | `src/md_blueprints/schemas/*.json` |
| Editor/docs schema mirror | `schemas/*.json` |
| Local compatibility wrapper | `tools/md_blueprints` |
| GitHub Action wrapper | `action.yml` |
| Internal CI | `.github/workflows/ci.yaml` |
| Release artifacts | `.github/workflows/release.yaml`, `scripts/package-smoke-test.sh`, `scripts/check-release-version.sh` |
| Customer setup docs | `README.md`, `docs/setup-your-repository.md`, `docs/github-setup.md` |
| Field reference | `docs/blueprint-yml-reference.md` |
| Change record | `CHANGELOG.md` |

## Repository Boundary

Keep the template, CLI package, and GitHub Action wrapper in this repository for now.

That is intentional:

- The CLI is validated against this repository's example blueprints, fixtures, schemas, workflows, and generated starter package.
- The action currently installs the package from the action checkout, so the action tag and package source stay aligned.
- Customers need one starting point while the public contract is still settling.

Revisit a split only after the CLI/action has an independent release cadence and at least one real customer repository pins to the action or package. At that point, move `src/md_blueprints/`, `pyproject.toml`, `action.yml`, package tests, and release workflows into a dedicated CLI/action repository, then keep this repository as the starter template.

## Post-Merge CLI Modularization

`src/md_blueprints/cli.py` is currently a direct port of the deploy engine. That kept this package conversion reviewable and reduced behavioral drift.

After this release lands, split it into smaller modules:

- `schema.py` for packaged schema loading and validation.
- `template.py` for `${...}` rendering and variable precedence.
- `project.py` for manifests, blueprint selection, rendering, and change detection.
- `deploy.py` for live MotherDuck planning, deploy, cleanup, and SQL helpers.
- `commands.py` or `cli.py` for argparse wiring and process exit behavior.

Add focused unit tests around each module before making larger schema migrations.
