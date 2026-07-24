# blueprint.yml Reference

A `blueprint.yml` describes one independently deployable package. Runtime validation uses the schema packaged with `md-blueprints`; `schemas/v1/` is the editor-facing mirror.

## File Shape

```yaml
schemaVersion: 1
name: wikipedia-pageviews
title: Wikipedia Pageviews
description: A dashboard backed by a declared producer output.

inputs:
  pageviews:
    blueprint: wikipedia-pageviews-ingest
    output: pageviews

resources:
  dives:
    dashboard:
      title: Wikipedia Pageviews
      source: src/dive.tsx
      requiredResources:
        - input: pageviews
          alias: wikipedia_pageviews
```

Required top-level fields are `schemaVersion`, `name`, `title`, and `resources`. Optional fields are `description`, `variables`, `targets`, `inputs`, and `outputs`.

`name` must match `^[a-z0-9][a-z0-9-]*$`. In canonical typed roots, it must also equal the package's immediate parent directory.

## Typed Roots

| Root | Permitted resource groups |
| --- | --- |
| `flights/` | `flights` plus supporting `shares`; top-level inputs and outputs are allowed |
| `dives/` | `dives`; top-level inputs are allowed |
| `guides/` | `guides` or compatibility `context`; top-level inputs are allowed |
| `roles/` | `roles` |
| `projects/` | Any resource combination |
| `blueprints/` or custom roots | Compatibility behavior; any resource combination |

Typed packages may declare multiple resources of their permitted type. Recursive organization is allowed.

All `source` and `requirements` paths must stay inside the package, including after symlink resolution.

## Rendering

Strings can contain `${path.to.value}`. Escape a literal placeholder as `\${path.to.value}`.

Available template roots are:

- `repository`
- `target.name`, `target.branch`, and `target.branch_slug`
- `var`
- `resources.shares`
- `resources.roles`
- `inputs`

Variables render with this precedence: root variables, root target variables, blueprint variables, blueprint target variables. Resource target overrides are deep-merged over the base resource.

An input exposes:

| Field | Description |
| --- | --- |
| `blueprint` | Producer blueprint name |
| `output` | Producer output key |
| `share` | Producer's package-local share key |
| `name` | Target-rendered MotherDuck share name |
| `database` | Target-rendered database name |
| `access` | Target-rendered share access |
| `visibility` | Target-rendered share visibility |

For example, a Guide or Flight can use `${inputs.events.database}` in its rendered configuration. Share URLs are resolved from live MotherDuck state during plan/deploy and are not a static template field.

## Inputs and Outputs

A producer exports a share:

```yaml
outputs:
  events:
    share: events
```

`outputs.<key>.share` must reference a key under the same blueprint's `resources.shares`.

A consumer imports it:

```yaml
inputs:
  events:
    blueprint: events-ingest
    output: events
```

`inputs.<key>.blueprint` and `output` are required non-empty strings. References are repository-local. Use a literal required-resource `url` for cross-repository shares.

Blueprint names are globally unique. Missing producers, missing outputs, output/share mismatches, self-references, and cycles are validation errors.

## Shares

```yaml
resources:
  shares:
    events:
      name: events
      database: events
      access: ORGANIZATION
      visibility: DISCOVERABLE
      includePattern:
        - reporting.*
      grants:
        roles: [analysts]
        mode: authoritative
      cleanup: true
      dropDatabase: false
      targets:
        preview:
          name: events${var.preview_suffix}
          database: events${var.preview_suffix}
          access: RESTRICTED
          visibility: HIDDEN
          dropDatabase: true
```

Required fields are `name` and `database`. Defaults are `access: ORGANIZATION`, `visibility: DISCOVERABLE`, `cleanup: true`, and `dropDatabase: false`.

A hidden share must use restricted access. With the default preview policy, cleanup-sensitive share and database names must contain `target.branch_slug`.

`includePattern` manages the filtered-share include list. An omitted field leaves the current filter unmanaged; an empty array includes nothing. `grants.roles` and `grants.users` manage `READ` grants. `mode: additive` preserves undeclared grantees, while `mode: authoritative` revokes them.

## Flights

