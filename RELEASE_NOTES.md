## Highlights

- Keep deployment, preview cleanup, and Doctor implementation in versioned reusable workflows, reducing generated customer workflows from 670 to 105 lines. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)
- Export existing Flights, Dives, and Guides into disabled, UUID-bound packages with `make export`, retaining ownership and deployment settings. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)

## Features

- Install the tested MotherDuck CLI with `make install-deploy` and use a local CLI login for read-only import. CI and other live commands continue to require the selected target token. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)

## Bug Fixes

- Wait for the exact submitted Flight run across supported runtimes. Handle both status and log schemas, preserve the failure reason when logs are unavailable, and stop downstream deployment after failed runs. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)
- Handle multiple native CLI JSON results and empty DDL output without retrying already-applied writes. Check Python timestamp dependencies before connecting. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)
- Import static JavaScript mount arrays with comments, unquoted keys, single quotes, trailing commas, and `as const`, without evaluating source expressions. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)

## Maintenance

- Update reusable workflow references together with CLI and direct action pins, preserving customer workflow settings. Keep generated documentation and dependency locks aligned. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)

## Tooling and Release

- Prepare version 0.5.0. Use the tested native CLI for import and CLI smoke checks, while bulk CI deployment keeps the Python runtime after live cycle comparison. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)

## Compatibility

- Schema version 1, existing expanded workflows, and UUID-bound imports remain supported. New reusable callers require the matching release. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)
- `make install-deploy` now installs the native CLI. Local live commands prefer it when available. To select the Python backend explicitly, install `md-blueprints[deploy]` and set `MD_BLUEPRINTS_SQL_BACKEND=duckdb`. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)

## Verification

- Passed the local Python 3.10–3.14 matrix, packaging and customer-journey smoke checks, typing, linting, and dependency audits. Isolated live cycles covered repeated updates, identity guards, run failures, preview isolation, and cleanup. [#66](https://github.com/motherduckdb/motherduck-blueprints/pull/66)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.4.3...v0.5.0
