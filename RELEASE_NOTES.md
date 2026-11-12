## Highlights

- Dives accept `grants`, which decide who can open a deployed Dive. Roles, users, and the organization receive `read` in additive or authoritative mode, as Flight `grants` do for `run`. [#172](https://github.com/motherduckdb/motherduck-blueprints/pull/172)
- Blueprints installs MotherDuck CLI `v1.5.6-2026-11-382`, the MotherDuck release of 2026-11-11. [#172](https://github.com/motherduckdb/motherduck-blueprints/pull/172)
- Three optional examples cover a SQL transformation, a data freshness monitor, and a Guide. [#166](https://github.com/motherduckdb/motherduck-blueprints/pull/166)

## Upgrading from v0.10.4

v0.10.5 is a patch release that adds an optional field and updates the pinned MotherDuck CLI. Existing manifests deploy as before, and a Dive without `grants` keeps its current access. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically. The local Dive preview is unchanged, so `make sync-preview` is not required.

1. Run `make upgrade VERSION=0.10.5`.
2. Run `make install-deploy` to install the pinned MotherDuck CLI.
3. Run `make validate`. Then open a pull request and review the preview plan before merging.
4. Optionally declare `grants` on Dives as described under [Features](#features).

Changes to review:

- [The pinned MotherDuck CLI changes](#compatibility)
- [Existing repositories do not receive the new examples](#compatibility)

## Features

- `resources.dives.<key>.grants` manages `read` grants on a Dive. Deploy issues `GRANT READ ON DIVE` and `REVOKE READ ON DIVE` after it creates or updates the Dive. Refer to the [Dives reference](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.5/docs/blueprint-yml-reference.md#dives). [#172](https://github.com/motherduckdb/motherduck-blueprints/pull/172)
  - `roles` and `users` name roles and MotherDuck usernames, and `organization: true` grants every member of the organization. Names are compared without regard to case.
  - `mode: additive`, the default, keeps grantees that are not declared. `mode: authoritative` revokes them, including grants made in the MotherDuck UI or with SQL.
  - MotherDuck gives a new Dive an organization `read` grant. With `mode: authoritative` and without `organization: true`, deploy revokes that grant, which restricts the Dive to the declared grantees. `plan` states this for a Dive that does not exist yet.
  - `plan` lists what deploy will grant and revoke. It stops before any write when a role does not exist and is not declared in the same run, or when a username is not in the organization.
  - Grants apply in every target, and target overrides merge into `grants`.
- `doctor` includes authoritative Dive grants in its warning about resources that revoke undeclared access. [#172](https://github.com/motherduckdb/motherduck-blueprints/pull/172)
- Three optional examples ship under `examples/`. None deploys until it is copied into a package root. [#166](https://github.com/motherduckdb/motherduck-blueprints/pull/166)
  - `pageviews-weekly-trends` is a SQL transformation Flight that reads another package through an input, with its share and Dive.
  - `data-freshness-monitor` is an hourly Flight that records freshness and row-count checks, fails the run on a problem, and can post to a webhook from a Flight secret.
  - `pageviews-guide` is a Guide with catalog, Flight, and Dive references.

## Compatibility

- **The pinned MotherDuck CLI changes.** Blueprints installs `v1.5.6-2026-11-382` instead of `v1.5.6-2026-11-37`. The commands and flags are unchanged. The help for `dive list --all` and `flight list --all` now states what they list: Dives shared with the identity, and every Flight in the organization for an admin. Run `make install-deploy` after upgrading. [#172](https://github.com/motherduckdb/motherduck-blueprints/pull/172)
- **Existing repositories do not receive the new examples.** `make upgrade` updates the version pins and does not add files. To use an example, generate a template with `md-blueprints init` in an empty directory and copy the example from its `examples/` directory. No action is required otherwise. [#166](https://github.com/motherduckdb/motherduck-blueprints/pull/166)

## Maintenance

- The documentation covers Dive sharing: who can open a deployed Dive, how Dive, share, and Flight grants combine, and how `flight cancel` applies to runs started by other people. [#172](https://github.com/motherduckdb/motherduck-blueprints/pull/172)
- A new examples index lists every example by purpose, shows how the examples connect, and states the practices they share. [#166](https://github.com/motherduckdb/motherduck-blueprints/pull/166)
- The documentation gains diagrams of the deployment flow, target selection, package selection, the adoption steps, the split of ownership with Terraform, and the layout of each example. [#166](https://github.com/motherduckdb/motherduck-blueprints/pull/166)
- The starter Flight and Dive READMEs describe what the packages deploy and which patterns to reuse. [#166](https://github.com/motherduckdb/motherduck-blueprints/pull/166)
- The package and action pins are updated to 0.10.5. [#166](https://github.com/motherduckdb/motherduck-blueprints/pull/166)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.10.4...v0.10.5
