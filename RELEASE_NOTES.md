## Highlights

- Previews, deploys, and preview cleanup work again in customer repositories. The generated deploy and cleanup workflows now pass `MOTHERDUCK_TOKEN` to the reusable workflows, which GitHub requires even when the token is an environment secret. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)
- `make upgrade` adds the missing `secrets:` block to existing workflows, and `make doctor` reports workflows that still lack it. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)

## Upgrading from v0.7.7

v0.7.8 is a patch release. Generated repositories pin an exact version in `Makefile` and in every workflow reference, so nothing changes until you upgrade. Workflows that reference the floating `@v0` tag receive the new reusable workflows automatically, but the token fix also needs a change in your own deploy and cleanup workflows, so run the upgrade either way.

1. Run `make upgrade VERSION=0.7.8`. It updates `CLI_VERSION` and every Blueprints workflow and action pin to `v0.7.8`, and adds `secrets: MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}` to the deploy and cleanup jobs that pass no secrets.
2. If a deploy or cleanup job uses `secrets: inherit`, replace it with the `MOTHERDUCK_TOKEN` line above. `make upgrade` leaves jobs that already have a `secrets` entry unchanged.
3. Run `make doctor`. It should not print a `MOTHERDUCK_TOKEN` warning.
4. To pick up the new guidance, copy `AGENTS.md`, `docs/github-action.md`, `docs/setup-your-repository.md`, and `docs/tooling-and-schema-versioning.md` from the [v0.7.8 template](https://github.com/motherduckdb/blueprints-template).
5. Open a pull request, review the diff, and merge it. The pull request's preview deployment should now find the token.

See [Compatibility](#compatibility) for what changes in your workflows.

## Bug Fixes

- Reusable workflows received an empty token. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127), fixes [#125](https://github.com/motherduckdb/motherduck-blueprints/issues/125)
  - Before: previews, deploys, and preview cleanup failed with `MOTHERDUCK_TOKEN is required`, even though `MOTHERDUCK_TOKEN` was set in the target's GitHub Environment. GitHub gives a reusable workflow an empty string for an environment secret unless the calling workflow passes it by name, and the generated workflows passed nothing.
  - Now: the reusable deploy and cleanup workflows declare `MOTHERDUCK_TOKEN` as an optional secret, and the generated workflows pass it. The value still comes from the GitHub Environment that the target selects. Thanks to [@philipqnguyen](https://github.com/philipqnguyen) for the report and the fix.

## Features

- `make upgrade` adds `secrets: MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}` to reusable deploy and cleanup jobs that pass no secrets, so an upgraded repository matches a newly generated one. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)
- `make doctor` warns about deploy and cleanup jobs that pass no token, and about jobs that use `secrets: inherit`, which GitHub only honors within one organization or enterprise. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)

## Compatibility

- Deploy and cleanup workflows must pass the token. A workflow that calls `reusable_deploy_blueprints.yaml` or `reusable_cleanup_preview_blueprints.yaml` without `secrets: MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}` still gets an empty token. Run `make upgrade` or add the block yourself. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)
- Do not use `secrets: inherit` for these jobs. It passes nothing when your repository is outside the motherduckdb organization. Pass `MOTHERDUCK_TOKEN` by name instead. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)

## Maintenance

- Documentation updates. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)
  - `docs/github-action.md` no longer says that no secret passing is needed.
  - `docs/setup-your-repository.md` has a troubleshooting row for `MOTHERDUCK_TOKEN is required`.
  - `docs/tooling-and-schema-versioning.md` describes the new `make upgrade` behavior.
  - The template `AGENTS.md` tells agents to keep the `secrets:` block.
- Dependency updates. [#128](https://github.com/motherduckdb/motherduck-blueprints/pull/128)
  - The local Dive preview uses React and React DOM 19.3.0, lucide-react 1.52.0, Vite 8.3.2, and @vitejs/plugin-react 6.1.2.
  - The action pins pytz 2026.5.
- The package and action pins move to 0.7.8. [#127](https://github.com/motherduckdb/motherduck-blueprints/pull/127)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.7.7...v0.7.8
