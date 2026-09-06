# Repository Reference

Use this page for the repository layout, dependency behavior, targets, and local commands.

## What a customer needs

A fresh repository contains the Wikipedia Flight and Dive, optional examples, documentation, and the workflow/preview support files. You edit `motherduck.yml`, each package's `blueprint.yml`, and its source. Other resource roots are created on demand. There is no need to create empty folders.

The tooling repository also contains Python source, tests, release tooling, and internal scaffolds. Those are not copied into customer repositories. Local source filenames are flexible: `main.py` or `index.tsx` pulled by the MotherDuck CLI can be referenced directly without adding a `src/` layer.

For existing account resources, begin with [adoption](adopt-existing-resources.md). CLI exports alone are not deployable Blueprints packages.

## Supported Layouts

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

The required targets are:

- `preview`: branch-scoped names, disabled Flight schedules, and cleanup enabled.
- `prod`: stable names deployed through the `motherduck-production` GitHub Environment.

`staging` is the one optional conventional target. Its presence changes CI/CD from direct production deployment to release promotion: previews and `main` use the staging service account, while published releases use production.

Cleanup-sensitive preview shares and databases must contain `${target.branch_slug}`. Preview Flight names and Dive titles must contain the branch or branch slug. Cleanup refuses identifiers that are not branch-scoped or that match production.

A target declares the GitHub Environment that holds its service-account token and documents that identity:

```yaml
targets:
  prod:
    mode: production
    deployment:
      tokenEnvVar: MOTHERDUCK_TOKEN
      identity: GitHub Actions production service account
```

Tokens are passed to the DuckDB connection and are never printed.

The default `preview + prod` topology points both targets at `motherduck-production` and deploys `main` directly to production. To isolate production, add `staging`, point both `preview` and `staging` at `motherduck-staging`, and keep `prod` on `motherduck-production`. Each GitHub Environment contains its own secret named `MOTHERDUCK_TOKEN`.

Staging and production may render the same database names because the databases belong to different service accounts. Their share names must differ; Blueprints validates this across every rendered share when staging is configured. A `_staging` suffix is the default scaffold convention. Use a customer-specific logical prefix to reduce the chance of a collision outside the repository.

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

Omit `--blueprints` to select all packages; an explicitly empty selection is an error. `doctor` validates all declared targets, including rendered resources, and exits unsuccessfully if the manifest is missing or validation fails. Preview commands preserve the existing Dive entrypoint if source selection fails.

`make new-blueprint NAME` remains a compatibility alias for `make new-project NAME`. For a Dive backed by another repository, use `make new-dive NAME URL=md:_share/...`. If a package declares several Dives, pass `DIVE=<resource-key>` to preview commands.

`make validate` renders every declared target, validates contracts and uniqueness, checks Flight Python syntax and source boundaries, and validates Dive mounts and Guide references. `md-blueprints plan` queries live state without mutations. A non-selected stable producer must already expose its declared share or planning fails before deployment.

## Dives

Preview Dives always use `draft`. Production manifests can declare `draft`, `ready`, `endorsed`, or `archived`; omitting `status` preserves the live value during content updates. Deployment plans show current and desired status, and endorsement requires an organization-admin identity.

## Guides

Declare Guide assets with `resources.guides`. They remain source-validation-only by default; `deploy: true` enables create, version, metadata, access, reference, and preview-cleanup lifecycle management. Organization-wide Guides require an admin deployment identity. `resources.context` remains accepted for validation-only compatibility; `md-blueprints doctor` recommends the new name.

See [Manage Guides as code](guides-as-code.md) for the end-to-end workflow, including branch-scoped previews and repository resource references.

## RBAC

Declare custom roles under `resources.roles` or scaffold a role package with `make new-role`. Roles deploy to stable staging and production targets, but never to preview, before resources that may grant access to them. Share `grants` can target roles and users in additive or authoritative mode. Role and organization-Guide changes run an admin capability preflight before the first mutation.

## CI/CD

Pull requests compute directly changed packages, expand the preview dependency graph, plan live changes, deploy branch-scoped resources, and comment with plans and preview links. Without staging, pushes to `main` expand changes downstream and deploy production. With staging, pushes to `main` deploy staging and a published non-prerelease GitHub Release verifies and deploys the exact tagged commit to production. Closing a PR or deleting a branch triggers dependency-safe preview cleanup through the preview target's GitHub Environment.

## Included examples

- [Wikipedia Pageviews](examples/wikipedia-pageviews.md) uses independent Flight and Dive packages connected through a named output and input.
- [NCS Field Recovery Explorer](examples/ncs-field-recovery.md) keeps its Flight, share, and Dive in one project because they deploy and roll back together.
