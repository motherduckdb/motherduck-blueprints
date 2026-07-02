# Tooling and Schema Versioning

MotherDuck Blueprints has two distribution surfaces:

- The template repository gives customer repos a working layout, examples, docs, and customer-facing GitHub workflows.
- The `md-blueprints` package and composite action are the active contract for schema validation, rendering, planning, deployment, cleanup, update checks, and migrations.

Customers should upgrade by bumping the package or action pin. They should not need to re-copy this template just to receive validator or deployer fixes.

## Package and Action Pinning

Generated repositories pin the CLI version in the `Makefile` `CLI_VERSION` variable, which `make setup` installs from PyPI. Live `plan`, `deploy`, and `cleanup` commands need the deploy extra, which includes the DuckDB Python runtime dependencies needed for MotherDuck connections:

```bash
make setup
make install-deploy
```

Upgrade by bumping `CLI_VERSION` in `Makefile` together with the action tag in `.github/workflows/`.

Customer workflows should pin the action major. While the package is `0.x`, the floating major tag is `v0`; switch examples to `v1` when the first stable customer contract is cut.

```yaml
- uses: motherduckdb/motherduck-blueprints@v0
  with:
    command: validate
```

The action installs the CLI from the pinned action checkout. For `plan`, `deploy`, and `cleanup`, it installs `.[deploy]`; validate-only commands stay light.

## Customer Upgrade Loop

The template includes Dependabot for GitHub Actions. Dependabot opens PRs that bump the action pin, the customer preview workflow validates the bump, and the customer merges when the preview is good.

For local checks around a bump:

```bash
md-blueprints doctor --check-updates
md-blueprints migrate --to latest
md-blueprints validate
make preview-smoke <blueprint-name>
```

The scheduled `Blueprints Doctor` workflow runs `doctor --check-updates` and opens or updates one tracking issue when the action is stale or the project schema needs migration.

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

Tagged `v*` pushes run the release workflow:

1. Verify tag, `pyproject.toml`, and `src/md_blueprints/__init__.py` versions match.
2. Build the wheel and source distribution.
3. Smoke test the installed wheel.
4. Smoke test the local action wrapper.
5. Attach artifacts to the matching GitHub Release.
6. Publish to PyPI through trusted publishing.
7. Force-update the floating major tag, for example `v0`.
8. Generate the customer template with the built wheel and force-push it to `motherduckdb/blueprints-template` when `BLUEPRINTS_TEMPLATE_PUSH_TOKEN` is configured.

One-time PyPI setup: register the `md-blueprints` project and add a trusted publisher for this repository, `release.yaml`, and the `pypi` environment. Tagged releases run `scripts/check-release-external-setup.sh` before publishing so a missing project or trusted-publishing setup fails with an actionable error.

One-time template setup: create `motherduckdb/blueprints-template`, mark it as a GitHub template repository, and add a `BLUEPRINTS_TEMPLATE_PUSH_TOKEN` secret that can force-push to that repository. Tagged releases fail before publishing when this setup is missing; the template push is part of the release contract, not an optional best-effort step.

Before creating a release tag:

```bash
make release-check TAG=v0.3.0
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

That command writes the customer file set, stamps the installed CLI version into the generated `Makefile`, and stamps the current major action tag into generated workflows.

Before the first stable customer handoff, split the generated customer template from tooling:

- Tooling repo: `src/md_blueprints/`, `pyproject.toml`, action wrapper, tests, scripts, CI, release workflow, and changelog.
- Template repo: `motherduck.yml`, `blueprints/`, `context/`, customer docs, thin Makefile, customer workflows, Dependabot, CODEOWNERS, and `.gitignore`.

The release workflow generates `motherduckdb/blueprints-template` from the same `md-blueprints init` package data so the stamped action tag, docs, examples, and CLI behavior cannot drift. The tooling repository's own deploy and doctor workflows use the local action checkout so pre-release PRs can validate before the floating major tag exists; generated customer workflows use the stamped public action tag.

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
| Release artifacts | `.github/workflows/release.yaml`, `scripts/package-smoke-test.sh`, `scripts/check-release-version.sh` |
| Customer setup docs | `README.md`, `docs/setup-your-repository.md`, `docs/github-setup.md` |
| Field reference | `docs/blueprint-yml-reference.md` |
| Change record | `CHANGELOG.md` |
