## Highlights

- Reduce the tooling repository from 191 to 141 source files by assembling shared assets from one authoritative copy. Installed packages retain the docs, schemas, starters, and preview support. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)
- Add complete validation and manual deployment workflows to the README, including environment-secret setup. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)

## Maintenance

- Remove duplicate scaffolds and empty optional-root guidance. Merge GitHub protection guidance into the setup guide and remove the outdated tooling devcontainer. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)
- Generate repository workflow jobs from reusable providers. Repository jobs still test the current checkout, while customer workflows use the release pin. Generated YAML remains checked in for GitHub Actions. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)

## Tooling and Release

- Release v0.5.1 through GitHub with self-contained wheel and source distribution assets. Source checkouts resolve authoritative assets directly, and wheel builds assemble the same files. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)

## Compatibility

**No customer file or resource migration is required.** Schema version 1, resource discovery roots, bound IDs and ownership guards, schedule configuration, targets, secrets, CLI commands, action inputs, and reusable workflow paths remain unchanged. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)

- In generated repositories, run `make upgrade VERSION=0.5.1`, review the diff, then run `make validate`. This updates CLI and action/workflow pins only. Existing expanded workflows are preserved. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)
- For older templates without `make upgrade`, update `CLI_VERSION` and MotherDuck Blueprints action or reusable-workflow pins manually to `0.5.1` / `v0.5.1`, preserving workflow settings. Direct-action users can use `motherduckdb/motherduck-blueprints@v0.5.1`. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)
- Adopted Flights, Dives, and Guides do not need re-export, re-import, renaming, or changes to bound IDs. Owner settings and `manageSchedule: false` remain as configured. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)
- Existing `templates/`, placeholder READMEs, `docs/github-setup.md`, and custom `.devcontainer/` files can remain. Upgrading does not delete them. Only remove old files after checking they are unmodified and unused by custom tooling. Keep populated resource directories and customized files. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)
- New repositories receive the consolidated setup guide. Optional roots continue to be created on demand, and the optional NCS example remains available. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)
- Tooling contributors and forks must use the asset map and source manifest when adding shared files, and run `make sync-workflows` after changing reusable jobs. Direct references to removed internal source paths must be updated. Customer CLI and action interfaces are unchanged. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)

## Verification

- Passed 295 unit tests, package installation and assembled-asset checks, upgrade-preservation coverage, mock deployments, preview/example builds, customer-journey checks, typing, and linting before release preparation. Final release checks are run against the v0.5.1 commit. [#68](https://github.com/motherduckdb/motherduck-blueprints/pull/68)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.5.0...v0.5.1
