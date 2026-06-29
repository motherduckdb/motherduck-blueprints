# Changelog

All notable changes to this repository are documented here.

Update this file in every pull request. Add entries under `Unreleased` until the change is released or merged into a reusable template.

## Unreleased

### Added

- Added CI coverage that validates manifests, mock deploys, builds the included Dive, and creates then destroys a generated starter blueprint.
- Added `make example-smoke` to prove the generated starter blueprint can be created, rendered, built, and removed.
- Added a generated blueprint README template.
- Added a complete `blueprint.yml` field reference for agents, LLM crawlers, and blueprint authors.
- Introduced project-first blueprint packages under `blueprints/<name>/`.
- Added the root `motherduck.yml` repository manifest, JSON schemas, and `tools/md_blueprints`.
- Added `tools/md_blueprints plan` for read-only live deployment planning.
- Added `tools/md_blueprints cleanup --dry-run` for preview cleanup planning.
- Added optional target deployment metadata for service account identity labels and token env var selection.
- Added a deployable starter scaffold through `make new-blueprint <blueprint-name>`.
- Added manifest-driven GitHub workflows for validation, preview deploys, production deploys, and preview cleanup.
- Added local smoke coverage for manifest validation, rendered targets, mock deploys, preview cleanup, failed Flight runs, and Dive preview builds.

### Changed

- Refreshed agent and repository docs so validation checklists, generated-template guidance, context notes, and PR reminders stay aligned.
- Expanded the generated starter blueprint with daily metrics, a summary view, an underscore-safe Dive alias, and a richer dashboard.
- Migrated the Wikipedia Pageviews example into `blueprints/wikipedia-pageviews/`.
- Ran read-only deployment plans before preview and production deploys in CI.
- Failed deploys before mutation when live planning finds duplicate Flights or Dives.
- Skipped production deployment and preview cleanup workflows when `MOTHERDUCK_TOKEN` is not configured.
- Reworked setup language for self-service use in your own repository.
- Simplified the README into a self-service quickstart and moved detailed repository mechanics into `docs/repository-reference.md`.
- Reworded blueprint documentation to describe the project-first layout without external product comparisons.
- Replaced type-first Dives, Flights, and bundles documentation with project-level blueprint guidance.
- Documented that blueprint packages represent one logical project or data product, not an organization, service account, user, or database owner.

### Removed

- Removed top-level `dives/`, `flights/`, and `bundles/` deployment lanes and scripts.
