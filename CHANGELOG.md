# Changelog

All notable changes to this repository are documented here.

Update this file in every pull request. Add entries under `Unreleased` until the change is released or merged into a reusable template.

## Unreleased

### Added

- Introduced project-first blueprint packages under `blueprints/<name>/`.
- Added the root `motherduck.yml` repository manifest, JSON schemas, and `tools/md_blueprints`.
- Added a deployable starter scaffold through `make new-blueprint <blueprint-name>`.
- Added manifest-driven GitHub workflows for validation, preview deploys, production deploys, and preview cleanup.
- Added local smoke coverage for manifest validation, rendered targets, mock deploys, preview cleanup, failed Flight runs, and Dive preview builds.

### Changed

- Migrated the Wikipedia Pageviews example into `blueprints/wikipedia-pageviews/`.
- Skipped production deployment and preview cleanup workflows when `MOTHERDUCK_TOKEN` is not configured.
- Reworked setup language for self-service use in your own repository.
- Simplified the README into a self-service quickstart and moved detailed repository mechanics into `docs/repository-reference.md`.
- Reworded blueprint documentation to describe the project-first layout without external product comparisons.
- Replaced type-first Dives, Flights, and bundles documentation with project-level blueprint guidance.
- Documented that blueprint packages represent one logical project or data product, not an organization, service account, user, or database owner.

### Removed

- Removed top-level `dives/`, `flights/`, and `bundles/` deployment lanes and scripts.
