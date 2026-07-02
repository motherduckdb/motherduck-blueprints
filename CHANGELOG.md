# Changelog

All notable changes to this repository are documented here.

Update this file in every pull request. Add entries under `Unreleased` until the change is released or merged into a reusable template.

## Unreleased

### Added

- Added Dependabot configuration for customer workflow action updates.
- Added a scheduled Blueprints Doctor workflow that opens a tracking issue when the pinned action or schema needs attention.
- Added `md-blueprints init <dir>` and packaged customer-template assets for generated repository setup.
- Added `requiredCliVersion` support in the root manifest.
- Added versioned packaged schema directories under `src/md_blueprints/schemas/v1/` with mirrored editor schemas under `schemas/v1/`.
- Added pytest coverage and strict mypy checking for the packaged CLI modules.
- Added deploy, template-rendering, include-glob, and CLI exit-code unit coverage for the module split.
- Added migration registry tests that simulate a future schema migration diff, write, and idempotency flow.
- Added the versioned `md-blueprints` Python package, console command, packaged schema resources, and GitHub Action wrapper.
- Added `md-blueprints doctor`, `md-blueprints check-updates`, and `md-blueprints migrate --to latest` as schema maintenance surfaces.
- Added tooling and schema versioning documentation for package pinning, compatibility policy, and customer upgrade flow.
- Added package and release-artifact smoke tests for the wheel, sdist, packaged schemas, and local GitHub Action wrapper.
- Added release external-setup preflight checks for the PyPI project and generated template repository.
- Added release version checks and GitHub Release publishing for tagged package artifacts.
- Added PyPI trusted publishing to the release workflow.
- Added a generated-template drift test that compares `md-blueprints init` output with the mirrored repository paths.

### Added

- Added `CONTRIBUTING.md` and `SECURITY.md`, including guidance that pull requests belong in this repository rather than the generated `blueprints-template` repository.
- Added a `make install-deploy` target to the tooling repository Makefile, matching the generated customer Makefile.
- Added mock deployment coverage for live Flight signatures: named `MD_RUN_FLIGHT`/`MD_DELETE_FLIGHT` arguments and the unscheduled preview Flight update retry path (ports the remaining coverage from PR #16).

### Changed

- Removed hardcoded `md-blueprints` version pins from the setup and versioning docs; local installs now go through the Makefile (`make setup`, `make install-deploy`), which owns the version pin in generated repositories.
- Changed template repository publishing to preserve `blueprints-template` history instead of force-pushing, and to tag and create a release on the template repository for each version so customer repositories can diff releases.
- Linked Flights, Dives, shares, and service accounts to their MotherDuck product docs pages from the repository and template READMEs.
- Aligned `actions/download-artifact` with the Dependabot-bumped `actions/upload-artifact` major version in the release workflow.
- Rewrote the repository `README.md` for a customer-facing audience: clarified what Blueprints is, documented the relationship between this repository, the `md-blueprints` package/action, and the generated `blueprints-template` repository, added the template-based quickstart, and removed hardcoded version pins. Added the missing Node.js prerequisite to the repository and template READMEs.
- Converted customer-facing deploy and cleanup workflows to run the pinned `motherduckdb/motherduck-blueprints` action instead of installing the local checkout.
- Kept tooling-repository deploy and doctor workflows on the local action checkout while generated customer workflows use the stamped public action tag.
- Updated the action to expose raw CLI stdout and install the deploy extra only for live commands.
- Replaced the deployer DuckDB CLI shell-out with the DuckDB Python package and its live MotherDuck runtime dependencies.
- Split the CLI implementation into schema, template, project, deploy, migration, and maintenance modules.
- Updated release publishing to maintain a floating major tag such as `v0`.
- Updated release publishing to generate the customer template and push it to `motherduckdb/blueprints-template`, failing tagged releases when the required template repository or token is missing.
- Improved validation errors for unsupported schema versions and unknown fields so they name the action/package upgrade path.
- Documented and implemented escaped literal template placeholders with `\${...}`.
- Updated docs and local setup guidance for PyPI installs, action `@v0`, the Python DuckDB runtime, and the schema compatibility matrix.
- Updated customer docs and template docs to use generated repository setup instead of cloning the tooling repository.
- Allowed the release external-setup preflight to accept a PyPI pending trusted publisher before the first package publish.
- Required the generated-template token preflight to prove push permission, catching unapproved fine-grained token requests before release.
- Made preview Flight updates idempotent when schedules are already disabled, aligned Flight run SQL with live MotherDuck function signatures, and surfaced live SQL failures as CLI errors instead of tracebacks.
- Added the MotherDuck runtime timezone dependency to generated starter Flight requirements.
- Updated generated starter Flights to read share URLs through `MD_LIST_DATABASE_SHARES()`.
- Updated preview cleanup to call Flight deletion with the live MotherDuck function signature.
- Included the DuckDB Python package in development installs so strict type checks cover live deploy configuration.
- Switched CI and deployment workflows to install and invoke the packaged `md-blueprints` command.
- Kept `tools/md_blueprints` as a compatibility wrapper around the package command.
- Documented that the template, CLI package, and action stay in one repository for this release, with modularization and repository split as follow-up criteria.

## v0.1.3 - 2026-06-29

### Added

- Added CI coverage that validates manifests, mock deploys, builds the included Dive, and creates then destroys a generated starter blueprint.
- Added `make example-smoke` to prove the generated starter blueprint can be created, rendered, built, and removed.
- Added a generated blueprint README template.
- Added a complete `blueprint.yml` field reference for agents, LLM crawlers, and blueprint authors.
- Added `tools/md_blueprints plan` for read-only live deployment planning.
- Added `tools/md_blueprints cleanup --dry-run` for preview cleanup planning.
- Added optional target deployment metadata for service account identity labels and token env var selection.

### Changed

- Refreshed agent and repository docs so validation checklists, generated-template guidance, context notes, and PR reminders stay aligned.
- Expanded the generated starter blueprint with daily metrics, a summary view, an underscore-safe Dive alias, and a richer dashboard.
- Ran read-only deployment plans before preview and production deploys in CI.
- Failed deploys before mutation when live planning finds duplicate Flights or Dives.
