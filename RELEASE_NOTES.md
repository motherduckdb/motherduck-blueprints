## Highlights

- Preview cleanup is safer and more complete. It no longer drops a shared database whose name only happens to contain the branch name, it cleans up Guides scoped by topic, and preview deploys no longer cancel a running cleanup. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Repositories with `motherduck.yml` in a subdirectory get previews and push deploys again. Change detection found no changed packages there and skipped every deploy. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Validation catches more mistakes before any write: misspelled target overrides, duplicate YAML keys, variable cycles, and endorsing a Dive without the admin role. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)

## Upgrading from v0.7.8

v0.8.0 is a minor release because some manifests that v0.7.8 accepted now fail validation, and Flight `config` values change format. Generated repositories pin an exact version in `Makefile` and in every workflow reference, so nothing changes until you upgrade. Workflows that reference the floating `@v0` tag receive v0.8.0 automatically, so check the [Compatibility](#compatibility) items for those repositories now.

1. Run `make upgrade VERSION=0.8.0`. It updates `CLI_VERSION` and every Blueprints workflow and action pin to `v0.8.0`.
2. Run `make validate`. Fix any misspelled `targets.<name>` override, duplicate key, or variable cycle that it reports.
3. If a Flight reads `config` values, check the code that compares them. See [Compatibility](#compatibility).
4. Copy these files from the [v0.8.0 template](https://github.com/motherduckdb/blueprints-template) to pick up the fixes outside the package: `.gitignore`, `.dive-preview/src/md-sdk.tsx`, `docs/blueprint-yml-reference.md`, `docs/repository-reference.md`, and `docs/use-with-terraform.md`. `make upgrade` updates version pins and workflow secrets only.
5. Open a pull request and review its preview and plan before merging.

## Features

- The local Dive preview supports `useExport` and `exportAs` on query results, so Dives that export data build with `make preview-smoke`. Local exports are logged, and the saved Dive produces the real file. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- `plan` and `deploy` check for the admin role before any write when a Dive moves to `status: endorsed`. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- The Guide scaffold includes a branch-scoped preview title, so a new Guide validates as soon as you set `deploy: true`. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- `md-blueprints upgrade` works in a repository that uses the Makefile without Blueprints workflows, and `doctor` reports that layout as aligned. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)

## Bug Fixes

- Change detection with a subdirectory root. Before: with `root: analytics`, pull request previews and push deploys found no changed packages and deployed nothing. Now: changed files map to the right packages, and changes to the deploy or cleanup workflow still deploy everything. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Preview cleanup. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
  - Before: a push shortly before a pull request closed could cancel the running cleanup and redeploy the preview. Now: preview deploys wait instead of cancelling, and skip when the pull request is already closed.
  - Before: closing branch `dev` dropped a preview database with the fixed name `events_dev`. Now: cleanup refuses any name that does not change with the branch.
  - Before: a preview Guide scoped by its topic made cleanup fail for every resource on the branch. Now: it is removed like other preview Guides.
  - Before: branches named without ASCII letters or digits all shared the preview slug `preview` and could remove each other's previews. Now: each gets its own slug.
- Authoritative grants. Before: a member declared as `Alice@Example.com` was revoked when MotherDuck listed `alice@example.com`. Now: role members and share users are compared without regard to case, like the plan's username check. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Dive source. Before: a `REQUIRED_DATABASES` export with a TypeScript type annotation, or on the last line without a newline, was deployed with the Dive or left broken source behind. Now: it is removed, and an export that cannot be removed safely stops `plan` and `deploy` before any write. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Guide references. Before: references set in a `targets.<target>` override skipped the dependency graph, so a package could deploy before the Guide it references, and a reference to a deleted Dive or Flight stopped the plan with a raw SQL error. Now: both are checked and reported as plan errors. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Error messages. Before: when the MotherDuck CLI had an update available, a failed query reported only "New MotherDuck CLI available". Now: the real error is shown. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Preview pull request comment. Before: a `|` in a resource name broke the table, and share links rendered as plain "Open Share" text because GitHub drops `md:` links. Now: names are escaped and share URLs are shown as code. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Generated `.gitignore`. Before: packages named `build`, `dist`, or `notes` were silently ignored by Git. Now: only those directories at the repository root are ignored. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Scheduled doctor. Before: the shared GitHub rate limit on hosted runners could open a false "upgrade needed" issue. Now: the release lookup is authenticated on github.com, and a failed run links to its log. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- `guides` with a dbt project. Before: any multi-document or custom-tag YAML in the project, such as Kubernetes or CloudFormation files, stopped discovery. Now: those files are skipped with a note, and YAML syntax errors still fail. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- `import` checks `--resource` selectors before connecting to MotherDuck, and `init --force` writes nothing when a destination would escape the target directory. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)

## Compatibility

- Flight `config` values change format. Booleans are sent as `true` and `false` instead of `True` and `False`, an empty value as an empty string instead of `None`, and nested objects and lists as JSON instead of Python reprs. Plain strings are unchanged. Update Flight code that compares a value with `"True"` or `"False"`. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Overrides under a `targets.<name>` that `motherduck.yml` does not declare now fail validation, except `preview`, `staging`, and `prod`. Rename a misspelled target such as `production` to the declared name. Check any `id` it held, because v0.7.8 ignored it. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Duplicate keys in `motherduck.yml` and `blueprint.yml` now fail validation. Merge the duplicate blocks. v0.7.8 kept only the last one. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Variables that reference each other in a cycle now fail validation. Break the cycle. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- A multi-line `REQUIRED_DATABASES` export that is not a static array now stops `plan` and `deploy`. Make it a static array, or move the dynamic part out of the export. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Endorsing a Dive needs a deployment identity with the admin role at plan time. Use an admin service account, or leave the Dive at `ready`. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Preview cleanup no longer removes resources named with the old shared slug `preview`, because they cannot be attributed to one branch. Delete those by hand if you used branches without ASCII letters or digits. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- Removing `accessTokenName` or `maxRuntimeSec` from a manifest keeps the Flight's current value, as before. This is now documented. Set `maxRuntimeSec: 0` to remove a timeout. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)

## Maintenance

- Documentation updates. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
  - Both Terraform guide examples now validate in a generated repository.
  - The preview Dive status docs say that a Dive with a non-draft base `status` needs `targets.preview.status: draft`.
- Tests run the installed CLI end to end against a fake MotherDuck account instead of mocking internals, and `make mock-test` uses the same fake. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)
- The package and action pins move to 0.8.0. [#130](https://github.com/motherduckdb/motherduck-blueprints/pull/130)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.7.8...v0.8.0
