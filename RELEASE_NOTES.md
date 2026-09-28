## Highlights

- Preview cleanup skips Dependabot branches before it starts, so those runs no longer check out code or validate the base manifest. [#94](https://github.com/motherduckdb/motherduck-blueprints/pull/94)
- Safer template publishing: each release validates the generated template before publishing it, and a patch for an older release line no longer moves `@v0` or the template back. [#94](https://github.com/motherduckdb/motherduck-blueprints/pull/94)

## Upgrading from v0.7.0

v0.7.1 is a patch release with no manifest or configuration changes. Generated repositories pin an exact version in `Makefile` and in every workflow reference, so nothing changes until you upgrade. Workflows that reference the floating `@v0` tag receive v0.7.1 automatically.

1. Run `make upgrade VERSION=0.7.1`. It updates `CLI_VERSION` and every Blueprints workflow and action pin to `v0.7.1`.
2. Run `make validate`.
3. Open a pull request, review the diff, and merge it.

## Bug Fixes

- Dependabot preview cleanup: before, the skip ran inside the cleanup job after it had checked out the base commit and validated its manifest, so a problem in those steps still showed a failed cleanup for a branch that never had a preview. Now the job is skipped for Dependabot branches before it starts. [#94](https://github.com/motherduckdb/motherduck-blueprints/pull/94)

## Maintenance

- Releases run `md-blueprints validate` on the generated template before pushing it to the template repository. [#94](https://github.com/motherduckdb/motherduck-blueprints/pull/94)
- A release for an older line keeps the template's default branch, the floating major tag, and the GitHub "Latest" release on the highest version. [#94](https://github.com/motherduckdb/motherduck-blueprints/pull/94)
- The tooling repository's own preview cleanup works when a pull request's base commit predates the action's `python` output. [#94](https://github.com/motherduckdb/motherduck-blueprints/pull/94)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.7.0...v0.7.1
