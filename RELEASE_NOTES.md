## Highlights

- The local Dive preview's `useSQLQuery` matches the production hook rebuilt on TanStack Query v5, adding `isPending` and `isFetching` and keeping previous rows visible while new SQL loads. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
- The starter Dive, scaffolds, and examples show placeholders while `isPending` is true, following MotherDuck's current guidance. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
- Blueprints installs MotherDuck CLI `v1.5.6-2026-11-616`, and the Python backend requires DuckDB 1.4 or newer. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)

## Upgrading from v0.11.1

v0.11.2 is a patch release. It changes no manifest fields and no deployment behavior, but the local Dive preview now reports query state as production Dives do, and the Python backend requires DuckDB 1.4 or newer. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically.

1. Run `make upgrade VERSION=0.11.2`.
2. Run `make install-deploy` to install the pinned MotherDuck CLI.
3. Run `make sync-preview` to refresh `.dive-preview/`. Until then, `make doctor` reports that the preview support files differ from the installed release.
4. Run `make validate` and `make preview-smoke` for each package with a Dive. Then open a pull request and review the preview plan before merging.

Review these items in the [Compatibility](#compatibility) section before upgrading:

- Dives that compare `useSQLQuery` `status` with `"idle"` or `"loading"`, or pass transformed rows as `initialData` or `placeholderData` with `select`.
- Dive source that imports `@tanstack/query-core`.
- Environments that install `md-blueprints[deploy]` with a `duckdb` version below 1.4.

## Features

- The local Dive preview's `useSQLQuery` uses `@tanstack/query-core` 5.101.4 with the same settings that production Dives use. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
  - The result adds `isPending` (true until a query has data) and `isFetching` (true while a query runs).
  - When SQL changes, previous rows remain on screen with `isPlaceholderData` set to true until new rows arrive. Passing `placeholderData: () => undefined` clears them instead.
  - `initialData` and `placeholderData` accept raw rows, which `select` transforms.
  - `isLoading` remains available for existing Dives and is true while connecting and during every fetch.
- The starter Dive, the `make new-dive` and `make new-project` scaffolds, and the `ncs-field-recovery` and `pageviews-weekly-trends` examples show placeholders while `isPending` is true. The `ncs-field-recovery` example dims a section while `isFetching` is true after a filter changes. Existing repositories keep their Dives. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)

## Bug Fixes

- Dives using `isPending` or `isFetching` now display loading states in the local preview. Before, the preview omitted these fields, so those Dives showed no loading state locally even though they did in MotherDuck. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
- When MotherDuck rejects a revoked or expired access token with "Invalid personal access token", Blueprints now identifies which secret to replace, matching its handling of other rejected tokens. Before, the command exited with the raw SQL error. MotherDuck now returns this error immediately instead of retrying. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)

## Compatibility

- **The local preview's `useSQLQuery` matches production state behavior.** `status` is `pending`, `error`, or `success`, previous rows remain while new SQL loads, and `initialData` and `placeholderData` take raw rows. Production Dives already behave this way. Update Dive code that relies on the previous preview behavior, then run `make sync-preview`. Refer to [preview-usesqlquery-tanstack](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.11.2/docs/breaking-changes.md#preview-usesqlquery-tanstack). [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
- **Dive source cannot import `@tanstack/query-core`.** The preview installs the package only for `useSQLQuery`. `make preview` and `make preview-smoke` fail with `Dives cannot import "@tanstack/query-core"`, matching production Dives. Use the `useSQLQuery` options and result fields instead. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
- **The `deploy` extra requires DuckDB 1.4 or newer.** MotherDuck no longer accepts DuckDB 1.3 clients. Install `duckdb` 1.4 or newer, preferably 1.5.6, in environments that install `md-blueprints[deploy]`. The GitHub Action and the MotherDuck CLI backend are not affected. Refer to [deploy-extra-needs-duckdb-1-4](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.11.2/docs/breaking-changes.md#deploy-extra-needs-duckdb-1-4). [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
- **The pinned MotherDuck CLI changes.** Blueprints installs `v1.5.6-2026-11-616` instead of `v1.5.6-2026-11-503`. Commands and flags are unchanged, and `dive --help` now states that sharing a Dive does not share the data it reads or the Flights it runs. Run `make install-deploy` after upgrading. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)

## Maintenance

- Documentation and generated repository agent instructions are updated for `useSQLQuery` and Dive data sharing. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
  - The [repository reference](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.11.2/docs/repository-reference.md#dives) documents how `useSQLQuery` reports loading states.
  - The [Dives reference](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.11.2/docs/blueprint-yml-reference.md#dives) recommends sharing a Dive's data and Flights as widely as the Dive and no wider. A Dive with `organization: true` requires shares with `ORGANIZATION` access, because a restricted share cannot be granted to the organization.
  - The Dives reference also documents the web app's Share Dive dialog, which shows whether viewers can read a Dive's data and, when the Dive is saved, can grant them `READ` on its shares. Share `grants` with `mode: authoritative` revoke those grants on the next deploy.
- Dependabot keeps `@tanstack/query-core` in `.dive-preview/` at the version that production Dives use, as it does for React, d3, lucide-react, and recharts. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)
- The package and action pins are updated to 0.11.2. [#185](https://github.com/motherduckdb/motherduck-blueprints/pull/185)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.11.1...v0.11.2
