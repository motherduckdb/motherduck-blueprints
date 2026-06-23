# Wikipedia Pageviews Example

This example pairs:

- `flights/wikipedia-pageviews/` - loads public Wikimedia pageview data into MotherDuck and publishes a share.
- `dives/wikipedia-pageviews/` - reads from that share through the `wikipedia_pageviews` alias.
- `bundles/wikipedia-pageviews/` - deploys the Flight, waits for the share, then deploys the Dive.

## What the Flight Creates

The Flight creates these MotherDuck objects if they do not already exist:

- database: `wikipedia_pageviews`
- schema: `main`
- table: `main.pageviews_daily`
- view: `main.pageviews_article_summary`
- share: `wikipedia_pageviews`

The share is created as organization-scoped and discoverable by default. After each load, the Flight runs `UPDATE SHARE "wikipedia_pageviews"` so the Dive can read the latest published snapshot.

## Public Data Source

The Flight uses the Wikimedia Pageviews API:

```text
https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/...
```

The default article set is `DuckDB`, `MotherDuck`, and `Wikipedia` for the last 30 complete days. Wikimedia asks API clients to send a useful `User-Agent`, so update `user_agent` in `flight_metadata.json` before deploying this in a real repository.

## Deployment Flow

The bundle is registered in `.github/workflows/deploy_bundles.yaml` with the bundle path and both component asset paths. The standalone Flight and Dive workflows remain available for standalone assets, but this example is intentionally deployed through the bundle workflow to preserve ordering.

The Flight has `"runOnDeploy": true`, so CI starts a run immediately after deploying it. That first run creates the tables and share. The Dive metadata uses:

```json
{
  "shareName": "wikipedia_pageviews",
  "previewShareName": "wikipedia_pageviews_preview_${BRANCH_SLUG}",
  "alias": "wikipedia_pageviews"
}
```

During Dive deployment, `scripts/deploy-dive.sh` resolves `shareName` to the generated `md:_share/...` URL by reading `MD_LIST_DATABASE_SHARES()`. During PR preview deployment, it resolves `previewShareName` instead, so the preview Dive reads the preview Flight's branch-scoped share.

The bundle workflow handles bootstrap ordering with `scripts/deploy-bundle.sh`: Flight, share wait, then Dive. That avoids hardcoding generated share URLs and avoids manually rerunning the Dive after the first Flight run.

## Preview Behavior

`flight_metadata.json` opts into preview Flights:

```json
{
  "preview": {
    "enabled": true,
    "runOnDeploy": true,
    "cleanupShare": true,
    "cleanupDatabase": true,
    "config": {
      "database": "wikipedia_pageviews_preview_${BRANCH_SLUG}",
      "share": "wikipedia_pageviews_preview_${BRANCH_SLUG}",
      "share_visibility": "HIDDEN"
    }
  }
}
```

On a pull request, the preview Flight is named `<Flight>:<branch> (Preview)`, has no schedule, runs once, and writes to the preview database/share. The preview Dive resolves `previewShareName` and reads that branch-scoped share. Cleanup deletes the preview Flight and drops the preview share/database when the PR closes or the branch is deleted.
