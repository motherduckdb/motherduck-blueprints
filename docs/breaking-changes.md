# Breaking changes

This page lists every backward-incompatible change in MotherDuck Blueprints, newest release first. Use it when an upgrade makes `make validate`, `plan`, `deploy`, or preview cleanup fail, or when behavior changes after an upgrade.

## How to use this page

- **From an error.** Errors added by a breaking change end with `see docs/breaking-changes.md#<entry>`. Jump to that entry.
- **Before an upgrade.** Read every entry between your current version and the target version. Run each entry's **Find** step.
- **To change the behavior.** Each entry names the code under **Implemented in**. With the local tooling installed, it is in `.venv/lib/python*/site-packages/md_blueprints/`. Report problems or propose improvements in [motherduckdb/motherduck-blueprints issues](https://github.com/motherduckdb/motherduck-blueprints/issues) and name the entry.

Each entry has the same fields: **Changed in**, **What changed**, **Symptom**, **Find**, **Fix**, and **Implemented in**.

## v0.9.1

Generated repositories pick up these changes with `make upgrade VERSION=0.9.1`. Run `make validate` after the upgrade. Every change below either rejects a manifest that previously deployed something other than what it declared, or changes a value that was rendered incorrectly.

### branch-selects-preview

- **Changed in:** v0.9.1
- **What changed:** `--branch` scopes preview resources only.
  - `plan`, `deploy`, `verify`, and `render` with `--branch` and no `--target` use the `preview` target. Before, they used `prod`, so `deploy --branch feature/x` deployed to production.
  - `--branch` with any target other than `preview` is an error.
  - `cleanup` is unchanged.
- **Symptom:** `--branch scopes preview resources and cannot be used with target 'prod'`.
- **Find:** search scripts and workflows for `--branch` next to `--target prod` or `--target staging`.
- **Fix:** remove `--branch` for stable targets, or pass `--target preview`.
- **Implemented in:** `md_blueprints.cli._resolve_target`.

### variable-json-values

- **Changed in:** v0.9.1
- **What changed:** variables whose value is a boolean, empty, or a list render as JSON text, as Flight `config` values have since [flight-config-json-values](#flight-config-json-values). Before, they rendered as Python reprs.
  - `default: true` rendered as `True`. It is now `true`.
  - An empty `default:` rendered as `None`. It is now an empty string.
  - A list rendered as `['a', 'b']`. It is now `["a", "b"]`.
  - Strings and numbers are unchanged.
- **Symptom:** no error. A Flight `config` value or a resource name built from such a variable changes on the next deploy.
- **Find:** look for `variables` and `targets.<target>.variables` entries in `motherduck.yml` and `blueprint.yml` whose value is not a string or number, then run `make render-preview NAME` and `.venv/bin/md-blueprints render --target prod` to compare.
- **Fix:** none for Flight code that already expects JSON-style values. Code that compares with `"True"`, `"False"`, or `"None"` must compare with `"true"`, `"false"`, or `""`.
- **Implemented in:** `md_blueprints.template.as_text`.

### blueprint-target-variables-only

- **Changed in:** v0.9.1
- **What changed:** a top-level `targets.<target>` entry in `blueprint.yml` accepts only `variables`. Before, any other field was accepted and ignored, so a typo such as `varibles` silently kept the default values.
- **Symptom:** `make validate` fails with `<file>: Unknown field '<field>' at $.targets.<target>`.
- **Find:** `make validate`.
- **Fix:** correct the field name to `variables`. Resource overrides belong under `resources.<group>.<key>.targets.<target>`.
- **Implemented in:** `schemas/v1/blueprint.schema.json` (`blueprintTarget`).

### target-mode-values

- **Changed in:** v0.9.1
- **What changed:** `targets.<target>.mode` in `motherduck.yml` must be `preview` or `production`. Before, any string was accepted, and a typo such as `prodution` made `make export` refuse the target as a preview target.
- **Symptom:** `make validate` fails with `motherduck.yml: $.targets.<target>.mode must be one of 'preview', 'production'`.
- **Find:** `make validate`.
- **Fix:** set `mode: production` for stable targets and `mode: preview` for the preview target.
- **Implemented in:** `schemas/v1/motherduck-root.schema.json`.

### unterminated-template-reference

- **Changed in:** v0.9.1
- **What changed:** a `${` without its closing `}` fails validation. Before, it was deployed literally, for example as a share named `${var.share`.
- **Symptom:** `make validate` fails with `Unterminated template reference in '<value>'`.
- **Find:** `make validate`.
- **Fix:** add the closing `}`, or write `\${` for a literal `${`.
- **Implemented in:** `md_blueprints.template.Template.render`.

### schedule-cron-fields

- **Changed in:** v0.9.1
- **What changed:** `scheduleCron` is checked field by field, as the MotherDuck CLI checks it. Each field uses digits and `* , / -` only, without names such as `MON`, and stays within its range: minute 0-59, hour 0-23, day of month 1-31, month 1-12, and day of week 0-7. Before, only the number of fields was checked, so an invalid schedule failed at deploy time.
- **Symptom:** `make validate` fails with `flights.<key>.scheduleCron '<value>' is not a valid 5-field UTC cron expression`.
- **Find:** `make validate`.
- **Fix:** correct the field the message names, for example `0 6 * * 1` instead of `0 6 * * MON`.
- **Implemented in:** `md_blueprints.project.cron_problem`.

## v0.9.0

Generated repositories pick up these changes with `make upgrade VERSION=0.9.0`, except the preview change, which also needs `.venv/bin/md-blueprints sync-preview --write`. Workflows on the floating `@v0` tag pick up the plan change automatically. Release notes: [v0.9.0](https://github.com/motherduckdb/motherduck-blueprints/releases/tag/v0.9.0).

### preview-matches-dive-runtime

- **Changed in:** v0.9.0
- **What changed:** the local Dive preview builds against the production Dive runtime.
  - `@motherduck/react-sql-query` exports only the production v1 API: `useSQLQuery`, `useExport`, `useDiveState`, `useRunFlight`, `useFlightRun`, `quoteSqlIdentifier`, and `quoteSqlString`. Before, it also exported `useConnection`, `useConnectionStatus`, and `MotherDuckSDKProvider`, which production Dives do not have.
  - React and React DOM are 18.3.1, lucide-react 0.468.0, recharts 3.7.0, and d3 7.9.0, the versions production Dives load. Before, Dependabot had moved the preview to React 19 and lucide-react 1.x, and d3 was missing.
  - Tailwind CSS is pinned to 3.4.17.
- **Symptom:** `make preview-smoke NAME` or `make preview NAME` fails with `"useConnection" is not exported by "src/md-sdk.tsx"`, or with a missing lucide-react icon. Those Dives already failed when MotherDuck rendered them.
- **Find:** `grep -rnE "useConnection|useConnectionStatus|MotherDuckSDKProvider" dives projects blueprints`, then `make preview-smoke NAME` for each Dive.
- **Fix:** read data with `useSQLQuery`, and replace icons added after lucide-react 0.468.0 with ones that exist in it. Keep `.dive-preview/package.json` at the pinned versions.
- **Implemented in:** `.dive-preview/src/md-sdk.tsx`, `.dive-preview/package.json`, and `md_blueprints.init.run_sync_preview`.

### preview-attaches-required-databases-only

- **Changed in:** v0.9.0
- **What changed:** when a Dive exports `REQUIRED_DATABASES`, the local preview attaches only those databases, read-only, as MotherDuck does. Before, it attached your whole workspace and the required databases read-write.
- **Symptom:** `make preview NAME` shows `Catalog "<name>" does not exist` for a database the Dive queries but does not declare, or a write error on a required database. Those Dives already failed when MotherDuck rendered them. In return, the owner of a share's source database can now preview a Dive that requires the share under the same name.
- **Find:** compare the databases each Dive queries with its `REQUIRED_DATABASES` export and the `requiredResources` in its `blueprint.yml`.
- **Fix:** declare every database the Dive reads in `requiredResources` and `REQUIRED_DATABASES`, and keep Dive queries read-only. Run `make sync-preview` after `make upgrade` to get the new preview files.
- **Implemented in:** `.dive-preview/src/md-sdk-runtime.tsx` (`MotherDuckSDKProvider` and `attachRequiredDatabases`).

### share-plan-reports-changes

- **Changed in:** v0.9.0
- **What changed:** for a share whose `includePattern` or `grants` Blueprints manages, `plan` compares the live state. A share that already matches is `present` instead of `update`. The notes list the changes, such as `include pattern changes from unfiltered to [reporting.*]`, `will grant: role analysts`, and `will revoke: user old@example.com`, instead of `filter and/or grants will be reconciled`. Deploy skips `ALTER SHARE ... SET INCLUDE_PATTERN` when the live pattern already matches.
- **Symptom:** no error. Automation that parses `plan --json` and expects `update` for every managed share, or matches the old note text, sees `present` or the new notes.
- **Find:** search your scripts for `filter and/or grants will be reconciled` or for checks on share `action`.
- **Fix:** treat `present` as "nothing to change" and read the notes for the planned changes.
- **Implemented in:** `md_blueprints.deploy.Deployer._managed_share_plan` and `Deployer._reconcile_share`.

## v0.8.0

Generated repositories pick up these changes with `make upgrade VERSION=0.8.0`. Workflows on the floating `@v0` tag pick them up automatically. Release notes: [v0.8.0](https://github.com/motherduckdb/motherduck-blueprints/releases/tag/v0.8.0).

### flight-config-json-values

- **Changed in:** v0.8.0
- **What changed:** Flight `config` values are sent as JSON-style strings. Before, they were Python reprs.
  - `true` / `false` were sent as `True` / `False`. They are now `true` / `false`.
  - An empty value was sent as `None`. It is now an empty string.
  - Objects and lists were sent as Python reprs such as `{'a': 1}`. They are now JSON such as `{"a": 1}`.
  - Strings and numbers are unchanged.
- **Symptom:** no error. Flight code that compares a value with `"True"`, `"False"`, or `"None"`, or that parses a Python repr, behaves differently after the next deploy.
- **Find:** look for `config:` values in `blueprint.yml` that are booleans, empty, objects, or lists. Then search Flight code: `grep -rnE "\"(True|False|None)\"|ast.literal_eval" flights projects blueprints`.
- **Fix:** compare with `"true"` and `"false"`, treat `""` as unset, and parse objects and lists with `json.loads`.
- **Implemented in:** `md_blueprints.project.config_value`.

### unknown-target-override

- **Changed in:** v0.8.0
- **What changed:** a `targets.<name>` override must name a target declared in `motherduck.yml`, or one of `preview`, `staging`, and `prod`. Before, any other name was silently ignored, including an adopted `id` inside it.
- **Symptom:** `make validate` fails with `<file>: resources.<group>.<key>.targets names unknown target(s) <name>; motherduck.yml declares: <targets>.`
- **Find:** `make validate`.
- **Fix:** rename the override to the declared target, for example `production` to `prod`. If it held an `id`, check that the id is the resource you meant to bind, because v0.7.8 and earlier never used it.
- **Implemented in:** `md_blueprints.project.Project._check_override_targets`.

### duplicate-yaml-keys

- **Changed in:** v0.8.0
- **What changed:** `motherduck.yml` and `blueprint.yml` must not repeat a key in the same mapping. Before, YAML kept the last value and dropped the others.
- **Symptom:** `make validate` fails with `Invalid YAML in <file>: duplicate key '<key>' in "<file>", line <n>, column <m>.`
- **Find:** `make validate`.
- **Fix:** merge the duplicate blocks into one. Check which values were active before: only the last block applied.
- **Implemented in:** `md_blueprints.schema._UniqueKeyLoader`.

### variable-cycle

- **Changed in:** v0.8.0
- **What changed:** variables that reference each other in a cycle, or nest too deeply to resolve, fail validation. Before, the unresolved `${var.name}` text was deployed as part of resource names.
- **Symptom:** `make validate` fails with `<file>: variables for target '<target>': variables reference each other in a cycle or nest too deeply: <names>.`
- **Find:** `make validate`.
- **Fix:** give one of the variables a literal value. To keep a literal `${...}` in a value, escape it as `\${...}`.
- **Implemented in:** `md_blueprints.project.Project._render_variables`.

### dive-required-databases-static

- **Changed in:** v0.8.0
- **What changed:** a multi-line `export const REQUIRED_DATABASES = ...` in a Dive must be a static array, so deploy can remove it before upload. Before, a non-static multi-line export was half removed and the Dive was deployed with broken source. Single-line exports, type annotations, `as const`, and trailing comments work as before.
- **Symptom:** `plan` and `deploy` fail before any write with `Dive <package>.<key>: REQUIRED_DATABASES must be a static array.`
- **Find:** `make preview-smoke NAME=<package>` builds the Dive, and `plan` reports every affected Dive.
- **Fix:** write the array literally, for example `[{ type: "share", path: "md:_share/...", alias: "orders" }]`. Declare the deployed mounts in `blueprint.yml` under `requiredResources`, which deploy uses instead of the export.
- **Implemented in:** `md_blueprints.deploy.strip_required_databases_export` and `Deployer._preflight_dive_sources`.

### endorse-requires-admin

- **Changed in:** v0.8.0
- **What changed:** `plan` and `deploy` check for the `admin` role before any write when a Dive moves to `status: endorsed`. Before, a non-admin deploy applied Flight and Dive changes and then failed at the status change.
- **Symptom:** `RBAC preflight failed: target requires the admin role (<package> endorses Dive <title>); the deployment identity has: <roles>.`
- **Find:** `grep -rn "status: endorsed" --include=blueprint.yml .`
- **Fix:** deploy with a service account that has the `admin` role, or keep the Dive at `status: ready` and endorse it in MotherDuck.
- **Implemented in:** `md_blueprints.deploy.Deployer._preflight_endorsements`.

### guide-override-references-checked

- **Changed in:** v0.8.0
- **What changed:** Guide `references` inside a `targets.<target>` override are checked and join the dependency graph, like base references. Before, they were not checked, and the referencing package could deploy before the Guide it reads.
- **Symptom:** `make validate` fails with `guide <package>.<key> reference <n> uses missing blueprint '<name>'` or `uses missing <package>.<type>.<resource>`. A dependency cycle that only appears when overrides are combined fails with `Blueprint dependency cycle`.
- **Find:** `make validate`.
- **Fix:** correct the reference, or declare the referenced resource. To break a cycle, keep the references for one direction in the base resource.
- **Implemented in:** `md_blueprints.project.Project._validate_contracts`.

### preview-cleanup-fixed-names

- **Changed in:** v0.8.0
- **What changed:** preview cleanup refuses a share, database, Flight, Dive, or Guide whose name does not change with the branch, even when it happens to contain the branch name. Before, closing branch `dev` dropped a shared preview database named `events_dev`.
- **Symptom:** cleanup fails with `Plan contains errors: ... refusing to delete preview <type> because its name does not change with the branch, so other previews share it: <name>.` A cleanup with an error removes nothing for that branch.
- **Find:** `.venv/bin/md-blueprints cleanup --target preview --branch <branch> --dry-run`.
- **Fix:** include `${target.branch_slug}` in preview names, for example with the starter's `${var.preview_suffix}`. Set `cleanup: false` on resources that previews share on purpose.
- **Implemented in:** `md_blueprints.deploy.Deployer.cleanup_plan` and `Deployer._preview_scope_error`.

### preview-slug-non-ascii

- **Changed in:** v0.8.0
- **What changed:** a branch name without ASCII letters or digits, such as `修正`, gets the preview slug `preview_<hash>`. Before, all such branches shared the slug `preview`. Cleanup no longer removes resources named with the old `preview` slug, because they cannot be traced to one branch.
- **Symptom:** previews for those branches get new names. Old previews named with `preview` stay after cleanup.
- **Find:** list preview shares and databases whose names end with `_preview` and no branch slug.
- **Fix:** delete the old preview resources by hand once no open pull request uses them.
- **Implemented in:** `md_blueprints.project.branch_slug` and `Deployer.cleanup_plan`.

### preview-deploy-concurrency

- **Changed in:** v0.8.0
- **What changed:** in the reusable deploy workflow, preview deploys no longer cancel a running deploy or cleanup for the same branch (`cancel-in-progress: false`). A deploy for a pull request that is already closed skips its job.
- **Symptom:** rapid pushes to a pull request wait for the running preview deploy instead of cancelling it. GitHub keeps one pending job per group, so a deploy can still replace a pending cleanup, and that preview then needs a manual cleanup.
- **Find:** look for skipped **Deploy Preview Blueprints** jobs on closed pull requests.
- **Fix:** none needed. To clean up a preview by hand, run `.venv/bin/md-blueprints cleanup --target preview --branch <branch>` with the preview token.
- **Implemented in:** the `compute_changes` and `deploy-preview` jobs of `.github/workflows/reusable_deploy_blueprints.yaml` in motherduckdb/motherduck-blueprints.

### preview-comment-share-url

- **Changed in:** v0.8.0
- **What changed:** the preview pull request comment shows share URLs as code in a `URL` column. Before, it rendered `[Open Share](md:_share/...)`, which GitHub showed as plain text with no URL. Names that contain `|` are escaped.
- **Symptom:** tools that parse the comment for `Open Share` links find none.
- **Find:** search automation for `Open Share`.
- **Fix:** read the share URL from the code span in the `URL` column.
- **Implemented in:** `md_blueprints.deploy.Deployer._deploy_blueprint`.

### gitignore-rooted

- **Changed in:** v0.8.0 (template `.gitignore`)
- **What changed:** the generated `.gitignore` ignores `build/`, `dist/`, and `notes/` only at the repository root. Before, it ignored directories with those names at any depth, including packages.
- **Symptom:** after you copy the new `.gitignore`, `git status` shows directories named `build`, `dist`, or `notes` inside packages.
- **Find:** `git status --short`.
- **Fix:** commit packages that were silently ignored. Add specific patterns for build output you do not want tracked.
- **Implemented in:** the template `.gitignore`.

## v0.7.8

Release notes: [v0.7.8](https://github.com/motherduckdb/motherduck-blueprints/releases/tag/v0.7.8).

### caller-token-secret

- **Changed in:** v0.7.8
- **What changed:** the deploy and cleanup workflows must pass `MOTHERDUCK_TOKEN` to the reusable workflows by name. GitHub gives a reusable workflow an empty environment secret unless the caller passes it. `secrets: inherit` passes nothing outside the motherduckdb organization.
- **Symptom:** previews, deploys, and cleanup fail with `MOTHERDUCK_TOKEN is required`, although the environment secret exists. `make doctor` warns about callers that pass no token or use `secrets: inherit`.
- **Find:** `make doctor`.
- **Fix:** run `make upgrade`, or add this to the calling job:

  ```yaml
  secrets:
    MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}
  ```

- **Implemented in:** `md_blueprints.upgrade.add_token_secrets`, `md_blueprints.maintenance.workflows_missing_token_secret`, and the `workflow_call` secrets of the reusable deploy and cleanup workflows.
