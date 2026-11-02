## Highlights

- Errors identify the cause more precisely. An unknown manifest field or `${...}` reference names the closest valid name, and a plan with errors lists each failing resource and states that nothing was changed. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- `plan`, `deploy`, `verify`, and `cleanup` read each Flight, Dive, and Guide list once per plan instead of once per resource, which reduces the number of MotherDuck queries for organizations with many resources. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- The deployment workflows add the plan to the job summary when the plan fails. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)

## Upgrading from v0.9.1

v0.9.2 is a patch release that also rejects one invalid `scheduleCron` form. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically. The local Dive preview is unchanged, so `make sync-preview` is not required.

1. Review the [v0.9.2 breaking-change entry](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.2/docs/breaking-changes.md#v092).
2. Run `make upgrade VERSION=0.9.2`.
3. Run `make validate` and correct any `scheduleCron` value that it now rejects. Then open a pull request and review the preview plan before merging.

Changes to review:

- [A `scheduleCron` step of `0` is rejected](#compatibility)
- [Changed error text](#compatibility)

## Features

- An unknown field in `blueprint.yml` or `motherduck.yml` names the closest valid field, for example `Did you mean 'scheduleCron'?`. An unknown `${...}` template reference names the closest valid reference in the same way. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- `make preview` for a package without a Dive lists the packages that declare one. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- `make upgrade` reminds users to run `make sync-preview` when the repository contains a local Dive preview. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)

## Bug Fixes

- `plan` queried the MotherDuck catalog again for every Flight, Dive, and Guide it checked. It now reads each list once per plan, and `deploy`, `verify`, and `cleanup` benefit from the same change. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- A plan with errors reported the failing resources in a single line. It now lists each failing resource on its own line with its notes and states that nothing was changed. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- When the plan failed, the deployment workflows did not write the plan to the job summary, so the summary did not show which resources had errors. The summary is now written for failed plans as well. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- A timeout while waiting for a share reported only the share name. The message now states that resources deployed before the timeout remain applied, what to check, and which settings extend the wait. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- A non-integer value in `SHARE_RESOLVE_ATTEMPTS`, `SHARE_RESOLVE_SLEEP_SECONDS`, `FLIGHT_RUN_POLL_ATTEMPTS`, or `FLIGHT_RUN_POLL_SLEEP_SECONDS` produced an `invalid literal for int()` error that did not name the variable. It now produces an error that names the variable, and a negative wait is rejected. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- Error output replaced short environment values, such as `false` from `TOKENIZERS_PARALLELISM=false`, with `[redacted]` wherever they appeared in the message. Only values of eight or more characters in variables whose names contain `TOKEN`, `PASSWORD`, `SECRET`, or `API_KEY` are now redacted. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- `make new-*` accepted names with a trailing or doubled hyphen, which produced titles such as `Events ` with a trailing space. These names are now rejected. Existing packages are not affected. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- Errors raised while rendering a manifest named the file by its absolute path. They now name the file relative to the repository root. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)

## Compatibility

- **A `scheduleCron` step of `0` is rejected.** A value such as `*/0 * * * *` previously passed validation, and the Flight then failed at deploy time after earlier resources had been applied. `make validate` now rejects it. Use a step of 1 or more, or remove the step. Refer to [schedule-cron-zero-step](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.2/docs/breaking-changes.md#schedule-cron-zero-step). [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- **Changed error text.** Plan errors use a multi-line format, rendering errors use paths relative to the repository root, and unknown-field errors may end with a suggestion. Automation that matches the previous error text must be updated. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)

## Maintenance

- The documentation describes the package name rules for `make new-*`, the zero-step rule for `scheduleCron`, and the plan summary for failed plans. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)
- The package and action pins are updated to 0.9.2. [#148](https://github.com/motherduckdb/motherduck-blueprints/pull/148)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.9.1...v0.9.2
