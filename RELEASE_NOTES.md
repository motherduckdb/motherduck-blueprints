## Highlights

- Organization Guides and roles deploy again. The admin check before these deploys failed for every identity, including organization admins, and stopped the whole job. [#112](https://github.com/motherduckdb/motherduck-blueprints/pull/112)
- Deploys find existing Flights, Dives, and Guides by name in large organizations. They used to read only one page of results and could create a duplicate. [#113](https://github.com/motherduckdb/motherduck-blueprints/pull/113)
- The Dive preview lockfile picks up a fix for a high-severity `source-map-js` advisory. [#112](https://github.com/motherduckdb/motherduck-blueprints/pull/112)

## Upgrading from v0.7.4

v0.7.5 is a patch release. Generated repositories pin an exact version in `Makefile` and in every workflow reference, so nothing changes until you upgrade. Workflows that reference the floating `@v0` tag receive v0.7.5 automatically.

1. Run `make upgrade VERSION=0.7.5`. It updates `CLI_VERSION` and every Blueprints workflow and action pin to `v0.7.5`.
2. Run `npm audit fix` in `.dive-preview` to pick up `source-map-js` 1.2.2. `make upgrade` updates version pins only and does not change preview files.
3. Run `make validate`, and `make preview-smoke <blueprint-name>` for any Dive.
4. Open a pull request, review the diff, and merge it.

If you set organization Guide access by hand with `MD_SET_GUIDE_ACCESS` as a workaround, the next deploy applies the `access` value in `blueprint.yml`. Keep `access: organization` there for Guides that should stay shared.

## Bug Fixes

- Deploying a package with an organization Guide (`access: organization`) or a deployed role used to fail before any write with `Catalog Error: Table Function with name md_list_roles_for_user does not exist!`, even when the deployment identity was an organization admin. Because the check runs before the plan is applied, `plan`, `verify`, and `deploy` also stopped every other selected Flight and Dive. The check now reads the identity's roles with `SHOW ROLES TO USER`, and an admin role inherited through a custom role also passes. [#112](https://github.com/motherduckdb/motherduck-blueprints/pull/112) (fixes [#111](https://github.com/motherduckdb/motherduck-blueprints/issues/111))
- In organizations with many Flights, Dives, or Guides, a deploy could miss an existing resource and create a duplicate with the same name. The name lookup read one page of results: the default page size for Dives, and 1000 for Flights and Guides. Lookups now read every page. If the list changes while it is being read, the deploy stops and asks you to retry. [#113](https://github.com/motherduckdb/motherduck-blueprints/pull/113)

## Maintenance

- `source-map-js` in the Dive preview lockfile moves from 1.2.1 to 1.2.2 for [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q). [#112](https://github.com/motherduckdb/motherduck-blueprints/pull/112)
- The package and action pins move to 0.7.5. [#112](https://github.com/motherduckdb/motherduck-blueprints/pull/112)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.7.4...v0.7.5
