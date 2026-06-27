# blueprint.yml Reference

Use this page as a machine-readable reference for `blueprints/<blueprint-name>/blueprint.yml`.

`blueprint.yml` describes one deployable MotherDuck blueprint package. It declares metadata, optional variables, target-specific overrides, and resources such as shares, Flights, Dives, and context files.

## File Shape

```yaml
schemaVersion: 1
name: wikipedia-pageviews
title: Wikipedia Pageviews
description: Loads public Wikimedia pageview data with a Flight and visualizes it in a Dive.

variables:
  database:
    description: MotherDuck database that stores data.
    default: wikipedia_pageviews

targets:
  preview:
    variables:
      database: wikipedia_pageviews_preview_${target.branch_slug}

resources:
  shares: {}
  flights: {}
  dives: {}
  context: {}
```

The `resources` object is required. Each resource group inside it is optional, so a blueprint can contain any combination of shares, Flights, Dives, and context resources.

## Rendering Model

`blueprint.yml` is first validated as YAML and then rendered for a target such as `preview` or `prod`.

| Rule | Behavior |
| --- | --- |
| Template syntax | Strings can contain `${path.to.value}` references. |
| Available template roots | `repository`, `target`, `var`, and `resources.shares`. |
| Target values | `target.name`, `target.branch`, and `target.branch_slug`. |
| Branch slug | Lowercase branch name with non-alphanumeric runs replaced by `_`, trimmed to 48 characters. Empty slugs render as `preview`. |
| Variable precedence | Root `motherduck.yml` variables, root target variables, blueprint variables, then blueprint target variables. Later values override earlier values. |
| Variable rendering | Variables render recursively for up to 5 passes, then all variable values are stringified. |
| Resource target overrides | `resources.<type>.<key>.targets.<target>` is deep-merged over the base resource before template rendering. |
| Share references | Shares render before Flights and Dives, so Flights and Dives can reference `${resources.shares.<key>.<field>}`. |

Example share reference:

```yaml
resources:
  shares:
    data:
      name: ${var.database}
      database: ${var.database}
  flights:
    loader:
      name: load-${resources.shares.data.name}
      source: src/flight.py
      requirements: src/requirements.txt
      config:
        database: ${resources.shares.data.database}
```

## Top-Level Fields

| Path | Required | Type or allowed values | Default | Description |
| --- | --- | --- | --- | --- |
| `schemaVersion` | Yes | `1` | None | Manifest schema version. The only accepted value is `1`. |
| `name` | Yes | String matching `^[a-z0-9][a-z0-9-]*$` | None | Blueprint package name. Use the same lowercase slug as `blueprints/<name>/`. |
| `title` | Yes | Non-empty string | None | Human-readable blueprint title. Rendered as a template string. |
| `description` | No | String | `""` after render | Human-readable blueprint description. Rendered as a template string. |
| `variables` | No | Object of variable definitions | `{}` | Blueprint-local variables. |
| `targets` | No | Object keyed by target name | `{}` | Blueprint-level target overrides. Currently, `targets.<target>.variables` is the interpreted field. |
| `resources` | Yes | Object | None | Resource declarations. Allowed keys are `shares`, `flights`, `dives`, and `context`. |

Unknown top-level keys are invalid.

## Variables

Variables can be short scalar values or objects with metadata.

| Shape | YAML example | Notes |
| --- | --- | --- |
| String | `database: analytics` | Accepted. Rendered value is stringified. |
| Number | `days_back: 30` | Accepted. Rendered value is stringified. |
| Boolean | `enabled: true` | Accepted. Rendered value is stringified. |
| Object | `database: { description: Data database, default: analytics }` | Requires `default`. `description` is optional. |

Object variable fields:

| Path | Required | Type or allowed values | Default | Description |
| --- | --- | --- | --- | --- |
| `variables.<key>.description` | No | String | None | Reader-facing description. |
| `variables.<key>.default` | Yes | Any YAML value | None | Variable value used during rendering. |

Unknown fields inside object variables are invalid.

## Blueprint Target Overrides

Blueprint-level target overrides are keyed by target name:

```yaml
targets:
  preview:
    variables:
      database: ${var.database}${var.preview_suffix}
```

The deploy tool currently reads `targets.<target>.variables` from this object. Use resource-level `targets` for resource field overrides such as preview Flight names or preview share names.

## Resource Groups

