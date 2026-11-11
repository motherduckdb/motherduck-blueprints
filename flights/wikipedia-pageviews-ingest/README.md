# Wikipedia Pageviews Ingest

The starter Flight. It loads daily pageviews for a list of Wikipedia articles from the public Wikimedia API, stores them in the `wikipedia_pageviews` database, and publishes that database as a share. The `wikipedia-pageviews` Dive reads the share through the `pageviews` output.

Use it as the pattern for loading any HTTP API on a schedule.

## What it deploys

- Flight `wikipedia-pageviews`: runs daily at 06:17 UTC and once on every deploy.
- Share `wikipedia_pageviews`, exported as the `pageviews` output.
- Table `main.pageviews_daily`: one row per project, article, access method, agent type, and day.
- View `main.pageviews_article_summary`: one row per article with totals over the loaded window.

A pull-request preview uses a database and share named after the branch, runs the Flight once, and has no schedule.

## Change what it loads

Edit `variables` in `blueprint.yml`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `articles` | `DuckDB,MotherDuck,Wikipedia` | Comma-separated article titles, as written in the article URL. |
| `days_back` | `30` | Complete days to load on each run. |
| `database`, `share` | `wikipedia_pageviews` | Names of the database and the share. |
| `user_agent` | Blueprints default | Identifies your requests to Wikimedia. Set your own contact URL. |

## Patterns to reuse

- **Reruns are safe.** Each run deletes the days it is about to load and inserts them again, so a retry or an overlapping window never duplicates rows.
- **Load in bulk.** Rows are staged in a temporary table and written to MotherDuck with one `INSERT ... SELECT`.
- **Retry the source.** HTTP calls retry with a pause, and the run fails when the API keeps failing.
- **Publish at the end.** The Flight runs `UPDATE SHARE` after the load so readers see the new day.
- **Attach only this database.** The connection uses `attach_mode=single`, which starts faster than attaching the whole workspace.

## Work on it

Edit `blueprint.yml` for deployment settings and `src/flight.py` for the load. Run `make validate` from the repository root. Start the first example pull request by changing this package, so production deploys the data before the dashboard.

Next steps built on this data: a [SQL transformation](../../examples/pageviews-weekly-trends/README.md), an [hourly freshness monitor](../../examples/data-freshness-monitor/README.md), and a [Guide](../../examples/pageviews-guide/README.md). See the [walkthrough](../../docs/examples/wikipedia-pageviews.md) for how selection and previews behave.

This is a new-resource example, not an import template. For an existing pipeline, follow [adoption](../../docs/adopt-existing-resources.md) and preserve its schedule, configuration, and identity deliberately.
