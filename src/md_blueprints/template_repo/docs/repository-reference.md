# Repository Reference

Use this page for the repository layout, dependency behavior, targets, and local commands.

## Repository Layout

```text
motherduck.yml
flights/
  <producer-name>/
    blueprint.yml
    src/flight.py
dives/
  <dive-name>/
    blueprint.yml
    src/dive.tsx
guides/
  <guide-name>/
    blueprint.yml
    guide.md
roles/
  <role-name>/
    blueprint.yml
projects/
  <project-name>/
    blueprint.yml
shared/
schemas/v1/
```

`motherduck.yml` is the repository catalog and policy file. The v0.4 template discovers manifests recursively:

```yaml
include:
  - flights/**/blueprint.yml
  - dives/**/blueprint.yml
  - guides/**/blueprint.yml
  - roles/**/blueprint.yml
  - projects/**/blueprint.yml
  - blueprints/**/blueprint.yml
```

The final entry preserves compatibility with existing repositories. No migration is required. Include patterns must stay inside the repository, overlapping matches are deduplicated, and blueprint names are globally unique.

## Package Boundaries

Every leaf package is independently deployable. Use:

- `flights/` for one or more Flights plus the shares and outputs they produce.
- `dives/` for one or more Dives and their declared inputs.
- `guides/` for one or more version-controlled Guides.
- `roles/` for production custom roles and direct memberships.
- `projects/` for any resource combination that genuinely ships, previews, and rolls back together.
- `shared/` for human-oriented shared documentation or configuration only. It has no deployment semantics.

Nested team or domain directories are allowed. In canonical roots, the directory immediately containing `blueprint.yml` must match the blueprint's lowercase slug. Typed roots reject mismatched resource groups. Custom include roots and legacy `blueprints/` packages remain unconstrained.

Resource source files must remain inside their package, including after symlink resolution.

## Inputs, Outputs, and Deployment Graph

A producer gives a package-local share a stable contract name:

```yaml
outputs:
  pageviews:
    share: pageviews
```

A same-repository consumer references that contract:

```yaml
inputs:
  pageviews:
    blueprint: wikipedia-pageviews-ingest
    output: pageviews

resources:
  dives:
    dashboard:
      requiredResources:
        - input: pageviews
          alias: wikipedia_pageviews
```

Inputs can also be used in templates through `${inputs.<name>.*}`. Rendered metadata includes the producer and output identity plus the target-specific share name, database, access, and visibility. Use a literal `url` required resource for a share owned by another repository.

The CLI validates missing producers, missing outputs, outputs pointing to missing shares, self-references, and dependency cycles before deployment.

Selection follows the graph:

- Preview expands recursively upstream and downstream, producing a branch-scoped connected preview.
- Production expands downstream only. Changing a producer redeploys its consumers; changing only a consumer uses the existing production output and does not rerun its producer.
- Deployment order is deterministic and producer-first.
- Preview cleanup reverses dependency order and removes deployed Guides before Dives, Flights, shares, and databases.

Direct Git change detection remains package-based. Graph expansion happens when plan, deploy, or cleanup interprets the selected names.

## Targets and Safety

The default targets are:

- `preview`: branch-scoped names, disabled Flight schedules, and cleanup enabled.
- `prod`: stable names deployed through the `motherduck-production` GitHub Environment.

Cleanup-sensitive preview shares and databases must contain `${target.branch_slug}`. Preview Flight names and Dive titles must contain the branch or branch slug. Cleanup refuses identifiers that are not branch-scoped or that match production.

A target can select a token environment variable and document its deployment identity:

```yaml
targets:
  prod:
    mode: production
    deployment:
      tokenEnvVar: MOTHERDUCK_TOKEN
      identity: GitHub Actions production service account
```

Tokens are passed to the DuckDB connection and are never printed.

## Local Commands

```bash
make setup
make validate
make new-flight events-ingest
make new-dive events-dashboard INPUT=events-ingest.data
make new-guide analytics-guide
make new-role analytics-team
make new-project revenue-overview
make preview wikipedia-pageviews
make preview-smoke wikipedia-pageviews
make render-preview wikipedia-pageviews

md-blueprints plan --target preview --branch feature/local --blueprints wikipedia-pageviews
md-blueprints cleanup --dry-run --target preview --branch feature/local
md-blueprints doctor
```

`make new-blueprint NAME` remains a compatibility alias for `make new-project NAME`. For a Dive backed by another repository, use `make new-dive NAME URL=md:_share/...`. If a package declares several Dives, pass `DIVE=<resource-key>` to preview commands.

`make validate` renders preview and production, validates contracts and uniqueness, checks Flight Python syntax and source boundaries, and validates Dive mounts and Guide references. `md-blueprints plan` queries live state without mutations. A non-selected production producer must already expose its declared share or planning fails before deployment.

## Guides

Declare Guide assets with `resources.guides`. They remain source-validation-only by default; `deploy: true` enables create, version, metadata, access, reference, and preview-cleanup lifecycle management. Organization-wide Guides require an admin deployment identity. `resources.context` remains accepted for validation-only compatibility; `md-blueprints doctor` recommends the new name.

## RBAC

Declare custom roles under `resources.roles` or scaffold a role package with `make new-role`. Roles deploy only in production, before resources that may grant access to them. Share `grants` can target roles and users in additive or authoritative mode. Role and organization-Guide changes run an admin capability preflight before the first mutation.

## CI/CD

Pull requests compute directly changed packages, expand the preview dependency graph, plan live changes, deploy branch-scoped resources, and comment with plans and preview links. Pushes to `main` expand production changes downstream and deploy through the protected production environment. Closing a PR or deleting a branch triggers dependency-safe preview cleanup.
