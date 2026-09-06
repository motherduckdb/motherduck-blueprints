## Highlights

- Import existing Flights, Dives, and Guides with UUID bindings and review-first manifests, then verify live identities before and after deployment. [#64](https://github.com/motherduckdb/motherduck-blueprints/pull/64)
- Start with a smaller customer repository, clearer setup guidance, and a single active example. [#61](https://github.com/motherduckdb/motherduck-blueprints/pull/61) [#63](https://github.com/motherduckdb/motherduck-blueprints/pull/63)

## Features

- Use named GitHub Action inputs, optional staging with environment-scoped credentials, and release-based production promotion. [#61](https://github.com/motherduckdb/motherduck-blueprints/pull/61)
- Update CLI and action pins together with make upgrade, and check imported bindings with the read-only verify command. [#63](https://github.com/motherduckdb/motherduck-blueprints/pull/63) [#64](https://github.com/motherduckdb/motherduck-blueprints/pull/64)

## Bug Fixes

- Reject empty deployment selections, unsafe import/scaffold paths, missing bound IDs, and owner mismatches; validate migrations before writing. [#61](https://github.com/motherduckdb/motherduck-blueprints/pull/61) [#64](https://github.com/motherduckdb/motherduck-blueprints/pull/64)
- Generate valid packages for reserved or numeric-leading names and preserve preview files and existing Python environments on setup errors. [#43](https://github.com/motherduckdb/motherduck-blueprints/pull/43) [#61](https://github.com/motherduckdb/motherduck-blueprints/pull/61)

## Maintenance

- Add customer agent instructions, adoption guidance, and executable README journey tests. [#42](https://github.com/motherduckdb/motherduck-blueprints/pull/42) [#63](https://github.com/motherduckdb/motherduck-blueprints/pull/63) [#64](https://github.com/motherduckdb/motherduck-blueprints/pull/64)
- Refresh packaging, Ruff, pip, and pytz dependencies. [#48](https://github.com/motherduckdb/motherduck-blueprints/pull/48) [#58](https://github.com/motherduckdb/motherduck-blueprints/pull/58) [#59](https://github.com/motherduckdb/motherduck-blueprints/pull/59) [#60](https://github.com/motherduckdb/motherduck-blueprints/pull/60)

## Tooling and Release

- Coordinate generated-template and PyPI publication with provenance, SBOMs, and release preflight checks; keep the canonical template validation-only. [#44](https://github.com/motherduckdb/motherduck-blueprints/pull/44) [#62](https://github.com/motherduckdb/motherduck-blueprints/pull/62)
- Refresh provenance and PyPI publishing actions. [#45](https://github.com/motherduckdb/motherduck-blueprints/pull/45) [#56](https://github.com/motherduckdb/motherduck-blueprints/pull/56) [#57](https://github.com/motherduckdb/motherduck-blueprints/pull/57)

## Compatibility

- Schema version 1 and existing action args remain supported. Generated deployments use GitHub Environment secrets named MOTHERDUCK_TOKEN; update CLI/action pins together. Imported UUID bindings require 0.4.3 or newer. [#61](https://github.com/motherduckdb/motherduck-blueprints/pull/61) [#64](https://github.com/motherduckdb/motherduck-blueprints/pull/64)
- Import does not transfer ownership or copy data or secret values. Imported resources are disabled until reviewed, and deployment verification is not a substitute for customer data-quality tests. [#64](https://github.com/motherduckdb/motherduck-blueprints/pull/64)

## Verification

- Regression coverage includes import identity and pagination contracts, failed preflight blocking all writes, post-deployment drift, package installation, and the generated customer journey. [#64](https://github.com/motherduckdb/motherduck-blueprints/pull/64)
- Publication is gated on package build/smoke checks and generated-template validation. [Release workflow](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.4.3/.github/workflows/release.yaml)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.4.0...v0.4.3
