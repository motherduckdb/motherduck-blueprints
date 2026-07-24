# Agent Guide

This repository contains MotherDuck Blueprints for Dives, Flights, shares, and Guides.

## Token Handling

Never invent, print, or commit MotherDuck tokens. Local Dives preview uses `.dive-preview/.env`, which is ignored by Git. CI uses the `MOTHERDUCK_TOKEN` repository secret. Shared repositories should use a MotherDuck service account token so deployments are not tied to a personal account.

## Project Layout

`motherduck.yml` is the canonical repository manifest. It discovers packages below `flights/`, `dives/`, `guides/`, `roles/`, `projects/`, and the compatibility `blueprints/` root, defines shared variables, and declares the `preview` and `prod` targets.

Each deployable package has a `blueprint.yml`, source files, and a package README. Use typed roots when ownership follows the resource type:

- `flights/**/<name>/` for Flight producers and their shares/outputs.
- `dives/**/<name>/` for Dives and their inputs.
- `guides/**/<name>/` for version-controlled Guides.
- `roles/**/<name>/` for production RBAC roles and memberships.
- `projects/**/<name>/` when any resource combination truly ships, previews, and rolls back together.

Nested organizational directories are allowed, but the package's immediate parent directory must match its lowercase blueprint slug. Existing `blueprints/<name>/` packages remain supported and are not required to migrate.

Use top-level `inputs` and `outputs` to connect independently deployed packages. Outputs name package-local shares; inputs reference `blueprint.output` contracts in the same repository. Use literal share URLs for external repositories.

Use `make new-flight`, `make new-dive`, `make new-guide`, `make new-role`, or `make new-project`. `make new-blueprint` remains an alias for a complete project scaffold.

When changing layout, commands, target behavior, or resource semantics, update the relevant public docs in the same PR. Check at least `README.md`, `docs/`, package READMEs, `.github/pull_request_template.md`, and this guide for drift.

## Resources

Declare resources in `blueprint.yml`:

- `resources.shares` names produced data products and their preview cleanup behavior.
- `resources.flights` deploys MotherDuck Flights from Python source and requirements files.
- `resources.dives` deploys Dives and required resources.
- `resources.guides` validates Guide files and deploys them when `deploy: true`; organization access requires an admin deployment identity.
- `resources.roles` reconciles production custom roles and memberships. Preview role deployment is always disabled.
- `resources.context` remains compatible, but `doctor` recommends `resources.guides`.

For Dives, keep `export const REQUIRED_DATABASES = ...` on one line in source when using local preview. The deploy engine strips that export and passes rendered `requiredResources` from `blueprint.yml`.

## Targets

Preview deployments are branch-scoped. Preview share/database names that may be cleaned up must include `${target.branch_slug}`. Production names are stable and deploy through the `motherduck-production` GitHub Environment.

Preview Flight schedules are disabled by target policy. Use `runOnDeploy: true` when a preview or production deploy should start an immediate run. Use `waitForRun: success` when dependent Dives should wait for the Flight run to succeed before resolving shares.

Preview selection expands through both upstream producers and downstream consumers. Production selection expands downstream only, so changing a consumer does not rerun an unchanged producer.

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
