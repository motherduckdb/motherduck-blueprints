## Highlights

- Every backward-incompatible change now has an entry in `docs/breaking-changes.md`, shipped in generated repositories. Each entry gives the exact error, a command to find affected files, the fix, and the code that implements the check. [#132](https://github.com/motherduckdb/motherduck-blueprints/pull/132)
- Errors added in v0.8.0 now end with `This check is new; see docs/breaking-changes.md#<entry>`, so you and your agents can go straight from a failure to its fix. [#132](https://github.com/motherduckdb/motherduck-blueprints/pull/132)

## Upgrading from v0.8.0

v0.8.1 changes no behavior. It only adds pointers to error messages and adds the new doc.

1. Run `make upgrade VERSION=0.8.1`.
2. Copy `docs/breaking-changes.md`, `AGENTS.md`, and `README.md` from the [v0.8.1 template](https://github.com/motherduckdb/blueprints-template), keeping any local edits. `make upgrade` updates version pins and workflow secrets only.
3. If you are upgrading from v0.7.8 or earlier, read the [v0.8.0 entries](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.8.1/docs/breaking-changes.md#v080) first.

## Features

- The template `AGENTS.md` tells agents to read the breaking-change entries newer than the current `CLI_VERSION` before `make upgrade`, and to follow the entry an error names. The template README and the upgrade guide link to the doc. [#132](https://github.com/motherduckdb/motherduck-blueprints/pull/132)

## Maintenance

- A test checks that every error pointer names an existing entry. The repository guide requires an entry and a pointer for each future breaking change. [#132](https://github.com/motherduckdb/motherduck-blueprints/pull/132)
- The package and action pins move to 0.8.1. [#132](https://github.com/motherduckdb/motherduck-blueprints/pull/132)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.8.0...v0.8.1
