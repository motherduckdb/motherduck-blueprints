## Highlights

- The local Dive preview accepts BIGINT and HUGEINT values in `useDiveState` and restores them as `bigint` after a reload, as production Dives now do. [#183](https://github.com/motherduckdb/motherduck-blueprints/pull/183)
- Blueprints installs MotherDuck CLI `v1.5.6-2026-11-503`. [#183](https://github.com/motherduckdb/motherduck-blueprints/pull/183)
- The local preview's build tools and the Python dependencies are updated. [#179](https://github.com/motherduckdb/motherduck-blueprints/pull/179), [#181](https://github.com/motherduckdb/motherduck-blueprints/pull/181)

## Upgrading from v0.11.0

v0.11.1 is a patch release. It changes no manifest fields and no deployment behavior. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically.

1. Run `make upgrade VERSION=0.11.1`.
2. Run `make install-deploy` to install the pinned MotherDuck CLI.
3. Run `make sync-preview` to refresh `.dive-preview/`. Until then, `make doctor` reports that the preview support files differ from the installed release.
4. Run `make validate`. Then open a pull request and review the preview plan before merging.

## Bug Fixes

- The local Dive preview no longer throws an error when a Dive stores a BIGINT or HUGEINT value with `useDiveState`. DuckDB-Wasm returns these columns as JavaScript `bigint`, which JSON cannot represent. Production Dives now store such values and restore them with the same value and type. The preview follows the same behavior: it writes each value to the page URL as `{ "$bigint": "<digits>" }` and reads it back as a `bigint` after a reload. Converting BIGINT values with `Number()` before charting them remains recommended. [#183](https://github.com/motherduckdb/motherduck-blueprints/pull/183)

## Compatibility

- **The pinned MotherDuck CLI changes.** Blueprints installs `v1.5.6-2026-11-503` instead of `v1.5.6-2026-11-451`. The commands, flags, and help text are unchanged. Run `make install-deploy` after upgrading. [#183](https://github.com/motherduckdb/motherduck-blueprints/pull/183)

## Maintenance

- The local Dive preview builds with Vite 8.3.8 and `@vitejs/plugin-react` 6.3.0. React, d3, lucide-react, and recharts remain at the versions that production Dives load. [#179](https://github.com/motherduckdb/motherduck-blueprints/pull/179), [#168](https://github.com/motherduckdb/motherduck-blueprints/pull/168)
- Dependency updates: [#181](https://github.com/motherduckdb/motherduck-blueprints/pull/181), [#170](https://github.com/motherduckdb/motherduck-blueprints/pull/170), [#180](https://github.com/motherduckdb/motherduck-blueprints/pull/180), [#182](https://github.com/motherduckdb/motherduck-blueprints/pull/182)
  - `certifi`, which verifies HTTPS certificates, is updated to 2026.10.23.
  - The `pip` version that the action installs with is updated to 26.3.
  - The development tools `ruff` and `types-pyyaml` are updated.
- The repository reference describes how the local preview keeps `useDiveState` values. [#183](https://github.com/motherduckdb/motherduck-blueprints/pull/183)
- The package and action pins are updated to 0.11.1. [#183](https://github.com/motherduckdb/motherduck-blueprints/pull/183)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.11.0...v0.11.1
