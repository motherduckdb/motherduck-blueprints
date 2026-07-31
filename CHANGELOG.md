# Changelog

All notable changes to this repository are documented here.

Update this file in every pull request. Add entries under `Unreleased` until the change is released or merged into a reusable template.

## Unreleased

### Added

- Added an end-to-end Guides-as-code how-to covering scaffolding, branch-scoped previews, access, references, planning, deployment, and troubleshooting.
- Added a project-pattern walkthrough for the NCS Field Recovery Explorer.
- Added PyPI and GitHub Release package distribution, release provenance attestations, SBOM publication, and multi-version CI coverage.
- Added Apache-2.0 licensing to both maintained repositories and complete package and action metadata.
- Added a standalone Blueprint Authoring Guide plus colocated Guides in the NCS and generated project examples.

### Changed

- Expanded the root, repository, setup, Guide package, and generated-template documentation to surface Guide deployment and the NCS public-data example.
- Pinned generated workflows to the same immutable release tag as their local CLI instead of a floating action tag.
- Hardened release ordering, external preflight, post-publish canaries, dependency installation, and repository policy checks.
- Replaced the flat CLI argument surface with strict per-command help and option validation.

### Fixed

- Made the compatibility matrix install the complete test dependency set, retained Python 3.10 resource traversal support, and audited dependencies with the repository's constrained packaging toolchain.
- Prevented template publication from racing the floating action tag and prevented unreleased source changes from rebuilding an already released package version.
- Made all typed scaffolds emit YAML-safe strings for reserved slugs and aliases, derive valid SQL aliases for numeric-leading blueprint names, normalize external-share URLs, and reject explicitly empty aliases.
- Rejected duplicate blueprint names across typed roots and command options that do not apply to the selected scaffold kind before writing files.
- Made `new project` use the complete canonical starter manifest and README instead of a reduced duplicate implementation.
- Fixed the full test-suite mypy failure in the cleanup SQL regression test and added tests to the strict CI type-check.
- Restored Python 3.10 compatibility in generated Flights by replacing the Python 3.11-only UTC API.
- Made Guide and project scaffolds include branch-scoped preview Guide titles so changing `deploy` to `true` validates immediately.
- Made unknown Make targets fail while preserving documented positional commands such as `make new-guide revenue-metrics`.

## v0.4.0 - 2026-07-30

### Added

- Added the `projects/ncs-field-recovery` public-data project, with a SODIR FactMaps ingestion Flight, published share, transparent oil-recovery metrics, and an interactive field-comparison Dive.
- Added declarative Dive governance statuses (`draft`, `ready`, `endorsed`, and `archived`) with live status transitions in deployment plans, status reconciliation through `MD_UPDATE_DIVE_STATUS`, and backward-compatible preservation when production status is omitted.
- Added typed `flights/`, `dives/`, `guides/`, `roles/`, and `projects/` roots with recursive discovery, root-specific validation, and typed CLI/Make scaffolds.
- Added same-repository `inputs` and share-backed `outputs`, `${inputs.<name>.*}` rendering, and Dive mounts through `requiredResources[].input`.
- Added dependency graph validation, preview connected-component expansion, production downstream expansion, deterministic producer-first deployment, and dependency-safe cleanup.
- Added full Guide create/update/version/metadata/access/delete lifecycle support, typed catalog and resource references, dependency ordering, and opt-in deployment through `resources.guides`.
- Added production RBAC role and membership reconciliation, additive or authoritative share grants, and an admin capability preflight.
- Added filtered-share `includePattern`, Flight `maxRuntimeSec`, and Dive governance `status` support.
- Kept `resources.context` compatible while recommending `resources.guides`.

### Changed

- Updated the repository and generated-template workflows to the current `actions/checkout`, `actions/setup-python`, `actions/setup-node`, and `actions/github-script` releases.
- Enforced `draft` status for all preview Dives and made generated examples deploy production Dives as `ready`.
- Split the Wikipedia example into an independently deployable Flight producer and Dive consumer, preserving its stable production resource names.
- Made local Dive preview source lookup manifest-driven and added multi-Dive selection with `DIVE=<resource-key>`.
- Prepared the package and generated repository template for `md-blueprints` v0.4.0 while keeping `schemaVersion: 1` and legacy `blueprints/` packages compatible.
- Hardened preview cleanup so Flights, Dives, deployed Guides, shares, and databases must be branch-scoped, cannot reuse their production identifiers, and require an explicit target-policy opt-in.
- Validated live preview operations with the requested branch instead of the validator's mock branch.
- Restricted included manifests and resource source files to their repository and blueprint package boundaries, including after symlink resolution.
- Made `md-blueprints init --force` refuse template destinations that resolve outside the target directory through symlinks.
- Published the CLI and composite action directly from repository tags, removed the PyPI release dependency, and made generated repositories install local tooling from their matching Git tag.
- Delayed GitHub Release publication and floating-tag updates until generated-template preflight and publishing succeed, and narrowed the default release workflow permission to read-only.
- Made closed-pull-request cleanup evaluate both the branch and base manifests so previews for added and removed packages are deleted.

