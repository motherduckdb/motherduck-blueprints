# Wikipedia Pageviews

The starter dashboard. It reads the share that `wikipedia-pageviews-ingest` publishes and shows totals per article, daily views over time, and the last seven days.

Use it as the pattern for a dashboard on data that another package owns.

## How it gets its data

`blueprint.yml` declares the producer's output as an input and mounts it under an alias:

```yaml
inputs:
  pageviews:
    blueprint: wikipedia-pageviews-ingest
    output: pageviews

resources:
  dives:
    pageviews:
      requiredResources:
        - input: pageviews
          alias: wikipedia_pageviews
```

`src/dive.tsx` then queries `wikipedia_pageviews.main.<table>`. The alias stays the same in previews and production; Blueprints points it at the right share.

## Patterns to reuse

- **Query the alias, never a database name.** The same source works in a preview, in staging, and in production.
- **Aggregate in SQL.** Each `useSQLQuery` returns the rows the chart needs, already grouped.
- **Handle loading, errors, and empty results.** The first preview may render before the first load finishes.
- **Import only what production provides.** `@motherduck/react-sql-query`, React, d3, lucide-react, and recharts. `make preview-smoke` fails on anything else.

## Work on it

Edit `src/dive.tsx` for the dashboard and `blueprint.yml` for mounts and metadata. From the repository root:

```bash
make validate
make preview-smoke NAME=wikipedia-pageviews
```

For a live local preview, set `VITE_MOTHERDUCK_TOKEN` in `.dive-preview/.env` and run `make preview NAME=wikipedia-pageviews`.

A preview deploys the producer too, so the preview Dive has data. In production, a dashboard-only change uses the existing share and does not rerun the Flight; change or select the Flight package for the first deployment.

For an existing dashboard, follow [adoption](../../docs/adopt-existing-resources.md). Preserve mount aliases and the exact title, and verify the planned UUID before updating it.
