## Highlights

- Blueprints matches MotherDuck's October releases. It installs MotherDuck CLI `v1.5.6-2026-10-484` with DuckDB 1.5.6. `plan` now stops before any write on a Flight access token that is missing or expired, or on a role name MotherDuck refuses. Before, these failed partway through a deploy. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The local Dive preview behaves like production Dives. It has the same SDK exports and library versions, the same read-only attachment of required databases, and the same DuckDB 1.5.6 client. `make sync-preview` refreshes it after an upgrade. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- `make export` and `md-blueprints import --all` work in large, busy organizations. Before, they failed whenever a Dive changed during the scan. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)

## Upgrading from v0.8.1

v0.9.0 is a minor release. Generated repositories pin exact versions, so `make upgrade` must name it. Workflows on the floating `@v0` tag receive it automatically, but still need step 3.

1. Read the [v0.9.0 breaking-change entries](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#v090).
2. Run `make upgrade VERSION=0.9.0`.
3. Run `make sync-preview` (or `.venv/bin/md-blueprints sync-preview --write`) to replace `.dive-preview/`. `make upgrade` does not update those files, and `make doctor` reports when they differ.
4. Run `make preview-smoke NAME` for each Dive, then open a pull request and review the preview plan before merging. Look for share rows that now report changes, and for new token or role-name errors.
5. Update any other pinned `motherduckdb/motherduck-blueprints@v0.8.1` references to `@v0.9.0`.

Changes to check:

- [Dive preview builds against the production runtime](#compatibility)
- [Dive preview attaches only required databases](#compatibility)
- [Share plans report include-pattern and grant changes](#compatibility)

## Features

- Install MotherDuck CLI `v1.5.6-2026-10-484`, which embeds DuckDB 1.5.6. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
  - `make export` records each Flight's `instanceType`, and local deploys can set it.
  - `motherduck dive watch` previews again.
  - Commands no longer print a "New MotherDuck CLI available" notice.
- `plan` checks each Flight's `accessTokenName` with `md_access_tokens()`. A missing or expired token stops `plan` and `deploy` before any write, and a token that expires within 14 days prints a warning. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- `plan` stops before any write when a role it would create has a name MotherDuck refuses. `make new-role finance-team` now declares `finance_team`. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- `plan` reports what will change on shares with a managed `includePattern` or `grants`, and deploy skips an unchanged `SET INCLUDE_PATTERN`. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- New Flights from `make new-flight` and the starter open only their own database with `md:<database>?attach_mode=single`. They connect in about half the time on a workspace with many databases, and fall back to the whole workspace on the first run, before the database exists. To read another database, attach it with `ATTACH 'md:<name>'`. Existing Flight source is unchanged. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The Dive preview supports `useRunFlight`, `useFlightRun`, `quoteSqlIdentifier`, `quoteSqlString`, and d3. New `make sync-preview` and `md-blueprints sync-preview` commands refresh `.dive-preview/`. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- The Python backend reuses one MotherDuck connection per command. That saves about 0.7 seconds per statement. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)

## Bug Fixes

- `make export`, `md-blueprints import --all`, and name lookups in `plan` and `deploy` failed with "Catalog changed or pagination repeated an ID" when a resource was updated during the scan. In an organization with about 2,700 Dives, every import failed this way. They now rescan, up to three times, and the importer reads 1,000 resources per page instead of 100. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The owner of a Dive's producer database could not preview the Dive locally, and saw "Share alias cannot be the same as an existing database name". The preview now attaches required databases the way MotherDuck does. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The Wikipedia starter Dive's "Article totals" chart was empty, locally and in MotherDuck, because recharts cannot plot BIGINT values. It now shows its bars. Repositories created earlier keep the old Dive source, so copy `dives/wikipedia-pageviews/src/dive.tsx` from the [v0.9.0 template](https://github.com/motherduckdb/blueprints-template) or convert the totals with `Number()`. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- `make preview` uses vite 8.3.5. vite 8.3.2 had three launch-editor advisories that affect Windows. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)

## Compatibility

- **Dive preview builds against the production runtime.** `@motherduck/react-sql-query` exports only the production v1 API, and React, lucide-react, recharts, d3, and Tailwind CSS are pinned to the versions production Dives load. A Dive that imports `useConnection`, or uses a newer lucide icon, fails `make preview-smoke`, as it already failed in MotherDuck. See [preview-matches-dive-runtime](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#preview-matches-dive-runtime). [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- **Dive preview attaches only required databases.** These are attached read-only. Declare every database a Dive reads in `requiredResources` and `REQUIRED_DATABASES`. See [preview-attaches-required-databases-only](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#preview-attaches-required-databases-only). [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- **Share plans report include-pattern and grant changes.** Automation that parses the plan sees `present` or a change list for those shares. See [share-plan-reports-changes](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#share-plan-reports-changes). [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)

## Maintenance

- Dependencies are updated. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
  - Python lock: json5 0.17.3, ruff 0.17.1, and others.
  - The action's pip, setuptools, build, and json5 constraints.
  - The preview's `@motherduck/wasm-client` 1.5.6-r.1.
  - The setup-python, setup-node, upload-artifact, and download-artifact action pins.
  - DuckDB stays at 1.5.6, the version MotherDuck runs.
- The docs cover several new topics. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
  - Role assignment under SCIM provisioning, an Enterprise plan feature.
  - Include-pattern plan requirements.
  - Running Flights from Dives, where only the Dive's owner can run them until MotherDuck releases Flight `run` grants.
  - Converting BIGINT values in Dives.
  - Troubleshooting rows for the new plan errors.
- The package and action pins move to 0.9.0. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.8.1...v0.9.0
