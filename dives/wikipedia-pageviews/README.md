# Wikipedia Pageviews

This starter dashboard reads `wikipedia-pageviews-ingest.pageviews`. Edit `src/dive.tsx` for the dashboard and `blueprint.yml` for mounts and metadata. From the repository root, run `make validate` and `make preview-smoke wikipedia-pageviews`.

Preview selection includes the producer. A production dashboard-only change assumes the producer's share already exists; change or select the Flight package for the first deployment.

For an existing dashboard, follow [adoption](../../docs/adopt-existing-resources.md). Preserve mount aliases and the exact title, and verify the planned UUID before updating it.
