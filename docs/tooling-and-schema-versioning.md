# Tooling and Schema Versioning

MotherDuck Blueprints has two distribution surfaces:

- The template repository gives customer repos a working layout, examples, docs, and customer-facing GitHub workflows.
- Versioned tags in this repository provide both the `md-blueprints` CLI source and the composite action used for schema validation, rendering, planning, deployment, cleanup, update checks, and migrations.

Customers should upgrade the exact CLI and action pins together. They should not need to re-copy this template just to receive validator or deployer fixes.

## CLI and Action Pinning

Generated repositories pin the CLI version in the `Makefile` `CLI_VERSION` variable. `make setup` installs `md-blueprints` from the matching Git tag in this repository; the same wheel and source distribution are published to PyPI and attached to the GitHub Release. Live `plan`, `deploy`, and `cleanup` commands need the deploy extra, which includes the DuckDB Python runtime dependencies needed for MotherDuck connections:

```bash
make setup
make install-deploy
```

Upgrade local tooling by bumping `CLI_VERSION` in `Makefile` and every Blueprints action tag in `.github/workflows/` to the same exact release.

Customer workflows should pin an immutable release tag:

```yaml
- uses: motherduckdb/motherduck-blueprints@v0.4.1
  with:
    command: validate
```

The action installs the CLI from the pinned action checkout. For `plan`, `deploy`, and `cleanup`, it installs `.[deploy]`; validate-only commands stay light.

## Customer Upgrade Loop

The template keeps Dependabot enabled for third-party GitHub Actions. Blueprints Doctor coordinates Blueprints upgrades because the action and local CLI pins must move together.

For local checks around a bump:

```bash
md-blueprints doctor --check-updates
md-blueprints migrate --to latest
md-blueprints validate
make preview-smoke <blueprint-name>
```

The scheduled `Blueprints Doctor` workflow runs `doctor --check-updates` and opens or updates one tracking issue when a release is stale, action and CLI pins drift, or the project schema needs migration.

## Schema Source of Truth

Packaged schemas live under `src/md_blueprints/schemas/v*/`. Repo-local schemas under `schemas/v*/` mirror those files for editors, docs, and agents, but runtime validation uses the packaged schemas.

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
requiredCliVersion: ">=1.3"
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

Each migration is a pure document transform. The command loads `motherduck.yml` and included `blueprint.yml` files, applies the migration path, emits a unified diff, optionally writes files, and revalidates migrated documents against the target schema.

For `schemaVersion: 1`, `md-blueprints migrate --to latest` prints that no migration is needed.

## Release Engineering

Stable `vMAJOR.MINOR.PATCH` tag pushes run the release workflow. The workflow trigger excludes floating tags such as `v0`, requires the tagged commit to be on `main`, and rejects other release-tag shapes:

1. Verify tag, `pyproject.toml`, and `src/md_blueprints/__init__.py` versions match.
2. Build the wheel and source distribution.
3. Smoke test the installed wheel as an internal packaging check.
4. Smoke test the local action wrapper.
5. Generate a reproducible CycloneDX SBOM and attest every release artifact.
6. Verify the generated-template repository, PyPI trusted publisher, and protected release environments.
7. Install the built wheel, generate the customer template with an exact action tag, and push it to `motherduckdb/blueprints-template`.
8. Require the generated repository's triggered workflow to pass against that exact action tag.
9. Publish the wheel and source distribution to PyPI through trusted publishing.
10. Attach the distributions and SBOM to the GitHub Release, then update the compatibility-only floating major alias.

The action installs the tagged checkout directly, generated repositories install local tooling from the matching Git tag, and Python users can install the identical package from PyPI. The floating major tag remains available for compatibility but generated repositories do not depend on it.

One-time template setup: create `motherduckdb/blueprints-template`, mark it as a GitHub template repository, and add a `BLUEPRINTS_TEMPLATE_PUSH_TOKEN` secret that can force-push to that repository. Tagged releases fail before publishing when this setup is missing; the template push is part of the release contract, not an optional best-effort step.

Before creating a release tag:

```bash
make release-check TAG=v0.4.1
make release-external-check
make validate
make mock-test
make package-smoke
make example-smoke
make preview-smoke wikipedia-pageviews
```

## Repository Boundary

This repository now carries the customer template as package data and exposes it through:

```bash
md-blueprints init <dir>
```

That command writes the customer file set and stamps the same exact release into the generated `Makefile` and workflows.

Before the first stable customer handoff, split the generated customer template from tooling:

- Tooling repo: `src/md_blueprints/`, `pyproject.toml`, action wrapper, tests, scripts, CI, release workflow, and changelog.
- Template repo: `motherduck.yml`, typed `flights/`, `dives/`, `guides/`, and `roles/` roots, `projects/`, `shared/`, customer docs, thin Makefile, customer workflows, Dependabot, CODEOWNERS, and `.gitignore`.

The release workflow generates `motherduckdb/blueprints-template` from the built wheel's `md-blueprints init` package data so the stamped action tag, docs, examples, and CLI behavior cannot drift. The tooling repository's own deploy and doctor workflows use the local action checkout; generated customer workflows use the stamped immutable release tag.

## Agent Maintenance Map

| Task | Files |
| --- | --- |
| CLI parsing and exit codes | `src/md_blueprints/cli.py` |
| Customer template generation | `src/md_blueprints/init.py`, `src/md_blueprints/template_repo/` |
| Schema loading and validation | `src/md_blueprints/schema.py`, `src/md_blueprints/schemas/v*/` |
| Template rendering | `src/md_blueprints/template.py` |
| Project manifest and changed detection | `src/md_blueprints/project.py` |
| Plan/deploy/cleanup behavior | `src/md_blueprints/deploy.py` |
| Migration behavior | `src/md_blueprints/migrations.py` |
| Doctor/update checks | `src/md_blueprints/maintenance.py` |
| Editor/docs schema mirror | `schemas/v*/` |
| Local compatibility wrapper | `tools/md_blueprints` |
| GitHub Action wrapper | `action.yml` |
| Internal CI | `.github/workflows/ci.yaml` |
| Release automation | `.github/workflows/release.yaml`, `scripts/package-smoke-test.sh`, `scripts/check-release-version.sh` |
| Customer setup docs | `README.md`, `docs/setup-your-repository.md`, `docs/github-setup.md` |
| Field reference | `docs/blueprint-yml-reference.md` |
| Change record | `CHANGELOG.md` |
