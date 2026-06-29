# Changelog

All notable changes to this repository are documented here.

Update this file in every pull request. Add entries under `Unreleased` until the change is released or merged into a reusable template.

## Unreleased

No unreleased changes.

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
