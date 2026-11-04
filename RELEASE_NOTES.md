## Highlights

- Flights accept `grants`, which give roles, users, or the whole organization the `run` permission. Since the MotherDuck release of 2026-10-22, viewers of a Dive can run a Flight that they own or hold `run` on, so Dives deployed with Blueprints can now run Flights for their viewers. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
- The starter Flight, the Flight scaffolds, and the NCS example list `duckdb==1.5.6` in `requirements.txt`. Since the MotherDuck release of 2026-11-02, the Flight runtime installs only the packages in `requirements.txt`, so Flights that import `duckdb` without listing it fail. `validate` and `doctor` identify these Flights. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
- Blueprints installs MotherDuck CLI `v1.5.6-2026-11-37`, the MotherDuck release of 2026-11-02. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)

## Upgrading from v0.9.2

v0.10.0 is a minor release that adds manifest fields and changes the pinned MotherDuck CLI. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically, but the repository steps below still apply.

1. Run `make upgrade VERSION=0.10.0`.
2. Run `make install-deploy` to install MotherDuck CLI `v1.5.6-2026-11-37`, and `make sync-preview` to refresh the local Dive preview.
3. Run `make validate`. For every Flight that it reports as importing `duckdb` without listing it, add `duckdb==1.5.6` to that Flight's `requirements.txt`. Repositories created from an earlier template carry the starter Flight, which requires this change. `make upgrade` does not modify existing packages.
4. Open a pull request and review the preview plan before merging.

Changes to review:

- [`motherduck flight logs` prints the last 100 lines by default](#compatibility)
- [Changed error text for failed Flight runs](#compatibility)

## Features

- Flights accept `grants` with `roles`, `users`, `organization`, and `mode`. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
  - `plan` reads the live grants, lists the grants that `deploy` will add or revoke, and stops before any write when a role does not exist or a user is not in the organization.
  - `deploy` issues `GRANT RUN ON FLIGHT` before any deploy-time run. `mode: authoritative` revokes undeclared grants, including grants made outside Blueprints, and `doctor` issues a warning for it.
  - Grantee names are compared without regard to letter case, as MotherDuck compares them.
- Flights accept `chart`, a Mermaid file that MotherDuck displays as the run chart in the Flight Explainer. As with `motherduck flight push`, an empty file clears the chart and an omitted field leaves the live chart unchanged. `make export` and `md-blueprints import` write the live chart of a Flight to `chart.mmd`. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
- `validate` and `doctor` issue a warning for each Flight that imports `duckdb` while its `requirements.txt` does not list it, and state the version to add. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
- MotherDuck CLI `v1.5.6-2026-11-37` adds `motherduck flight get-run`, `motherduck flight explain`, and the `--tail`, `--head`, and `--offset` options for `motherduck flight logs`. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)

## Bug Fixes

- The starter Flight failed with "No module named 'duckdb'" after the MotherDuck release of 2026-11-02, because its `requirements.txt` did not list `duckdb`. The starter, the `make new-flight` and `make new-project` scaffolds, and the NCS example now list `duckdb==1.5.6`. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
- When a deploy-time Flight run failed, the error identified the run only by its number. It now names the Flight and states the `motherduck flight logs` command that prints the complete log. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)

## Compatibility

- **`motherduck flight logs` prints the last 100 lines by default.** The MotherDuck CLI that `make install-deploy` installs no longer prints the complete log. Blueprints does not depend on this command. Scripts and runbooks that read its output must pass `--tail` or `--head` with a larger value and page with `--offset`. Refer to [cli-flight-logs-last-100-lines](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.0/docs/breaking-changes.md#cli-flight-logs-last-100-lines). [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
- **Changed error text for failed Flight runs.** The error for a failed deploy-time run begins with the Flight name and spans several lines. The warning for deprovisioned users reads "members or grantees" instead of "members or share grantees". Automation that matches the previous text must be updated. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)

## Maintenance

- The documentation describes how viewers of a Dive run Flights, states that Dive source cannot yet reference a Flight ID per target, assigns Flight `run` grants to Blueprints in the Terraform ownership guide, and states that secure views on shares are available in the MotherDuck web application but are not managed by Blueprints. The local Dive preview comments describe the current rule for running Flights. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)
- ruff is updated to 0.17.2. [#147](https://github.com/motherduckdb/motherduck-blueprints/pull/147)
- The package and action pins are updated to 0.10.0. [#150](https://github.com/motherduckdb/motherduck-blueprints/pull/150)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.9.2...v0.10.0
