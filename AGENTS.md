# Agent Guide

This repository contains MotherDuck Blueprints for Dives, Flights, shares, and Guides.

## Token Handling

Never invent, print, or commit MotherDuck tokens. Local Dives preview uses `.dive-preview/.env`, which is ignored by Git. CI reads `MOTHERDUCK_TOKEN` from the GitHub Environment declared by the selected target; repository-level deployment secrets are deprecated. Shared repositories should use a MotherDuck service account token so deployments are not tied to a personal account.

## Project Layout

Customer workflows are short callers for `.github/workflows/reusable_*.yaml` in this repository. Keep reusable action pins aligned with the package version. Test both caller contracts and provider behavior when changing deployment orchestration.

Generated customer repositories receive their own operating guide from `src/md_blueprints/template_repo/AGENTS.md`. Keep it aligned with the deploy engine. Internal scaffold templates and empty-root READMEs are packaged for tooling but not emitted by `init`. Existing account resources follow `docs/adopt-existing-resources.md`; exporting is not automatic adoption, and CLI metadata IDs do not bind Flight/Dive manifests.

Wikipedia is the only active starter. Optional examples live under `examples/` and are not discovered until copied into an active package root. Keep root and packaged examples in sync.

`motherduck.yml` is the canonical repository manifest. It discovers packages below `flights/`, `dives/`, `guides/`, `roles/`, `projects/`, and the compatibility `blueprints/` root, defines shared variables, and declares the required `preview` and `prod` targets plus optional `staging`.

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

## MotherDuck CLI

Use `make install-deploy` to install the MotherDuck CLI version tested by Blueprints. CI import uses its JSON query interface. Deployment, planning, verification, and cleanup use the Python runtime to avoid a process per query. Keep native runtime installation in the action, not customer workflows. `make cli-smoke` checks the real binary's help and local scaffolds without credentials.

`make export` runs the read-only importer through the CLI and writes disabled packages for every visible Flight, Dive, and Guide. Individual native pulls do not include all adoption metadata. Preserve the importer's owner, schedule, pagination, and version checks. Local import alone may use `motherduck login`; CI and other live commands require the target token.

## Resources

`md-blueprints import` performs read-only discovery of Flights, Dives, and Guides and writes only with `--write`. Imported resources remain disabled, use stable-target IDs and owner guards, preserve existing schedules with `manageSchedule: false`, and raise the project's minimum CLI version. Bound IDs must never fall back to name-based creation. Maintain the import and adoption contracts in `docs/adopt-existing-resources.md`.

Declare resources in `blueprint.yml`:

- `resources.shares` names produced data products and their preview cleanup behavior.
- `resources.flights` deploys MotherDuck Flights from Python source and requirements files.
- `resources.dives` deploys Dives and required resources.
- `resources.guides` validates Guide files and deploys them when `deploy: true`; organization access requires an admin deployment identity.
- `resources.roles` reconciles production custom roles and memberships. Preview role deployment is always disabled.
- `resources.context` remains compatible, but `doctor` recommends `resources.guides`.

For Dives, keep `export const REQUIRED_DATABASES = ...` on one line in source when using local preview. The deploy engine strips that export and passes rendered `requiredResources` from `blueprint.yml`.

## Targets

Preview deployments are branch-scoped. Preview share/database names that may be cleaned up must include `${target.branch_slug}`. Without staging, `main` deploys production. With `targets.staging`, previews and `main` use the staging service account and a published release deploys production. Staging shares must differ from production shares; their database names may match.

Preview Flight schedules are disabled by target policy. Use `runOnDeploy: true` when a preview or production deploy should start an immediate run. Use `waitForRun: success` when dependent Dives should wait for the Flight run to succeed before resolving shares.

Preview selection expands through both upstream producers and downstream consumers. Production selection expands downstream only, so changing a consumer does not rerun an unchanged producer.

## Commands

Use these commands before opening PRs:

```bash
make validate
make mock-test
make example-smoke
make journey-smoke
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

CI installs the local `md-blueprints` package and calls the package command for change detection, validation, preview/staging/prod deployment, and preview cleanup. `tools/md_blueprints` remains as a compatibility wrapper for existing local commands.

The GitHub Action defaults to validation. Prefer named `target`, `branch`, `blueprints`, and `root` inputs in workflows; reserve `args` for advanced flags. Keep customer READMEs focused on the first deployment and put detailed options in `docs/`.

Deployment always runs preflight before writes and verifies live identity/dependency/status results afterward by default. `verify` is read-only and checks disabled imported bindings too. Keep tests proving that invalid IDs/owners block all writes and that postcheck failures fail CD. Postcheck opt-out must never bypass preflight.

## Changelog

Update `CHANGELOG.md` in every pull request, including docs-only changes. Keep entries under `Unreleased` until the change is released or merged into a reusable template.