### Fixed

- Made the NCS field ingestion transactional, collision-safe across concurrent runs, and covered by source pagination, transformation, and rollback tests.
- Improved the NCS Field Recovery Dive's mobile layout, keyboard focus, toggle state, loading/error announcements, chart description, and table semantics.
- Made update checks reject only newer releases instead of treating an unreleased local version as outdated, and made the scheduled doctor close resolved upgrade issues.
- Made CI run for every pull request and main-branch push so docs and generated-template drift cannot bypass the mirror tests.
- Made Guide deployments reconcile content, resolved references, metadata, and access independently, preventing duplicate versions and unauthorized redundant access mutations while still clearing removed references.
- Made CI and production deployment workflows react to `roles/**` changes in both this repository and generated customer repositories.
- Updated the Dive preview lockfiles to resolve the PostCSS source-map path traversal advisory.
- Made generated repositories reinstall local tooling after `CLI_VERSION` changes instead of silently reusing an older executable.
- Excluded floating action tags from release triggers and rejected prerelease release-tag shapes before they can update the generated template or stable action major.
- Pinned DuckDB below 1.5.5 until MotherDuck supports that client release, preventing live action installs from selecting an incompatible runtime.
- Made plans reject missing Guide references, inherited roles, and share-grant roles before deployment can mutate earlier resources.
- Made Guide resource references honor explicit IDs, filtered shares support declarative reset, and preview Guide cleanup tolerate validation-only production definitions.
- Made standalone Dive scaffolds query the connected share's catalog instead of assuming starter Flight tables.
- Enforced exactly one Dive data-source selector in editor and runtime schemas.
- Allowed scaffolded Dive inputs to reference any non-empty output key supported by the manifest contract.
- Made scaffolded Dives validate local producer outputs and preserve the actual share URL or rendered share name used by local preview.
- Attached declared Dive databases before local preview queries run and surfaced share-resolution or attach failures in the connection state.
- Made `render` and `dive-source` validate their target before returning generated output or source paths.
- Rejected duplicate aliases within a Dive's required resources.
- Failed deployment planning immediately when a required share is missing and no selected Flight is configured to produce it on deploy.
- Serialized cleanup events per branch and made delete operations idempotent when another cleanup run removes a resource after planning.

## v0.3.0 - 2026-07-02

### Added

