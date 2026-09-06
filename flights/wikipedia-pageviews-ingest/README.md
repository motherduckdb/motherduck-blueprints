# Wikipedia Pageviews Ingest

This starter Flight loads public Wikimedia pageviews and publishes the `pageviews` output. The `wikipedia-pageviews` Dive consumes it.

Edit `blueprint.yml` for deployment settings and `src/flight.py` for ingestion logic. Run `make validate` from the repository root. Start the first example PR by changing this package so production deploys the data before the dashboard.

This is a new-resource example, not an import template. For an existing pipeline, follow [adoption](../../docs/adopt-existing-resources.md) and preserve its schedule, configuration, and identity deliberately.
