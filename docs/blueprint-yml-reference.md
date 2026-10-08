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

Variables render with this precedence: root variables, root target variables, blueprint variables, blueprint target variables. Resource target overrides are deep-merged over the base resource. The merged, rendered resource is validated again for every target, so a wrong type or unknown field inside `targets.<target>` fails validation with the file, resource, and target named.

`target.branch_slug` is the branch name lowercased, with every run of characters other than `a-z` and `0-9` replaced by `_`. Slugs of 48 characters or more are cut to at most 39 characters plus `_` and an 8-character hash of the full branch name, so two long branches never share preview resources.

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
        staging:
          name: events_staging
        preview:
          name: events${var.preview_suffix}
          database: events${var.preview_suffix}
          access: RESTRICTED
          visibility: HIDDEN
          dropDatabase: true
```

Required fields are `name` and `database`. `access` is `ORGANIZATION`, `RESTRICTED`, or `UNRESTRICTED`, and `visibility` is `DISCOVERABLE` or `HIDDEN` (case-insensitive). Defaults are `access: ORGANIZATION`, `visibility: DISCOVERABLE`, `cleanup: true`, and `dropDatabase: false`.

A hidden share must use restricted access. With the default preview policy, cleanup-sensitive share and database names must contain `target.branch_slug` as a whole `_`-separated part, such as `events_preview_feature_x`. When `targets.staging` exists, every rendered staging share name must differ from every production share name. Staging and production database names may match because they belong to separate service accounts.

`includePattern` manages the filtered-share include list. An omitted field leaves the current filter unmanaged, `null` resets the share to unfiltered, and an empty array includes nothing. `grants.roles` and `grants.users` manage `READ` grants. `mode: additive` (the default) preserves undeclared grantees, while `mode: authoritative` revokes them, including grants made outside Blueprints, for example by Terraform. `plan` lists the revocations. `grants.users` are MotherDuck usernames in the share owner's organization; see the username check under [roles](#roles).

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

Required fields are `name`, `source`, and `requirements`. Optional fields include `id`, `owner`, `deploy`, `manageSchedule`, `scheduleCron`, `accessTokenName`, `maxRuntimeSec`, `instanceType`, `runOnDeploy`, `waitForRun`, `secrets`, `config`, and `targets`. `maxRuntimeSec: 0` means no timeout. With `waitForRun: success`, deployment waits at least `maxRuntimeSec` plus two minutes for the run to finish.

`instanceType` sets the Flight's instance size: `F4` (0.5 vCPU, 4 GB), `F16` (2 vCPU, 16 GB), or `F32` (4 vCPU, 32 GB). Your plan decides which sizes are allowed:

| Plan | Allowed | Default |
| --- | --- | --- |
| Business, Free Trial | `F4`, `F16`, `F32` | `F16` |
| Lite | `F4`, `F16` | `F16` |
| Free | `F4` | `F4` |

Without `instanceType`, a new Flight gets the plan default and an existing Flight keeps its current size. Removing the field does not reset the size; set it to the size you want. MotherDuck rejects a size your plan does not allow when the Flight is created or updated. Sending a size needs DuckDB 1.5.6 or newer. The Blueprints action already uses it. Locally, `plan` and `deploy` stop before any write when the SQL backend is older; install `md-blueprints[deploy]` and set `MD_BLUEPRINTS_SQL_BACKEND=duckdb`, because the pinned MotherDuck CLI ships DuckDB 1.5.5.

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

A Dive requires `title`, `source`, and a `requiredResources` array, which may be empty for a Dive without data mounts. `id`, `owner`, `deploy`, `description`, `status`, and target overrides are optional. `status` accepts `draft`, `ready`, `endorsed`, or `archived`; preview Dives are always `draft`. Endorsing a Dive requires an organization admin. Preview titles must include the branch or branch slug.

The deployer strips the `export const REQUIRED_DATABASES = ...` declaration (single-line or multi-line) from local-preview source and passes the rendered mounts to MotherDuck.

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

Catalog references require exactly one of `url`, `share`, or `input`, and may narrow to a schema plus one table, view, or macro. Dive, Flight, and Guide references require either `uuid` or a repository `resource`; set `blueprint` for a resource in another package. These references participate in dependency ordering and are resolved during planning before any mutation. A referenced validation-only Guide must declare its stable `id`; set `deploy: true` instead when this repository owns its lifecycle. Set a stable `id` on a deployed Guide when topic and title are not sufficient to identify an existing Guide. Preview Guides cannot use a production ID and their title or topic must be branch-scoped.

`resources.context` is deprecated. It remains validation-only for compatibility. Rename it to `resources.guides`.

For a complete scaffold-to-deployment workflow, see [Manage Guides as code](guides-as-code.md).

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

Roles deploy to stable staging and production targets and require an admin deployment identity. They never deploy to preview. `includedRoles` are roles inherited by the custom role; `members` are MotherDuck usernames. `plan` and `deploy` look up every declared username with the MotherDuck [`GET /v1/users`](https://motherduck.com/docs/sql-reference/rest-api/users-list/) endpoint, without regard to case, and stop before any write when one is not a user in the organization. A deprovisioned user prints a warning. When the user list cannot be read, for example because the deployment identity lacks the `member_management.view_all_members` privilege, Blueprints prints a warning and skips the check, so an unknown username fails at its `GRANT` instead. `mode: additive` preserves assignments not listed in the manifest. `mode: authoritative` revokes undeclared direct role and user memberships, including ones granted by other tools such as Terraform, and `plan` lists them. Blueprints never delete roles automatically.

## Adopting existing resources (0.4.3+)

Flights, Dives, and Guides accept `id` and an optional `owner` guard. Put these under the stable target override that owns the resource. A bound ID is looked up directly; missing/inaccessible IDs fail the plan and never fall back to name-based creation. Flight updates additionally require the creator's identity. Renaming a bound resource retains its UUID. Without an ID, existing name/title discovery remains supported.

`deploy: false` validates source but skips resource deployment and preview cleanup. Flights and Dives retain their existing default of deployment enabled; Guides default to disabled. The importer sets all three explicitly to false, so activation is a separate reviewed edit.

Flight `manageSchedule` defaults to true for compatibility. Set it to false on an adopted Flight to leave the live schedule untouched during updates, including its paused state. The configured cron is retained for review; creates still use the normal schedule policy.

Do not reuse a stable ID in preview. No two active resources may update the same UUID. `owner` checks the recorded owner against the live object; it is not an ownership-transfer instruction or a guarantee of permission. See [import existing resources](adopt-existing-resources.md).

## Target and Deployment Semantics

Every resource accepts a `targets.<target>` override. All declared targets validate uniqueness for Flight names, Dive titles, deployed Guide identities, role names, and share names. Staging additionally validates that its share names do not collide with production.

Inputs and repository-local Guide references form a DAG:

- Preview selection expands recursively downstream, then adds the producers those packages read. Unchanged consumers of those producers are not previewed.
- Stable staging and production selection expand recursively downstream only.
- Producers deploy before consumers.
- A consumer-only production plan requires the producer's output to exist in MotherDuck and fails before mutation otherwise.
- Cleanup runs in reverse dependency order.

## Compatibility

These fields are additive to `schemaVersion: 1` and require `md-blueprints >=0.4.0`. Existing manifests without inputs, outputs, Guides, or roles continue to validate, including manifests discovered below `blueprints/`.