```yaml
resources:
  flights:
    loader:
      name: events-ingest
      source: src/flight.py
      requirements: src/requirements.txt
      scheduleCron: 17 6 * * *
      maxRuntimeSec: 1800
      runOnDeploy: true
      waitForRun: success
      secrets: []
      config:
        database: ${resources.shares.events.database}
      targets:
        preview:
          name: events-ingest:${target.branch} (Preview)
          scheduleCron: ""
```

Required fields are `name`, `source`, and `requirements`. Optional fields include `scheduleCron`, `accessTokenName`, `maxRuntimeSec`, `runOnDeploy`, `waitForRun`, `secrets`, `config`, and `targets`. `maxRuntimeSec: 0` means no timeout.

Flight source must exist and parse as Python. Cron values use five UTC fields. The default preview policy disables schedules. `waitForRun: success` applies when `runOnDeploy: true`.

## Dives

A Dive mount chooses exactly one data source:

```yaml
requiredResources:
  - share: local_share_key
    alias: local_data
  - input: repository_contract
    alias: contract_data
  - url: md:_share/external/id
    alias: external_data
```

Each item requires `alias` and exactly one of:

- `share`: a share in the same blueprint.
- `input`: a declared top-level input.
- `url`: a literal MotherDuck share URL, normally owned outside this repository.

A Dive requires `title`, `source`, and at least one required resource. `description`, `status`, and target overrides are optional. `status` accepts `draft`, `ready`, `endorsed`, or `archived`; preview Dives are always `draft`. Endorsing a Dive requires an organization admin. Preview titles must include the branch or branch slug.

The deployer strips the one-line `export const REQUIRED_DATABASES = ...` declaration from local-preview source and passes the rendered mounts to MotherDuck.

## Guides

```yaml
resources:
  guides:
    trusted-metrics:
      title: Trusted metrics
      topic: finance/revenue
      source: guide.md
      description: Canonical finance definitions.
      access: organization
      deploy: true
      references:
        - type: catalog
          share: events
          schema: reporting
          table: metrics
        - type: dive
          blueprint: revenue-dashboard
          resource: dashboard
```

A validation-only Guide requires `source`; a deployed Guide also requires `title`. `topic`, `description`, `access`, `references`, `changeComment`, `externalId`, `cleanup`, and target overrides are optional. `deploy` defaults to `false` for compatibility; `deploy: true` creates the Guide and publishes versioned content and references during selected deployments. `access` is `user` by default or `organization`, which requires an admin deployment identity.

Catalog references require exactly one of `url`, `share`, or `input`, and may narrow to a schema plus one table, view, or macro. Dive, Flight, and Guide references require either `uuid` or a repository `resource`; set `blueprint` for a resource in another package. These references participate in dependency ordering. Set a stable `id` when topic and title are not sufficient to identify an existing Guide. Preview Guides cannot use a production ID and their title or topic must be branch-scoped.

`resources.context` retains its validation-only compatibility behavior; `md-blueprints doctor` recommends `resources.guides`.

## Roles

```yaml
resources:
  roles:
    finance:
      name: finance
      includedRoles: [explorer]
      members:
        - finance-service-account
      mode: authoritative
      deploy: true
```

Roles deploy only to production and require an admin deployment identity. `includedRoles` are roles inherited by the custom role; `members` are MotherDuck usernames. `mode: additive` preserves assignments not listed in the manifest. `mode: authoritative` revokes undeclared direct role and user memberships. Blueprints never delete roles automatically.

## Target and Deployment Semantics

Every resource accepts a `targets.<target>` override. Preview and production rendering validate uniqueness for Flight names, Dive titles, deployed Guide identities, role names, and share names.

Inputs and repository-local Guide references form a DAG:

- Preview selection expands recursively upstream and downstream.
- Production selection expands recursively downstream only.
- Producers deploy before consumers.
- A consumer-only production plan requires the producer's output to exist in MotherDuck and fails before mutation otherwise.
- Cleanup runs in reverse dependency order.

## Compatibility

These fields are additive to `schemaVersion: 1` and require `md-blueprints >=0.4.0`. Existing manifests without inputs, outputs, Guides, or roles continue to validate, including manifests discovered below `blueprints/`.
