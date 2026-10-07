## Highlights

- The setup guide explains the admin check that runs before deploying roles and organization Guides, including the `md_list_roles_for_user` error from v0.4.0 to v0.7.4. [#115](https://github.com/motherduckdb/motherduck-blueprints/pull/115)
- The repository guide for agents says that an inherited `admin` role passes and that a missing one stops every selected package. [#115](https://github.com/motherduckdb/motherduck-blueprints/pull/115)

## Upgrading from v0.7.5

v0.7.6 changes documentation only. Deployment behavior is the same as v0.7.5. Generated repositories pin an exact version in `Makefile` and in every workflow reference, so nothing changes until you upgrade. Workflows that reference the floating `@v0` tag receive v0.7.6 automatically.

1. Run `make upgrade VERSION=0.7.6`. It updates `CLI_VERSION` and every Blueprints workflow and action pin to `v0.7.6`.
2. To pick up the new guidance, copy `AGENTS.md` and `docs/setup-your-repository.md` from the [v0.7.6 template](https://github.com/motherduckdb/blueprints-template). `make upgrade` updates version pins only and does not change docs.
3. Run `make validate`.
4. Open a pull request, review the diff, and merge it.

## Maintenance

- `docs/setup-your-repository.md` has two new troubleshooting rows. [#115](https://github.com/motherduckdb/motherduck-blueprints/pull/115)
  - `RBAC preflight failed: target requires the admin role`: grant `admin` to the deployment identity, directly or through a custom role, or set `deploy: false` on the roles and organization Guides it names.
  - `Table Function with name md_list_roles_for_user does not exist`: run `make upgrade` to move to v0.7.5 or newer.
- The template `AGENTS.md` describes the admin check. [#115](https://github.com/motherduckdb/motherduck-blueprints/pull/115)
- The package and action pins move to 0.7.6. [#115](https://github.com/motherduckdb/motherduck-blueprints/pull/115)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.7.5...v0.7.6
