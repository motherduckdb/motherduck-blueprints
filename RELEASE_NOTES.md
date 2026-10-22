## Highlights

- This release aligns Blueprints with the MotherDuck releases of October 2026. It installs MotherDuck CLI `v1.5.6-2026-10-484`, which embeds DuckDB 1.5.6, and `plan` now detects missing or expired Flight access tokens and invalid role names before any write. Previously, these conditions caused a deployment to fail partway through. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The local Dive preview now matches the production Dive runtime: the same SDK exports, the same library versions, the same DuckDB 1.5.6 client, and the same read-only attachment of required databases. The new `make sync-preview` command refreshes the preview after an upgrade. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- `make export` and `md-blueprints import --all` now complete reliably in organizations with many Dives, including while those Dives are being modified. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)

## Upgrading from v0.8.1

v0.9.0 is a minor release. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically but still require step 3.

1. Review the [v0.9.0 breaking-change entries](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#v090).
2. Run `make upgrade VERSION=0.9.0`.
3. Run `make sync-preview` (or `.venv/bin/md-blueprints sync-preview --write`) to replace the files in `.dive-preview/`. `make upgrade` does not update these files, and `make doctor` reports when they differ from the installed release.
4. Run `make preview-smoke NAME` for each Dive. Then open a pull request and review the preview plan before merging, paying particular attention to share rows that now report changes and to new access token or role name errors.
5. Update any remaining `motherduckdb/motherduck-blueprints@v0.8.1` references to `@v0.9.0`.

Changes to review:

- [The Dive preview builds against the production runtime](#compatibility)
- [The Dive preview attaches only required databases](#compatibility)
- [Share plans report include-pattern and grant changes](#compatibility)

## Features

- Blueprints installs MotherDuck CLI `v1.5.6-2026-10-484`, which embeds DuckDB 1.5.6. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
  - `make export` records the `instanceType` of each Flight, and local deployments can set it.
  - `motherduck dive watch` previews Dives correctly.
  - Commands no longer print a "New MotherDuck CLI available" notice.
- `plan` validates the `accessTokenName` of each Flight against `md_access_tokens()`. A missing or expired token stops `plan` and `deploy` before any write, and a token that expires within 14 days produces a warning. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- `plan` stops before any write when a role it would create has a name that MotherDuck does not accept. `make new-role finance-team` now declares the role `finance_team`. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- `plan` reports the pending changes for shares with a managed `includePattern` or `grants`, and `deploy` no longer reissues an unchanged `SET INCLUDE_PATTERN`. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- Flights created by `make new-flight`, and the starter Flight, open only their own database with `md:<database>?attach_mode=single`. This reduces connection time by approximately half in workspaces with many databases. On the first run, before the database exists, the Flight opens the full workspace to create it. A Flight that reads additional databases must attach them with `ATTACH 'md:<name>'`. Existing Flight source code is not modified. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The Dive preview supports `useRunFlight`, `useFlightRun`, `quoteSqlIdentifier`, `quoteSqlString`, and d3. The new `make sync-preview` and `md-blueprints sync-preview` commands refresh `.dive-preview/`. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- The Python backend reuses a single MotherDuck connection for each command, which saves approximately 0.7 seconds per statement. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)

## Bug Fixes

- `make export`, `md-blueprints import --all`, and the name lookups in `plan` and `deploy` failed with "Catalog changed or pagination repeated an ID" when a Dive, Flight, or Guide was modified during the scan. This occurred consistently in organizations with many frequently updated Dives. These commands now repeat the scan up to three times before reporting the error, and the importer reads 1,000 resources per page instead of 100. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The owner of the database behind a Dive's share could not preview that Dive locally and received the error "Share alias cannot be the same as an existing database name". The preview now attaches required databases in the same way as MotherDuck. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- The "Article totals" chart in the Wikipedia starter Dive displayed no bars, both locally and in MotherDuck, because the chart library cannot plot BIGINT values. The chart now displays correctly. Repositories created before this release retain the previous Dive source. To apply the fix, copy `dives/wikipedia-pageviews/src/dive.tsx` from the [v0.9.0 template](https://github.com/motherduckdb/blueprints-template), or convert the totals with `Number()`. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- `make preview` uses vite 8.3.5, which resolves three launch-editor security advisories in vite 8.3.2 that affect Windows. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)

## Compatibility

- **The Dive preview builds against the production runtime.** `@motherduck/react-sql-query` exports only the production v1 API, and React, lucide-react, recharts, d3, and Tailwind CSS are pinned to the versions that production Dives load. A Dive that imports `useConnection`, or uses a lucide icon newer than the pinned version, now fails `make preview-smoke`, consistent with its behavior in MotherDuck. Refer to [preview-matches-dive-runtime](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#preview-matches-dive-runtime). [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)
- **The Dive preview attaches only required databases, in read-only mode.** Declare every database that a Dive reads in both `requiredResources` and `REQUIRED_DATABASES`. Refer to [preview-attaches-required-databases-only](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#preview-attaches-required-databases-only). [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
- **Share plans report include-pattern and grant changes.** Automation that parses the plan receives either `present` or a list of changes for these shares. Refer to [share-plan-reports-changes](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.0/docs/breaking-changes.md#share-plan-reports-changes). [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)

## Maintenance

- Dependencies are updated. [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
  - The Python lock file, including json5 0.17.3 and ruff 0.17.1.
  - The pip, setuptools, build, and json5 constraints of the GitHub Action.
  - `@motherduck/wasm-client` 1.5.6-r.1 in the Dive preview.
  - The setup-python, setup-node, upload-artifact, and download-artifact action pins.
  - DuckDB remains at 1.5.6, the version that MotherDuck runs.
- The documentation covers the following additional topics. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141), [#142](https://github.com/motherduckdb/motherduck-blueprints/pull/142)
  - Role assignment under SCIM provisioning, which is available on the Enterprise plan.
  - Requirements for include patterns in plans.
  - Running Flights from Dives. Until MotherDuck releases Flight `run` grants, only the owner of a Dive can run Flights from it.
  - Converting BIGINT values in Dives.
  - Troubleshooting entries for the new plan errors.
- The package and action pins are updated to 0.9.0. [#141](https://github.com/motherduckdb/motherduck-blueprints/pull/141)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.8.1...v0.9.0
