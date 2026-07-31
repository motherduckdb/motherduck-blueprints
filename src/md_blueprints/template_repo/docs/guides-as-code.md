# Manage Guides as code

Use a Guide package when your team wants metric definitions, query conventions, and domain knowledge to follow the same review and deployment workflow as application code. A deployed Guide keeps its Markdown content, metadata, access, and references in MotherDuck aligned with `blueprint.yml`.

This workflow requires `md-blueprints >=0.4.0`. Organization-wide Guides require an admin deployment identity.

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

The generated manifest uses `deploy: false`, so `make validate` checks the Guide source without publishing it. It already includes a branch-scoped preview title, making `deploy: true` the only required change when the content is ready to publish.

### Standalone or colocated

Use `guides/<name>/` when the Guide has its own owner or deployment lifecycle. [`guides/blueprint-authoring/`](../guides/blueprint-authoring/) is the included standalone example.

Use `projects/<name>/guide.md` when the Guide must change and roll back with that project's Flight, share, or Dive. `make new-project revenue-overview` creates a validation-only `project-guide` resource with references to the generated Flight and Dive. [`projects/ncs-field-recovery/`](../projects/ncs-field-recovery/) demonstrates the same colocated shape in a complete project.

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

Set `deploy: true` when the repository should own the Guide lifecycle. New scaffolds already contain the required branch-scoped preview title; the following expanded package also attaches the Guide to a table in an existing MotherDuck database and keeps previews private:

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

After review, merge the pull request. The production workflow publishes stable Guide content, references, metadata, and access through the protected `motherduck-production` environment.

## Troubleshooting

- **The plan says `validated_only`.** Set `deploy: true` after the Guide is ready to publish.
- **Preview validation rejects the title.** Older or handwritten manifests must add `${target.branch}` or `${target.branch_slug}` to the preview title or topic; current scaffolds include this already.
- **The deployment requires the admin role.** Use an admin service account for `access: organization`, or use `access: user` to keep the Guide private to the deployment identity.
- **The plan finds duplicate Guides.** Set the existing production Guide's UUID as `id` and set `targets.preview.id: null`.
- **A reference does not resolve.** Check the `blueprint` and `resource` keys, or use the live resource's `uuid` for an externally managed Dive, Flight, or Guide.
