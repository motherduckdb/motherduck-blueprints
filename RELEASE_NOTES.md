## Highlights

- Write repository Guides with your own agent. `make guides` gathers read-only context from your packages, SQL, and dbt project, and the new **Prepare Guide context** workflow does the same in CI. [#82](https://github.com/motherduckdb/motherduck-blueprints/pull/82) [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Safer deployments: long branch names no longer share preview resources, target overrides are validated, and commands reject flags they do not support. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Easier to fit your organization: self-hosted runners and custom Python versions in the reusable workflows, and a new guide for teams that also use the [MotherDuck Terraform provider](https://github.com/motherduckdb/terraform-provider-motherduck). [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)

## Upgrading from v0.6

v0.7.0 is a pre-1.0 minor release, so it can contain behavior changes. Generated repositories pin an exact version in `Makefile` and in every workflow reference, so nothing changes until you upgrade. Workflows that reference the floating `@v0` tag receive v0.7.0 automatically.

1. Run `make upgrade VERSION=0.7.0`. It updates `CLI_VERSION` and every Blueprints workflow and action pin to `v0.7.0`.
2. Run `make validate`. Validation is stricter in this release. Fix any reported manifest errors before you continue.
3. Open a pull request, review the diff, and check the preview plan in the PR comment before merging.
4. Optional: generate a fresh template with `md-blueprints init` in an empty directory and copy the files `make upgrade` does not add:
   - `.github/workflows/prepare_guide_context.yaml` for Guide context in CI.
   - `Makefile` for `NAME=` support and failing typos.

Check these changes before merging. Details are under [Compatibility](#compatibility):

- Stricter validation of target overrides, share access and visibility, and preview names.
- New preview names for branches with long names.
- Custom workflow steps that import `md_blueprints` or PyYAML after the action runs.
- Manual staging and production runs from branches other than the default branch.
- `init-guides` and `update-guides` now print an agent brief instead of writing Guides.

## Features

- Guide authoring for agents: [#82](https://github.com/motherduckdb/motherduck-blueprints/pull/82)
  - `make guides` prints a read-only brief with declared packages, resources, data contracts, SQL sources, and existing Markdown.
  - `make guides DBT=/path/to/project` adds dbt descriptions, columns, tests, accepted values, and relationship hints.
- Guide context in CI: [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
  - A reusable **Prepare Guide context** workflow uploads the brief as a `guide-context` artifact.
  - The action accepts `command: guides` and a `dbt` input.
  - A `stdout-file` output keeps context out of logs.
- Reusable workflow inputs for your runners: `runs-on` (a label or a JSON array for self-hosted runners), `python-version`, and `timeout-minutes` for Prepare Guide context. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- The action installs Blueprints into its own environment and adds a `python` output for later steps. Command output streams to the job log while it runs. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Clearer plans and checks: [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
  - `plan` notes Flights, Dives, and Guides that matched an existing resource by name, and lists the grants `mode: authoritative` will revoke.
  - `doctor` warns about authoritative mode, `blueprint.yml` files that `include` does not match, and workflows missing from your repository.
- Command help and input: every command has its own `--help`, errors list valid targets and packages, and Makefile targets accept `NAME=`. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- New docs: [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
  - [Use with Terraform](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.7.0/docs/use-with-terraform.md) covers resource ownership, delivering the deployment token from Terraform, and using Terraform-owned shares.
  - Setup now covers prerequisites, removing the example, adapting environment and branch names, and adding Blueprints to an existing repository.

## Bug Fixes

- Long preview branch names: before, branches whose names matched in the first 48 characters shared preview resources, so closing one PR could remove another's preview. Now those slugs end in a hash of the branch name, and cleanup also removes previews created under the old names. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Target overrides: before, a wrong type or misspelled field under `targets.<target>` was ignored during deployment. Now validation fails and names the file, resource, and target. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- `deploy --dry-run`: before, it deployed for real. Now it fails and points to `plan`. Other unsupported flags fail the same way. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- `init --force`: before, it replaced existing files such as `README.md`, `.gitignore`, and `LICENSE`. Now it only adds missing files and lists the ones it kept. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Makefile input: before, `make valdiate` succeeded silently and `make new-flight "my flight"` created `flights/my`. Now both fail with a message. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Preview cleanup: before, a database name that deployment accepted could stop cleanup half-way. Now names are quoted the same way everywhere. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Preview deploy and cleanup: before, closing a PR during a deploy could leave resources behind. Now cleanup waits for a running deploy on the same branch. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Flight waits: before, `waitForRun: success` gave up after a fixed ten minutes. Now it waits for at least `maxRuntimeSec` plus two minutes and explains what was already applied. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Dive source: before, only a single-line `REQUIRED_DATABASES` export was removed at deploy time. Now multi-line exports work too. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Other fixes: [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
  - Escaped `\${...}` placeholders inside variables stay literal.
  - `upgrade --offline` no longer contacts the network.
  - The starter Flight stops on invalid config instead of using production defaults.
  - Preview comments are no longer duplicated on busy repositories.

## Compatibility

- `init-guides` and `update-guides` now print an agent brief, like `make guides`. They no longer write Guide files or `.guide-state.json`. Existing Guide files stay unchanged. Ask your agent to update Guides from the brief. [#82](https://github.com/motherduckdb/motherduck-blueprints/pull/82)
- Validation is stricter. Run `make validate` after upgrading and fix what it reports: [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
  - Resources are checked again after `targets.<target>` overrides are applied.
  - Share `access` must be `ORGANIZATION`, `RESTRICTED`, or `UNRESTRICTED`, and `visibility` must be `DISCOVERABLE` or `HIDDEN`, in any case.
  - Preview share and database names must contain the branch slug as a separate `_` part, such as `events_preview_feature_x`.
  - Duplicate role members, included roles, grants, and include patterns are rejected, as are Guide fields longer than their limits.
- Branches with slugs of 48 or more characters get new preview names. Nothing to do: cleanup removes previews under both names. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- The action no longer installs packages into the job's Python. If a later step imports `md_blueprints` or PyYAML, run it with the action's `python` output. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Manual `staging` and `prod` runs of **Deploy Blueprints** must start from the default branch. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Dependabot pull requests are validated but no longer attempt a preview. Dependabot runs receive no environment secrets. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- CLI usage errors exit with status 2 instead of 1. Update scripts that compare exit codes. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- New role scaffolds use `deploy: false`. Set `deploy: true` once the deployment identity has admin rights. Existing roles are unchanged. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Local preview now uses React and React DOM 19.2.8. Run `make preview-smoke <blueprint-name>` for custom Dives. [#82](https://github.com/motherduckdb/motherduck-blueprints/pull/82)
- Deprecated, still working, and printing a notice: [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
  - `resources.context`. Rename it to `resources.guides`.
  - `make new-blueprint`. Use `make new-project`.
  - `tools/md_blueprints`. Use `make` targets or `.venv/bin/md-blueprints`.

## Maintenance

- Maintainer-only content moved from the shipped docs into `MAINTAINING.md`. A test keeps documented action pins equal to the package version and blocks shipped docs from linking to tooling-only files. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- The release check requires release notes for the tagged version. The template push token is sent as a header instead of being embedded in the clone URL. Artifact actions match the versions used in CI. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Generated repositories get deploy path filters and CODEOWNERS entries for files they actually contain. Workflow checkouts no longer persist credentials. [#92](https://github.com/motherduckdb/motherduck-blueprints/pull/92)
- Dependabot groups React and React DOM updates. The unused direct Arrow dependency was removed from the local preview. [#82](https://github.com/motherduckdb/motherduck-blueprints/pull/82)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.6.0...v0.7.0