| Path | Required | Type | Description |
| --- | --- | --- | --- |
| `resources.shares` | No | Object keyed by share resource key | Declares named data products that Flights can produce and Dives can consume. |
| `resources.flights` | No | Object keyed by Flight resource key | Declares Python MotherDuck Flights. |
| `resources.dives` | No | Object keyed by Dive resource key | Declares MotherDuck Dives. |
| `resources.context` | No | Object keyed by context resource key | Declares future context-layer assets. These validate only and must not deploy yet. |

Resource keys are local identifiers. Dives refer to share resource keys with `requiredResources[].share`.

## Shares

Example:

```yaml
resources:
  shares:
    pageviews:
      name: ${var.share}
      database: ${var.database}
      access: ORGANIZATION
      visibility: DISCOVERABLE
      cleanup: true
      dropDatabase: false
      targets:
        preview:
          name: ${var.share}${var.preview_suffix}
          database: ${var.database}${var.preview_suffix}
          access: RESTRICTED
          visibility: HIDDEN
          dropDatabase: true
```

| Path | Required | Type or allowed values | Default | Description |
| --- | --- | --- | --- | --- |
| `resources.shares.<key>.name` | Yes | Non-empty string | None | MotherDuck share name after rendering. |
| `resources.shares.<key>.database` | Yes | Non-empty string | None | Database that backs the share. |
| `resources.shares.<key>.access` | No | String | `ORGANIZATION` | Share access mode passed to project code. Current examples use `ORGANIZATION`, `UNRESTRICTED`, or `RESTRICTED`. |
| `resources.shares.<key>.visibility` | No | String | `DISCOVERABLE` | Share visibility passed to project code. Current examples use `DISCOVERABLE` or `HIDDEN`. |
| `resources.shares.<key>.cleanup` | No | Boolean | `true` during preview cleanup | Whether preview cleanup should drop this share. |
| `resources.shares.<key>.dropDatabase` | No | Boolean | `false` | Whether preview cleanup should also drop the backing database. |
| `resources.shares.<key>.targets` | No | Object keyed by target name | `{}` | Target-specific share overrides. |

Rendered share validation:

- `name` and `database` must be non-empty after rendering.
- If `visibility` renders as `HIDDEN`, `access` must render as `RESTRICTED`.
- In the default preview target, share names must include `${target.branch_slug}`.
- In the default preview target, databases must include `${target.branch_slug}` when `dropDatabase: true`.
- Preview cleanup refuses to drop shares or databases whose rendered names do not include the branch slug.

## Flights

Example:

```yaml
resources:
  flights:
    pageviews_loader:
      name: wikipedia-pageviews
      source: src/flight.py
      requirements: src/requirements.txt
      scheduleCron: 17 6 * * *
      accessTokenName: ""
      runOnDeploy: true
      waitForRun: success
      secrets: []
      config:
        database: ${resources.shares.pageviews.database}
      targets:
        preview:
          name: wikipedia-pageviews:${target.branch} (Preview)
          scheduleCron: ""
```

| Path | Required | Type or allowed values | Default | Description |
| --- | --- | --- | --- | --- |
| `resources.flights.<key>.name` | Yes | Non-empty string | None | MotherDuck Flight name after rendering. Must be unique per rendered target. |
| `resources.flights.<key>.source` | Yes | Non-empty string | None | Path to the Python Flight source, relative to the blueprint directory. |
| `resources.flights.<key>.requirements` | Yes | Non-empty string | None | Path to the Flight `requirements.txt`, relative to the blueprint directory. |
| `resources.flights.<key>.scheduleCron` | No | String | `""` | Five-field UTC cron expression, or empty string for no schedule. |
| `resources.flights.<key>.accessTokenName` | No | String | `""` | Named MotherDuck access token to pass to Flight deployment. Empty strings are omitted. |
| `resources.flights.<key>.runOnDeploy` | No | Boolean | `false` | Whether deployment starts a Flight run immediately. |
| `resources.flights.<key>.waitForRun` | No | `success` or `false` | `false` | When set to `success`, deployment waits for the immediate run to succeed. |
| `resources.flights.<key>.secrets` | No | Array of strings | `[]` | MotherDuck Flight secret names. |
| `resources.flights.<key>.config` | No | Object with any values | `{}` | Flight runtime config. Values are rendered and stringified before deployment. |
| `resources.flights.<key>.targets` | No | Object keyed by target name | `{}` | Target-specific Flight overrides. |

