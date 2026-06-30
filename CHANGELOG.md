# Changelog

All notable changes to this repository are documented here.

Update this file in every pull request. Add entries under `Unreleased` until the change is released or merged into a reusable template.

## Unreleased

### Added

- Added the versioned `md-blueprints` Python package, console command, packaged schema resources, and GitHub Action wrapper.
- Added `md-blueprints doctor`, `md-blueprints check-updates`, and `md-blueprints migrate --to latest` as schema maintenance surfaces.
- Added tooling and schema versioning documentation for package pinning, compatibility policy, and customer upgrade flow.
- Added package and release-artifact smoke tests for the wheel, sdist, packaged schemas, and local GitHub Action wrapper.
- Added release version checks and GitHub Release publishing for tagged package artifacts.

### Changed

- Updated live Flight deploys to call `MD_RUN_FLIGHT` with the current MotherDuck argument order.
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
