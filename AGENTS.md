# Agent Guide

This repository contains MotherDuck Blueprints for Dives, Flights, shares, and future context-layer assets.

## Token Handling

Never invent, print, or commit MotherDuck tokens. Local Dives preview uses `.dive-preview/.env`, which is ignored by Git. CI uses the `MOTHERDUCK_TOKEN` repository secret. Shared repositories should use a MotherDuck service account token so deployments are not tied to a personal account.

## Project Layout

`motherduck.yml` is the canonical repository manifest. It includes `blueprints/*/blueprint.yml`, defines shared variables, and declares the `preview` and `prod` targets. It is a catalog and policy file, not the deployable project boundary.

Each deployable project lives in `blueprints/<blueprint-name>/`:

- `blueprint.yml` - resource manifest.
- `src/flight.py` - optional Flight source.
- `src/requirements.txt` - optional Flight dependencies.
- `src/dive.tsx` - optional Dive source.
- `README.md` - blueprint-specific notes.

Do not add deployable resources under top-level `dives/`, `flights/`, or `bundles/`; deployable work belongs in blueprint packages. Use lowercase slug names for blueprints (`a-z`, `0-9`, and `-`) so paths, selectors, and rendered resource names stay predictable.

Treat a blueprint package as one logical project or data product. Do not split or group packages by MotherDuck organization, service account, user, or database ownership. Databases are resources inside a project package; service accounts are target or resource identity choices.

Use `make new-blueprint <blueprint-name>` as the starting example for new projects. The generated package should stay deployable: its Flight creates starter data and a share, and its Dive reads that share.

When changing layout, commands, target behavior, or resource semantics, update the relevant public docs in the same PR. Check at least `README.md`, `docs/`, blueprint `README.md` files, `templates/blueprint/README.md`, `context/README.md`, `.github/pull_request_template.md`, and this guide for drift.

## Resources

Declare resources in `blueprint.yml`:

- `resources.shares` names produced data products and their preview cleanup behavior.
- `resources.flights` deploys MotherDuck Flights from Python source and requirements files.
- `resources.dives` deploys Dives and required resources.
- `resources.context` validates future context-layer files but must use `deploy: false` until MotherDuck exposes a deployment API.

For Dives, keep `export const REQUIRED_DATABASES = ...` on one line in source when using local preview. The deploy engine strips that export and passes rendered `requiredResources` from `blueprint.yml`.

## Targets

Preview deployments are branch-scoped. Preview share/database names that may be cleaned up must include `${target.branch_slug}`. Production names are stable and deploy through the `motherduck-production` GitHub Environment.

Preview Flight schedules are disabled by target policy. Use `runOnDeploy: true` when a preview or production deploy should start an immediate run. Use `waitForRun: success` when dependent Dives should wait for the Flight run to succeed before resolving shares.

## Commands

Use these commands before opening PRs:

```bash
make validate
make mock-test
make example-smoke
```

When a blueprint includes a Dive, also run:

```bash
make preview-smoke <blueprint-name>
```

Use these for local iteration:

```bash
make setup
make preview <blueprint-name>
make preview-smoke <blueprint-name>
make render-preview <blueprint-name>
```

CI installs the local `md-blueprints` package and calls the package command for change detection, validation, preview/prod deployment, and preview cleanup. `tools/md_blueprints` remains as a compatibility wrapper for existing local commands.

## Changelog

Update `CHANGELOG.md` in every pull request, including docs-only changes. Keep entries under `Unreleased` until the change is released or merged into a reusable template.
