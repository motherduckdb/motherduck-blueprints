## Highlights

- This release updates development and runtime dependencies. It contains no change to validation, planning, deployment, or cleanup behavior.
- The local Dive preview uses `@vitejs/plugin-react` 6.2.1. [#155](https://github.com/motherduckdb/motherduck-blueprints/pull/155)

## Upgrading from v0.10.2

v0.10.3 is a patch release. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically.

1. Run `make upgrade VERSION=0.10.3`.
2. Run `make sync-preview`, then `make setup`, so that the local Dive preview files and their installed packages match this release. Until then, `doctor` reports the preview files as out of date.
3. Run `make validate`. Then open a pull request and review the preview plan before merging.

## Maintenance

- The local Dive preview uses `@vitejs/plugin-react` 6.2.1. Production Dives are unaffected, because the plugin is used only by the local preview build. [#155](https://github.com/motherduckdb/motherduck-blueprints/pull/155)
- The action installs pytz 2026.6 for the Python SQL backend. [#156](https://github.com/motherduckdb/motherduck-blueprints/pull/156)
- Development dependencies are updated. These are not installed in generated repositories.
  - types-PyYAML 6.0.12.20261030 [#157](https://github.com/motherduckdb/motherduck-blueprints/pull/157)
  - pytest 9.2.0 [#158](https://github.com/motherduckdb/motherduck-blueprints/pull/158)
  - mypy 2.4.1 [#159](https://github.com/motherduckdb/motherduck-blueprints/pull/159)
- The package and action pins are updated to 0.10.3. [#162](https://github.com/motherduckdb/motherduck-blueprints/pull/162)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.10.2...v0.10.3
