## Highlights

- Initialize and refresh a repository overview Guide with `make init-guides` and `make update-guides`, preserving authored notes and deployment settings. [#80](https://github.com/motherduckdb/motherduck-blueprints/pull/80)
- Keep installed packages and generated customer repositories aligned through a single asset map. [#69](https://github.com/motherduckdb/motherduck-blueprints/pull/69)

## Features

- Draft a private, disabled Guide from production package declarations, refresh resource and data-contract facts, report source changes for review, and preview updates with `--dry-run`. Business rules remain authored context. [#80](https://github.com/motherduckdb/motherduck-blueprints/pull/80)

## Bug Fixes

- Keep native CLI smoke-test JSON separate from stderr upgrade notices so notices do not break result parsing. [#69](https://github.com/motherduckdb/motherduck-blueprints/pull/69)

## Maintenance

- Assemble both source distributions and wheels from the authoritative asset map, removing a separately maintained source manifest. [#69](https://github.com/motherduckdb/motherduck-blueprints/pull/69)

## Tooling and Release

- Update preview tooling to Vite 8.2.2 and its React plugin 6.1.1, and update Lucide React to 1.42.0. [#79](https://github.com/motherduckdb/motherduck-blueprints/pull/79) [#75](https://github.com/motherduckdb/motherduck-blueprints/pull/75) [#73](https://github.com/motherduckdb/motherduck-blueprints/pull/73)
- Update action build pins to setuptools 84.0.0 and wheel 0.48.0, and refresh locked mypy, Ruff, and PyYAML typing dependencies. [#76](https://github.com/motherduckdb/motherduck-blueprints/pull/76) [#71](https://github.com/motherduckdb/motherduck-blueprints/pull/71) [#74](https://github.com/motherduckdb/motherduck-blueprints/pull/74) [#78](https://github.com/motherduckdb/motherduck-blueprints/pull/78) [#72](https://github.com/motherduckdb/motherduck-blueprints/pull/72)

- Align the CLI, reusable workflows, documentation, and generated template on v0.6.0. [Release diff](https://github.com/motherduckdb/motherduck-blueprints/compare/v0.5.1...v0.6.0)

## Compatibility

- Schema version 1, existing resource IDs, deployment targets, schedules, and adoption settings are unchanged. The new Guide workflow is opt-in and does not publish content automatically. [#80](https://github.com/motherduckdb/motherduck-blueprints/pull/80) [#69](https://github.com/motherduckdb/motherduck-blueprints/pull/69)
- Existing repositories can run `make upgrade VERSION=0.6.0`, then `make validate` to install and check the pinned CLI. Use `.venv/bin/md-blueprints guides init` and `.venv/bin/md-blueprints guides update`. Upgrading pins does not add the new Makefile shortcuts. New templates include them. [#80](https://github.com/motherduckdb/motherduck-blueprints/pull/80)
- React and React DOM remain on 18, and Apache Arrow remains on 17 for the current MotherDuck WASM client. The incompatible standalone major upgrades are excluded. [#77](https://github.com/motherduckdb/motherduck-blueprints/pull/77) [#70](https://github.com/motherduckdb/motherduck-blueprints/pull/70)
- Custom Dives using Lucide should run their preview build to check icon exports after upgrading the preview dependencies. Repository icon imports and generated examples were checked with Lucide 1.42.0. [#73](https://github.com/motherduckdb/motherduck-blueprints/pull/73)

## Verification

- Passed 312 unit tests, manifest validation, strict typing and lint, mock deployments, native CLI smoke, preview and generated-example builds, customer journeys, and installed-wheel smoke tests during integration. [#80](https://github.com/motherduckdb/motherduck-blueprints/pull/80) [#71](https://github.com/motherduckdb/motherduck-blueprints/pull/71) [#75](https://github.com/motherduckdb/motherduck-blueprints/pull/75)
- CI covers Python 3.10–3.14, packaging, workflow lint, and dependency audits. Tagged publication additionally verifies release artifacts and the generated template. [CI](https://github.com/motherduckdb/motherduck-blueprints/actions/workflows/ci.yaml) [Release workflow](https://github.com/motherduckdb/motherduck-blueprints/actions/workflows/release.yaml)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.5.1...v0.6.0
