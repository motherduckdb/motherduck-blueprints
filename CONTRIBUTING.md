# Contributing

Thanks for your interest in improving MotherDuck Blueprints.

## Where to contribute

- **This repository (`motherduckdb/motherduck-blueprints`)** is the source of truth for the `md-blueprints` CLI, the GitHub Action, the docs, and the customer repository template. Open issues and pull requests here.
- **[`motherduckdb/blueprints-template`](https://github.com/motherduckdb/blueprints-template)** is generated from this repository on each release. Do not open pull requests there; changes to it are overwritten. If something in a generated repository looks wrong, the fix belongs in `src/md_blueprints/template_repo/` in this repository.

## Before opening a pull request

Run the local checks:

```bash
make setup
make validate
make mock-test
make example-smoke
```

If your change touches a blueprint with a Dive, also run:

```bash
make preview-smoke <blueprint-name>
```

A few repository rules, enforced by review and tests:

- Update `CHANGELOG.md` in every pull request, including docs-only changes. Add entries under `Unreleased`.
- The customer template under `src/md_blueprints/template_repo/` mirrors several top-level paths (`docs/`, `blueprints/`, `schemas/`, `.dive-preview/`, `templates/blueprint/`, `context/`, `motherduck.yml`). A drift test fails if the copies diverge, so change both together.
- When changing layout, commands, target behavior, or resource semantics, update the matching public docs in the same pull request.

## Reporting issues

Use [GitHub issues](https://github.com/motherduckdb/motherduck-blueprints/issues) for bugs and feature requests. For product questions about MotherDuck itself, use the [MotherDuck Community Slack](https://slack.motherduck.com/) or [MotherDuck support](https://motherduck.com/docs/getting-started).

For security issues, see [SECURITY.md](SECURITY.md) — please do not report vulnerabilities through public issues.
