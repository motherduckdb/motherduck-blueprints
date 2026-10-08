## Highlights

- `plan` and `deploy` check role `members` and share `grants.users` against your organization's users before any write. A misspelled or unknown username now stops the plan instead of failing at its `GRANT` partway through a deploy. [#117](https://github.com/motherduckdb/motherduck-blueprints/pull/117)
- The `blueprint.yml` reference lists `F32` as an allowed Flight size on the Free Trial plan. [#117](https://github.com/motherduckdb/motherduck-blueprints/pull/117)

## Upgrading from v0.7.6

v0.7.7 is a patch release. Generated repositories pin an exact version in `Makefile` and in every workflow reference, so nothing changes until you upgrade. Workflows that reference the floating `@v0` tag receive v0.7.7 automatically.

1. Run `make upgrade VERSION=0.7.7`. It updates `CLI_VERSION` and every Blueprints workflow and action pin to `v0.7.7`.
2. To pick up the new guidance, copy `AGENTS.md`, `docs/blueprint-yml-reference.md`, and `docs/setup-your-repository.md` from the [v0.7.7 template](https://github.com/motherduckdb/blueprints-template). `make upgrade` updates version pins only and does not change docs.
3. Run `make validate`, then run `plan` for each target that deploys roles or share user grants and review the output.
4. Open a pull request, review the diff, and merge it.

Check the [username check](#compatibility) before upgrading if your manifests list role members or share grant users.

## Features

- Username check for roles and shares. [#117](https://github.com/motherduckdb/motherduck-blueprints/pull/117)
  - When a deployed role declares `members` or a share declares `grants.users`, `plan` and `deploy` list the organization's users with the MotherDuck [`GET /v1/users`](https://motherduck.com/docs/sql-reference/rest-api/users-list/) endpoint.
  - A username that is not in the organization marks the role or share as an error, and nothing is written. Usernames are compared without regard to case.
  - A deprovisioned user prints a warning and does not block the deploy.
  - Private regions can set `MOTHERDUCK_HOST` to their regional API host. Other regions need no setting.

## Compatibility

- Unknown usernames now fail the plan. If a manifest lists a member or grantee that is not in the organization, the deploy stops before any write with `member(s) are not users in this organization` or `grant user(s) are not users in this organization`. Fix the spelling or remove the user. [#117](https://github.com/motherduckdb/motherduck-blueprints/pull/117)
- The check needs the `member_management.view_all_members` privilege, which the preset roles include. If the user list cannot be read, Blueprints prints a warning and skips the check, and deployment behaves as in v0.7.6. [#117](https://github.com/motherduckdb/motherduck-blueprints/pull/117)

## Maintenance

- Documentation updates. [#117](https://github.com/motherduckdb/motherduck-blueprints/pull/117)
  - `docs/blueprint-yml-reference.md` describes the username check for roles and share grants, and lists `F32` on Free Trial.
  - `docs/setup-your-repository.md` has a troubleshooting row for unknown usernames.
  - The template `AGENTS.md` describes the username check.
- The package and action pins move to 0.7.7. [#117](https://github.com/motherduckdb/motherduck-blueprints/pull/117)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.7.6...v0.7.7