- Added Dependabot configuration for customer workflow action updates.
- Added a scheduled Blueprints Doctor workflow that opens a tracking issue when the pinned action or schema needs attention.
- Added `md-blueprints init <dir>` and packaged customer-template assets for generated repository setup.
- Added `requiredCliVersion` support in the root manifest.
- Added versioned packaged schema directories under `src/md_blueprints/schemas/v1/` with mirrored editor schemas under `schemas/v1/`.
- Added pytest coverage and strict mypy checking for the packaged CLI modules.
- Added deploy, template-rendering, include-glob, and CLI exit-code unit coverage for the module split.
- Added migration registry tests that simulate a future schema migration diff, write, and idempotency flow.
- Added the versioned `md-blueprints` Python package, console command, packaged schema resources, and GitHub Action wrapper.
- Added `md-blueprints doctor`, `md-blueprints check-updates`, and `md-blueprints migrate --to latest` as schema maintenance surfaces.
- Added tooling and schema versioning documentation for package pinning, compatibility policy, and customer upgrade flow.
- Added package and release-artifact smoke tests for the wheel, sdist, packaged schemas, and local GitHub Action wrapper.
- Added release external-setup preflight checks for the PyPI project and generated template repository.
- Added release version checks and GitHub Release publishing for tagged package artifacts.
- Added PyPI trusted publishing to the release workflow.
- Added a generated-template drift test that compares `md-blueprints init` output with the mirrored repository paths.
- Added `CONTRIBUTING.md` and `SECURITY.md`, including guidance that pull requests belong in this repository rather than the generated `blueprints-template` repository.
- Added a `make install-deploy` target to the tooling repository Makefile, matching the generated customer Makefile.
- Added mock deployment coverage for live Flight signatures: named `MD_RUN_FLIGHT`/`MD_DELETE_FLIGHT` arguments and the unscheduled preview Flight update retry path (ports the remaining coverage from PR #16).

### Changed

- Removed hardcoded `md-blueprints` version pins from the setup and versioning docs; local installs now go through the Makefile (`make setup`, `make install-deploy`), which owns the version pin in generated repositories.
- Changed template repository publishing to preserve `blueprints-template` history instead of force-pushing, and to tag and create a release on the template repository for each version so customer repositories can diff releases.
- Linked Flights, Dives, shares, and service accounts to their MotherDuck product docs pages from the repository and template READMEs.
- Aligned `actions/download-artifact` with the Dependabot-bumped `actions/upload-artifact` major version in the release workflow.
- Rewrote the repository `README.md` for a customer-facing audience: clarified what Blueprints is, documented the relationship between this repository, the `md-blueprints` package/action, and the generated `blueprints-template` repository, added the template-based quickstart, and removed hardcoded version pins. Added the missing Node.js prerequisite to the repository and template READMEs.
- Converted customer-facing deploy and cleanup workflows to run the pinned `motherduckdb/motherduck-blueprints` action instead of installing the local checkout.
- Kept tooling-repository deploy and doctor workflows on the local action checkout while generated customer workflows use the stamped public action tag.
- Updated the action to expose raw CLI stdout and install the deploy extra only for live commands.
- Replaced the deployer DuckDB CLI shell-out with the DuckDB Python package and its live MotherDuck runtime dependencies.
- Split the CLI implementation into schema, template, project, deploy, migration, and maintenance modules.
- Updated release publishing to maintain a floating major tag such as `v0`.
- Updated release publishing to generate the customer template and push it to `motherduckdb/blueprints-template`, failing tagged releases when the required template repository or token is missing.
- Improved validation errors for unsupported schema versions and unknown fields so they name the action/package upgrade path.
- Documented and implemented escaped literal template placeholders with `\${...}`.
- Updated docs and local setup guidance for PyPI installs, action `@v0`, the Python DuckDB runtime, and the schema compatibility matrix.
- Updated customer docs and template docs to use generated repository setup instead of cloning the tooling repository.
- Allowed the release external-setup preflight to accept a PyPI pending trusted publisher before the first package publish.
- Required the generated-template token preflight to prove push permission, catching unapproved fine-grained token requests before release.
- Made preview Flight updates idempotent when schedules are already disabled, aligned Flight run SQL with live MotherDuck function signatures, and surfaced live SQL failures as CLI errors instead of tracebacks.
- Added the MotherDuck runtime timezone dependency to generated starter Flight requirements.
- Updated generated starter Flights to read share URLs through `MD_LIST_DATABASE_SHARES()`.
- Updated preview cleanup to call Flight deletion with the live MotherDuck function signature.
- Included the DuckDB Python package in development installs so strict type checks cover live deploy configuration.
- Switched CI and deployment workflows to install and invoke the packaged `md-blueprints` command.
- Kept `tools/md_blueprints` as a compatibility wrapper around the package command.
- Documented that the template, CLI package, and action stay in one repository for this release, with modularization and repository split as follow-up criteria.

## v0.1.3 - 2026-06-29

### Added

- Added CI coverage that validates manifests, mock deploys, builds the included Dive, and creates then destroys a generated starter blueprint.
- Added `make example-smoke` to prove the generated starter blueprint can be created, rendered, built, and removed.
- Added a generated blueprint README template.
- Added a complete `blueprint.yml` field reference for agents, LLM crawlers, and blueprint authors.
- Added `tools/md_blueprints plan` for read-only live deployment planning.
- Added `tools/md_blueprints cleanup --dry-run` for preview cleanup planning.
- Added optional target deployment metadata for service account identity labels and token env var selection.

### Changed

- Refreshed agent and repository docs so validation checklists, generated-template guidance, context notes, and PR reminders stay aligned.
- Expanded the generated starter blueprint with daily metrics, a summary view, an underscore-safe Dive alias, and a richer dashboard.
- Ran read-only deployment plans before preview and production deploys in CI.
- Failed deploys before mutation when live planning finds duplicate Flights or Dives.
