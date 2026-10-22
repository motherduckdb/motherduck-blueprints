## Highlights

- A deployment that names a branch can no longer reach a stable target. `plan`, `deploy`, `verify`, and `render` with `--branch` and no `--target` now use the `preview` target instead of `prod`, and `--branch` with any other target is rejected. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- `make validate` now detects manifests that previously deployed something other than what they declared, and every validation error names the file, and where relevant the target, that caused it. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- The local Dive preview resolves shares that are shared with the user, stops with an explanation instead of loading indefinitely, and reports a Dive that fails to render instead of displaying a blank page. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)

## Upgrading from v0.9.0

v0.9.1 is a patch release that also tightens validation. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically, including the stricter validation, and still require step 3.

1. Review the [v0.9.1 breaking-change entries](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.1/docs/breaking-changes.md#v091).
2. Run `make upgrade VERSION=0.9.1`.
3. Run `make sync-preview` (or `.venv/bin/md-blueprints sync-preview --write`) to apply the Dive preview changes in `.dive-preview/`.
4. Run `make validate` and correct any manifest that it now rejects. Then open a pull request and review the preview plan before merging, paying particular attention to Flight `config` values and resource names that are built from boolean, empty, or list variables.
5. Update any scripts or workflows that pass `--branch` together with a stable `--target`.

Changes to review:

- [`--branch` selects the preview target](#compatibility)
- [Variables render as JSON text](#compatibility)
- [Stricter manifest validation](#compatibility)

## Features

- `validate` and `doctor` issue warnings for the following conditions, without failing validation. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
  - A manifest named `blueprint.yaml`, or `blueprint.yml` with different letter case, which Linux CI runners do not read.
  - A role name that MotherDuck does not accept. Previously, this was detected only by `plan`.
  - A `REQUIRED_DATABASES` export that is not a static array, which stops `plan` and `deploy`.
  - `REQUIRED_DATABASES` aliases that differ from the `requiredResources` of the Dive, which cause the local preview and the deployed Dive to attach different databases.
- New repositories created with `md-blueprints init` receive next steps, and `init --force` reports version pins only for the files it wrote. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- The CLI suggests the closest command when a command name is mistyped, lists all commands when it is run without one, and suggests the repository root when it is run from a subdirectory. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)

## Bug Fixes

- When MotherDuck rejected the deployment token, some share lookups reported the rejection as a warning and the command continued. `plan`, `deploy`, `verify`, `cleanup`, and `import` now stop and name the token variable, the target, and the GitHub Environment that holds the secret. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- Verification reported only the first problem it found. It now reports every problem across the checked resources, and after `deploy` it states that the deployment was applied and that no rollback was attempted. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- Schema errors, such as an unknown or missing field, did not name the file. Errors now begin with the path of the `blueprint.yml` or `motherduck.yml`, and a file that is not UTF-8 text is reported as such. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- Duplicate-name errors reported one duplicate at a time and did not name the packages involved. They now list every duplicated name with the resources that use it, and explain the placeholder branch that `validate` uses for preview names. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- `make upgrade VERSION=<version>` accepted a version that had not been released and wrote the pins, after which every `make` target failed, including `make upgrade`. `upgrade` now refuses a version newer than the latest release before it writes any pin, issues a warning before a downgrade, and `make upgrade` runs with the installed CLI so that it can correct an unusable pin. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- The generated Makefile ignored `PYTHON=` once `.venv` existed, and reported only a pip error when Python was older than 3.10. It now reports the Python version and the corrective step, both before it creates `.venv` and when an existing `.venv` is too old. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- `make preview` and `make preview-smoke` built against previously installed packages after `package-lock.json` changed. They now reinstall the preview dependencies when the lock file changes. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- `md-blueprints init --force` in an existing repository re-created starter packages that had been removed. It now leaves them out. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- `make new-role` with a name that starts with a digit produced a role name that MotherDuck does not accept. It now prefixes the name, for example `role_2025_analysts`. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- The local Dive preview had the following defects. Run `make sync-preview` to apply the corrections. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
  - It found only shares that the user owns, so a share created by the CI service account was reported as unresolved. It now also searches the shares that are shared with the user.
  - It used the placeholder token from `.env.example` and loaded indefinitely when MotherDuck could not be reached. It now treats the placeholder as missing, names `.dive-preview/.env` in its token messages, and stops after 60 seconds without a response.
  - A Dive that failed to render produced a blank page. The preview now displays the error.
- `changed --base <revision>` selected every package without explanation when the revision could not be compared. It now issues a warning that names the cause. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- A missing token produced only CI guidance during local use, and a variable that differs only in letter case, such as `motherduck_token`, was ignored without notice. The message now gives local guidance outside CI and names the differently cased variable. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- Errors that contained the word "environment" in a path or variable name received GitHub Environments advice, and local file permission errors received MotherDuck permission advice. Hints are now added only when they match the cause. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- An interrupted command printed a Python traceback. It now exits with code 130 and a short message. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)

## Compatibility

- **`--branch` selects the preview target.** `plan`, `deploy`, `verify`, and `render` with `--branch` and no `--target` use `preview`, and `--branch` with any other target is rejected. Remove `--branch` from commands for stable targets. Refer to [branch-selects-preview](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.1/docs/breaking-changes.md#branch-selects-preview). [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- **Variables render as JSON text.** Variables whose value is a boolean, empty, or a list render as `true`, an empty string, or `["a", "b"]` instead of `True`, `None`, or `['a', 'b']`. Flight code that compares with `"True"`, `"False"`, or `"None"` must compare with `"true"`, `"false"`, or `""`. Refer to [variable-json-values](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.1/docs/breaking-changes.md#variable-json-values). [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- **Stricter manifest validation.** Run `make validate` and correct each manifest that it rejects. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
  - A top-level `targets.<target>` entry in `blueprint.yml` accepts only `variables`. Refer to [blueprint-target-variables-only](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.1/docs/breaking-changes.md#blueprint-target-variables-only).
  - `targets.<target>.mode` in `motherduck.yml` must be `preview` or `production`. Refer to [target-mode-values](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.1/docs/breaking-changes.md#target-mode-values).
  - A `${` without its closing `}` is rejected. Refer to [unterminated-template-reference](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.1/docs/breaking-changes.md#unterminated-template-reference).
  - Each `scheduleCron` field must use only digits and `* , / -` and stay within its range. Refer to [schedule-cron-fields](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.9.1/docs/breaking-changes.md#schedule-cron-fields).
- **Changed error text.** Validation errors begin with the file path, and duplicate-name errors use a new multi-line format. Automation that matches the previous error text must be updated. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)

## Maintenance

- The release notes of every published release, and the v0.9.0 changelog entry, are rewritten in a formal register. [#144](https://github.com/motherduckdb/motherduck-blueprints/pull/144)
- The documentation describes the target selection of `--branch`, the rules for `scheduleCron`, the rendering of non-string variables, and the order of steps for removing the starter packages. [#145](https://github.com/motherduckdb/motherduck-blueprints/pull/145)
- The package and action pins are updated to 0.9.1. [#144](https://github.com/motherduckdb/motherduck-blueprints/pull/144)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.9.0...v0.9.1