Rendered Flight validation:

- `name`, `source`, and `requirements` must be non-empty after rendering.
- `source` and `requirements` files must exist.
- `source` must parse as valid Python.
- Non-empty `scheduleCron` values must contain exactly 5 fields.
- In the default preview target, schedules are disabled by policy and render as `""` even if the base Flight sets `scheduleCron`.
- `waitForRun: success` only waits when `runOnDeploy: true` starts a run.

## Dives

Example using a local share resource:

```yaml
resources:
  dives:
    pageviews:
      title: Wikipedia Pageviews
      source: src/dive.tsx
      description: Recent daily pageviews.
      requiredResources:
        - share: pageviews
          alias: wikipedia_pageviews
      targets:
        preview:
          title: Wikipedia Pageviews:${target.branch} (Preview)
```

Example using a direct share URL:

```yaml
resources:
  dives:
    external:
      title: External Share Dive
      source: src/dive.tsx
      requiredResources:
        - url: md:_share/example/00000000-0000-0000-0000-000000000000
          alias: external_data
```

| Path | Required | Type or allowed values | Default | Description |
| --- | --- | --- | --- | --- |
| `resources.dives.<key>.title` | Yes | Non-empty string | None | MotherDuck Dive title after rendering. Must be unique per rendered target. |
| `resources.dives.<key>.source` | Yes | Non-empty string | None | Path to the Dive source, relative to the blueprint directory. |
| `resources.dives.<key>.description` | No | String | `""` | Dive description passed to MotherDuck. |
| `resources.dives.<key>.requiredResources` | Yes | Non-empty array | None | Share resources or direct share URLs that the Dive mounts. |
| `resources.dives.<key>.targets` | No | Object keyed by target name | `{}` | Target-specific Dive overrides. |

Rendered Dive validation:

- `title` and `source` must be non-empty after rendering.
- `source` file must exist.
- `requiredResources` must contain at least one item.
- Each required resource must set `alias`.
- Each required resource must set either `share` or `url`.
- If `share` is set, it must reference a key under `resources.shares` in the same blueprint.

Required resource fields:

| Path | Required | Type or allowed values | Description |
| --- | --- | --- | --- |
| `share` | Required when `url` is absent | Non-empty string | Local share resource key. The deployer resolves this to the rendered share URL. |
| `url` | Required when `share` is absent | Non-empty string | Direct MotherDuck share URL. |
| `alias` | Yes | Non-empty string | Database alias exposed to the Dive. |

## Context Resources

Example:

```yaml
resources:
  context:
    policy:
      source: context/policy.md
      deploy: false
```

| Path | Required | Type or allowed values | Default | Description |
| --- | --- | --- | --- | --- |
| `resources.context.<key>.source` | Yes | Non-empty string | None | Path to a context file, relative to the blueprint directory. |
| `resources.context.<key>.deploy` | No | Boolean | `false` | Must be `false` or omitted until MotherDuck exposes a context deployment API. |
| `resources.context.<key>.targets` | No | Object keyed by target name | `{}` | Target-specific context overrides. |

Rendered context validation:

- `source` file must exist.
- `deploy: true` is invalid for every target until context deployment is supported.

## Target Override Pattern

Every resource type supports a `targets` object. The override key must match a target in `motherduck.yml` to affect that rendered target.

```yaml
resources:
  shares:
    data:
      name: analytics
      database: analytics
      targets:
        preview:
          name: analytics${var.preview_suffix}
          database: analytics${var.preview_suffix}
```

Target overrides are deep-merged. Nested objects such as `config` can override one key without repeating the full object:

```yaml
resources:
  flights:
    loader:
      name: analytics-loader
      source: src/flight.py
      requirements: src/requirements.txt
      config:
        mode: full
        database: analytics
      targets:
        preview:
          config:
            mode: sample
```

Rendered preview `config`:

```json
{
  "mode": "sample",
  "database": "analytics"
}
```

## Validation Summary

Run these checks before opening a pull request:

```bash
make validate
make mock-test
make preview-smoke <blueprint-name>
```

`make validate` checks schemas, renders preview and production targets, enforces uniqueness, verifies file paths, parses Flight Python sources, and checks rendered resource rules. `make mock-test` exercises scaffold creation, preview deploy, production deploy, cleanup, and failed Flight run handling without contacting MotherDuck. Run `make preview-smoke <blueprint-name>` for every blueprint that includes a Dive.
