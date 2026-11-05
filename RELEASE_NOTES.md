## Highlights

- `changed` selects every package that a change affects. Previously, it did not select the package that a file was moved out of, or packages below directories with non-ASCII names, so those packages were not redeployed. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- Values substituted into templates, such as the branch name, are treated as literal text. A valid Git branch name that contains `${` no longer fails validation or resolves as a template reference. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- Deploying an unchanged Guide whose file uses CRLF line endings no longer appends a new Guide version on every deploy. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)

## Upgrading from v0.10.0

v0.10.1 is a patch release that also rejects two manifest values that validation previously accepted by mistake. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically. The local Dive preview is unchanged, so `make sync-preview` is not required.

1. Review the [v0.10.1 breaking-change entry](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.1/docs/breaking-changes.md#v0101).
2. Run `make upgrade VERSION=0.10.1`.
3. Run `make validate` and correct any `schemaVersion: true` or `waitForRun: 0` that it now rejects. Then open a pull request and review the preview plan before merging.

Changes to review:

- [A boolean no longer matches a number in validation](#compatibility)
- [Changed error text for variable cycles](#compatibility)

## Bug Fixes

- `changed` selects packages more completely. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
  - When a file was moved from one package to another, Git rename detection listed only the destination, so the package that lost the file was not redeployed. Both packages are now selected.
  - Git quoted paths below directories with non-ASCII names, so those paths matched no package. They are now matched.
- Deploying an unchanged Guide whose file uses CRLF line endings appended a new Guide version on every deploy, because the comparison translated line endings while MotherDuck stores the file unchanged. An unchanged Guide is now left as it is. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- Values substituted into templates were parsed as templates again. A valid Git branch name such as `feature/${x}` failed with an unterminated template reference error, or resolved as a reference when it reached a resource through a variable. The same applied to rendered share names, producer outputs, and variable values. Substituted values are now always literal text. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- Validation states that a preview Guide must include the branch in its title or its topic, but a separate check rejected every preview Guide that kept the production title. A preview Guide whose topic includes the branch may now keep the production title. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- `import --write` wrote `motherduck.yml` in the encoding of the system locale. It now writes UTF-8. `${` in the keys of exported Flight configuration mappings is now escaped, so it is no longer read as a template reference. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- A Flight or Guide source file that is not UTF-8 failed validation with a Python decoding error. The error now names the file and states the required encoding. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- The timeout error for `waitForRun: success` reported one polling interval more than the time actually waited. It now reports the time waited. [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)

## Compatibility

- **A boolean no longer matches a number in validation.** Validation compares fixed values as JSON Schema does. `schemaVersion: true` and `waitForRun: 0` are now rejected. Previously, `waitForRun: 0` deployed as `waitForRun: false`. Write `schemaVersion: 1`, and `waitForRun: false` or `waitForRun: success`. Refer to [schema-booleans-are-not-numbers](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.1/docs/breaking-changes.md#schema-booleans-are-not-numbers). [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)
- **Changed error text for variable cycles.** Variables no longer have a nesting limit, so the error reads `variables reference each other in a cycle` instead of `in a cycle or nest too deeply`. Automation that matches the previous text must be updated. Refer to [variable-cycle](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.1/docs/breaking-changes.md#variable-cycle). [#153](https://github.com/motherduckdb/motherduck-blueprints/pull/153)

## Maintenance

- ruff is updated to 0.17.3. [#152](https://github.com/motherduckdb/motherduck-blueprints/pull/152)
- The package and action pins are updated to 0.10.1. [#152](https://github.com/motherduckdb/motherduck-blueprints/pull/152)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.10.0...v0.10.1
