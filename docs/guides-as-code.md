# Manage Guides as code

Use a Guide package when your team wants metric definitions, query conventions, and domain knowledge to follow the same review and deployment workflow as application code. A deployed Guide keeps its Markdown content, metadata, access, and references in MotherDuck aligned with `blueprint.yml`.

This workflow requires `md-blueprints >=0.4.0`. Organization-wide Guides require an admin deployment identity.

## Initialize and refresh from the repository

To draft a Guide from the packages already in your repository, run:

```bash
make init-guides
```

This creates `guides/repository-overview/` with a private, disabled Guide. It records production package descriptions, Flights and schedules, Dives and mounts, shares, input/output contracts, and the locations of other Guides and roles. Only packages discovered by `motherduck.yml` are included. Optional examples stay out until enabled.

After adding or changing packages, run:

```bash
make update-guides
make validate
```

`update-guides` also initializes the Guide if it does not exist. Repeating either command without changes leaves the files untouched. For a preview of the changes, use:

```bash
.venv/bin/md-blueprints guides update --dry-run
```

Both CLI commands accept `--root PATH`. They always describe the entire repository's production declarations. Existing repositories can call the CLI directly after upgrading if their Makefile does not yet have these targets.

The generated section of `guide.md` tracks added, changed, and removed package declarations. Write business definitions, join rules, tested SQL, and pitfalls under **Reviewed context**, outside the generated markers. Updates preserve those notes, the package README, and the manifest's IDs, access, and deployment settings. Edits inside the generated section cause a conflict instead of being overwritten. Move those edits outside the markers and restore the generated section from Git before retrying.

The command reports changes to declared source files, requirements, package READMEs, and manifests using hashes stored in `.guide-state.json`. Commit that file with the Guide. A code-only change updates the hashes and reports the affected file. Read that file and update the reviewed context as needed. The command does not infer business rules from Python or SQL, copy source code or Flight config, or query live MotherDuck state.

This is a broad orientation Guide with no resource references, so it adds no deployment dependencies. Use separate subject Guides with references for rules governing particular catalog objects, Flights, or Dives. Existing authored and imported Guides are preserved.

Review the diff and enable `resources.guides.overview.deploy: true` only when the production Guide is ready. Its preview and staging overrides remain disabled because the generated content describes production. Publish through the normal repository deployment workflow. Init and update only change local files.

## 1. Scaffold a Guide package

Create a package below the typed `guides/` root:

```bash
make new-guide revenue-metrics
```

The command creates:

```text
guides/revenue-metrics/
  blueprint.yml
  guide.md
  README.md
```

The generated manifest uses `deploy: false`, so `make validate` checks the Guide source without publishing it. This is useful while the Guide is still being reviewed.

## 2. Write the Guide

Keep one subject area in each Guide. Put the rules an agent must follow near the top, include working SQL patterns, and call out known pitfalls.

````markdown
# Revenue metrics

## Rules

- Use `analytics.main.subscriptions` for recurring revenue.
- Exclude rows where `is_test_account` is true.
- Calculate MRR from the normalized monthly amount, not invoice totals.

## Query pattern

```sql
SELECT month, sum(monthly_amount) AS mrr
FROM analytics.main.subscriptions
WHERE NOT is_test_account
GROUP BY month
ORDER BY month;
```
````

Do not include tokens, credentials, personal data, or source excerpts that should not be shared with everyone who can read the Guide.

## 3. Configure deployment and references

Set `deploy: true` when the repository should own the Guide lifecycle. The following package attaches the Guide to a table in an existing MotherDuck database and keeps previews private:

```yaml
schemaVersion: 1
name: revenue-metrics
title: Revenue metrics
description: Canonical recurring-revenue definitions.

resources:
  guides:
    guide:
      title: Revenue metrics
      topic: finance/revenue
      source: guide.md
      description: Definitions and query rules for recurring revenue.
      access: organization
      deploy: true
      changeComment: Synchronize the reviewed revenue definitions.
      references:
        - type: catalog
          url: md:analytics
          schema: main
          table: subscriptions
          description: Canonical recurring-revenue source.
      targets:
        preview:
          title: Revenue metrics:${target.branch} (Preview)
          access: user
```

Preview Guide titles or topics must include `${target.branch}` or `${target.branch_slug}`. Preview Guides cannot use a production `id`; Blueprints discovers each preview by its rendered topic and title and removes it when the branch closes.

Production deployment matches an existing Guide by `id` when configured, or by the exact topic and title otherwise. Set `id` only when adopting a specific existing production Guide or when topic and title are not unique. When the production resource has an `id`, set `targets.preview.id: null` so the preview gets its own identity.

## 4. Add resource references

References help agents discover the Guide while exploring the resources it documents. A Guide can reference:

- A catalog object from a package-local `share`, a repository `input`, or a literal share `url`.
- A Dive, Flight, or Guide by stable `uuid`.
- A Dive, Flight, or Guide resource in this repository by `resource`, with `blueprint` when it lives in another package.

When the referenced resources exist in the same repository, reference a Dive and a Guide in their packages:

```yaml
references:
  - type: dive
    blueprint: revenue-dashboard
    resource: dashboard
  - type: guide
    blueprint: data-governance
    resource: metric-ownership
```

Blueprints resolves all repository references during planning and fails before mutation if a target is missing or ambiguous. Guide references also participate in dependency ordering, and reference cycles fail validation.

See the [Guide manifest reference](blueprint-yml-reference.md#guides) for every field and reference selector.

## 5. Validate and review the plan

Validate both preview and production rendering without contacting MotherDuck:

```bash
make validate
```

With the target's MotherDuck token environment variable configured, install the live deployment dependencies and inspect the preview plan:

```bash
make install-deploy
.venv/bin/md-blueprints plan \
  --target preview \
  --branch feature/revenue-guide \
  --blueprints revenue-metrics
```

The plan reports `validated_only`, `create`, `update`, or an actionable error for each Guide. It also verifies that referenced live resources resolve before deployment starts.

## 6. Deploy through GitHub

Push the branch and open a pull request. The generated workflow:

1. Detects the changed Guide package.
2. Includes connected producers and consumers in the preview selection.
3. Deploys the branch-scoped preview after its references resolve.
4. Adds the Guide ID and deployment plan to the pull request comment.
5. Deletes the preview Guide when the pull request closes or the branch is deleted.

After review, merge the pull request. Without staging, the merge publishes stable Guide content through `motherduck-production`. With `targets.staging`, the merge publishes to staging; create a non-prerelease GitHub Release when the exact tagged content is ready to deploy through `motherduck-production`.

## Troubleshooting

- **The plan says `validated_only`.** Set `deploy: true` after the Guide is ready to publish.
- **Preview validation rejects the title.** Add `${target.branch}` or `${target.branch_slug}` to the preview title or topic.
- **The deployment requires the admin role.** Use an admin service account for `access: organization`, or use `access: user` to keep the Guide private to the deployment identity.
- **The plan finds duplicate Guides.** Set the existing production Guide's UUID as `id` and set `targets.preview.id: null`.
- **A reference does not resolve.** Check the `blueprint` and `resource` keys, or use the live resource's `uuid` for an externally managed Dive, Flight, or Guide.
