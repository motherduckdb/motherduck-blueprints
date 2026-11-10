## Highlights

- `md-blueprints --help` and the generated `make help` list their commands by task and show a typical workflow. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- Newly generated repositories provide `make plan` and `make verify`, which read MotherDuck without changing it. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- `md-blueprints new` prints the files it wrote and the next steps, and each scaffolded package has a README that describes its files and its preview behavior. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)

## Upgrading from v0.10.3

v0.10.4 is a patch release that changes command output and messages only. Validation, planning, deployment, and cleanup behavior are unchanged. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically. The local Dive preview is unchanged, so `make sync-preview` is not required.

1. Run `make upgrade VERSION=0.10.4`.
2. Run `make validate`. Then open a pull request and review the preview plan before merging.
3. Optionally adopt the new Makefile targets as described under [Compatibility](#compatibility).

Changes to review:

- [Existing repositories keep their Makefile](#compatibility)
- [Additional messages on standard error](#compatibility)

## Features

- `md-blueprints --help` groups the commands under four tasks: creating packages, checking locally, reading or changing MotherDuck, and maintaining the repository. It also shows a typical workflow. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- The Makefile of a newly generated repository has two read-only targets, `make plan` and `make verify`. Both accept `TARGET=<target>`, `BRANCH=<branch>` for a preview, and `NAME=<package>`, and both require the token of the selected target. Its `make help` lists the targets by task. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- `md-blueprints new` prints the files it wrote and the next steps for the kind of package it created. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- The README of a scaffolded Flight, Dive, Guide, or role package describes the files of the package, its behavior in previews, and the next steps. Previously it contained one generic line. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- `doctor` ends with a `result:` line that states whether anything requires attention. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)

## Bug Fixes

- Several errors named a problem without a remedy. They now state what to do. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
  - A preview target without `--branch` explains that preview resources are named after the branch and names the two ways to proceed.
  - An unknown target lists the declared targets. For `staging`, the error refers to the staging setup section of the setup guide.
  - `dive-source` without a package lists the packages that declare a Dive.
  - `new` without a kind or a name shows examples.
- `validate --target <stable target> --branch <name>` accepted `--branch` without comment, although the option applies only to previews. It now prints a warning that `--branch` is ignored. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- `changed` without `--base` or `--all` listed every package without explanation. It now prints a note on standard error that states why. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)

## Compatibility

- **Existing repositories keep their Makefile.** `make upgrade` updates the version pins and does not rewrite the Makefile, so `make plan`, `make verify`, and the grouped `make help` are present only in repositories generated from this release. To adopt them, generate a template with `md-blueprints init` in an empty directory, copy its `Makefile`, and reapply any local changes. No action is required otherwise. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- **Additional messages on standard error.** `validate` and `changed` print the warning and the note described above on standard error, and `doctor` and `new` print additional lines on standard output. Standard output of `changed`, `plan`, `render`, and `verify` and all exit codes are unchanged. Automation that treats any output on standard error as a failure must pass `--all` or `--base` to `changed`. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)

## Maintenance

- The repository reference and the generated `README.md` and `AGENTS.md` describe `make plan`, `make verify`, and `make help`. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)
- The package and action pins are updated to 0.10.4. [#164](https://github.com/motherduckdb/motherduck-blueprints/pull/164)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.10.3...v0.10.4
