## Highlights

- Role names are compared without regard to case in role membership and share grants. Previously, with `mode: authoritative`, a role written with a capital letter was granted and then revoked on every deploy. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- Staging and production deploys queue every run. Previously, GitHub cancelled all but the newest waiting run, and the packages of a cancelled run were not deployed. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- The documentation gains an index by task and by error, and the field reference and the generated `AGENTS.md` are restructured for faster lookup by people and agents. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)

## Upgrading from v0.10.1

v0.10.2 is a patch release that also changes when Guide versions are appended and adds timeouts to the reusable workflows. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically. The local Dive preview is unchanged, so `make sync-preview` is not required.

1. Review the [v0.10.2 breaking-change entries](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.2/docs/breaking-changes.md#v0102).
2. Run `make upgrade VERSION=0.10.2`.
3. Run `make validate`. Then open a pull request and review the preview plan before merging.
4. When a Flight with `waitForRun: success` can run longer than two hours, set `timeout-minutes` under `with:` in `.github/workflows/deploy_blueprints.yaml`.

Changes to review:

- [Guide versions are appended only on change](#compatibility)
- [Staging and production deploys queue every run](#compatibility)
- [Reusable workflow jobs and native CLI statements have timeouts](#compatibility)

## Features

- The reusable deploy and cleanup workflows accept a `timeout-minutes` input for the jobs that use the MotherDuck token. The defaults are 120 minutes for deploys and 60 minutes for preview cleanup. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- `changed` prints a warning when a package was removed from the repository, because its deployed resources are not deleted and a scheduled Flight keeps running. The repository reference documents how to [retire a package](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.2/docs/repository-reference.md#retire-a-package). [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- A failed staging or production deploy ends with an explanation that later pushes deploy only their own changes and that the failed job must be run again. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)

## Bug Fixes

- Role names were compared case-sensitively in role membership and share grants, although MotherDuck stores role names in lowercase. They are now compared without regard to case, as Flight grants already were. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
  - With `mode: authoritative`, a share grant or an included role declared with a capital letter was granted and then revoked on every deploy.
  - A role declared with a capital letter was planned as a new role on every run.
  - A capitalised reference to an existing role was reported as a role that does not exist.
- YAML `<<` merge keys were rejected with "could not determine a constructor for the tag 'tag:yaml.org,2002:merge'". They now load, and a key that overrides a merged key is not reported as a duplicate. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- A manifest value written with Jinja-style braces, such as `{{ branch }}`, ended the command with a Python traceback. It now fails validation with an error that names the `${name}` template syntax. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- The preview comment on a pull request kept the report of the last successful preview after a later plan or deploy failed. The comment is now updated and states the failure. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- An export whose name starts with `REQUIRED_DATABASES`, such as `REQUIRED_DATABASES_BY_ENV`, was removed from a deployed Dive together with the `REQUIRED_DATABASES` export. Only the exact name is now removed. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)

## Compatibility

- **Guide versions are appended only on change.** Deploy appends a Guide version only when the content or the references differ from the live Guide, or when the manifest sets `externalId` and it differs. Previously, each deploy from a newer commit appended a version with identical content. Automation that expects the latest version's external ID to be the most recently deployed commit must set `externalId`. Refer to [guide-version-only-on-change](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.2/docs/breaking-changes.md#guide-version-only-on-change). [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- **Staging and production deploys queue every run.** The reusable deploy workflow sets `queue: max` on the concurrency group of its staging and production jobs. No action is required on github.com. Repositories on a GitHub Enterprise Server release that does not support `concurrency.queue` must remain on v0.10.1 until the server is upgraded. Refer to [stable-deploys-queue](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.2/docs/breaking-changes.md#stable-deploys-queue). [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- **Reusable workflow jobs and native CLI statements have timeouts.** Deploy jobs stop after 120 minutes, preview cleanup after 60 minutes, and jobs without the MotherDuck token after 15 minutes. A statement sent through the native MotherDuck CLI stops after 900 seconds. Repositories with longer deploy-time Flight runs must set `timeout-minutes`, and `MD_BLUEPRINTS_QUERY_TIMEOUT_SECONDS` adjusts the statement limit. Refer to [deploy-job-timeouts](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.2/docs/breaking-changes.md#deploy-job-timeouts). [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)

## Maintenance

- The documentation has an [index by task and by error](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.2/docs/README.md) with a section for agents. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
  - The field reference lists share, Flight, Guide, and role rules as tables and lists, and states that share `access` and `visibility` apply only when the share is created.
  - The repository reference describes what each workflow event deploys.
  - The generated `AGENTS.md` groups its constraints by topic.
- The release production job no longer keeps Git credentials in the checkout. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)
- The package and action pins are updated to 0.10.2. [#160](https://github.com/motherduckdb/motherduck-blueprints/pull/160)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.10.1...v0.10.2
