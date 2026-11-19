## Highlights

- MotherDuck now makes a new Dive readable only by its owner. Because a Dive that Blueprints creates is owned by the deployment identity, `plan` now reports a new Dive that declares no `grants`. [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)
- The starter Dive, new Dive and project scaffolds, and the examples share production Dives with the organization and keep preview Dives private, matching their shares. [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)
- Blueprints installs MotherDuck CLI `v1.5.6-2026-11-451`. [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)

## Upgrading from v0.10.6

v0.11.0 is a minor release because the default access of newly created Dives changes on the MotherDuck side, and new scaffolds now declare Dive `grants` to compensate. Existing manifests remain valid and deploy as before, and Dives that already exist keep their grants. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically. The local Dive preview is unchanged, so `make sync-preview` is not required.

1. Run `make upgrade VERSION=0.11.0`.
2. Run `make install-deploy` to install the pinned MotherDuck CLI.
3. Add `grants` to each Dive that does not exist yet and that other people need to open, for example `grants: {organization: true}` with `organization: false` under `targets.preview`. `make upgrade` does not edit manifests.
4. Run `make validate`. Then open a pull request and review the preview plan before merging. A new Dive without `grants` is reported in the plan.

Changes to review:

- [New Dives are private to the deployment identity](#compatibility)
- [The pinned MotherDuck CLI changes](#compatibility)

## Features

- `plan` reports a new Dive that declares no `grants`. The note states that only the deployment identity will be able to open the Dive and suggests declaring `grants`. Dives that already exist are not reported. [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)
- New packages declare Dive `grants`. Refer to the [Dives reference](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.11.0/docs/blueprint-yml-reference.md#dives). [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)
  - The starter Dive, the Dive in `make new-project` packages, and `make new-dive` packages grant `read` to the organization in production and to nobody in preview.
  - The `pageviews-weekly-trends` and `ncs-field-recovery` examples declare the same grants.
  - These grants match the shares of the same packages, which use `ORGANIZATION` access in production and `RESTRICTED` access in preview.

## Compatibility

- **New Dives are private to the deployment identity.** MotherDuck no longer gives a new Dive an organization `read` grant, unless the organization is exempt from this default. A Dive that Blueprints creates without `grants`, including every new preview Dive, can be opened only by the deployment identity. Declare `grants` on Dives that other people need to open. Dives that already exist keep their grants. Organizations that still receive the organization grant can restrict a Dive with `mode: authoritative` without `organization: true`, as before. Refer to the [Dives reference](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.11.0/docs/blueprint-yml-reference.md#dives). [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)
- **The pinned MotherDuck CLI changes.** Blueprints installs `v1.5.6-2026-11-451` instead of `v1.5.6-2026-11-382`. The commands and flags are unchanged. `dive --help` now shows how to share a Dive with SQL, and `dive push --help` states that pushing does not change who can open a Dive. Run `make install-deploy` after upgrading. [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)

## Maintenance

- The Dives reference, the repository reference, the setup guide, the Terraform guide, the examples index, the MotherDuck CLI page, and the agent instructions describe the new default access of Dives. The setup guide notes that a preview Dive is readable only by the deployment service account and describes the local preview as the way to view it before merging. [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)
- The package and action pins are updated to 0.11.0. [#177](https://github.com/motherduckdb/motherduck-blueprints/pull/177)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.10.6...v0.11.0
