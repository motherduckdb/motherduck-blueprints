# Wikipedia Pageviews Example

This example is a self-contained blueprint in `blueprints/wikipedia-pageviews/`.

## What It Deploys

- `resources.flights.pageviews_loader` - loads public Wikimedia pageview data into MotherDuck.
- `resources.shares.pageviews` - names the database share produced by the Flight.
- `resources.dives.pageviews` - reads from that share through the `wikipedia_pageviews` alias.

The Flight creates these MotherDuck objects if they do not already exist:

- database: `wikipedia_pageviews`
- schema: `main`
- table: `main.pageviews_daily`
- view: `main.pageviews_article_summary`
- share: `wikipedia_pageviews`

After each load, the Flight runs `UPDATE SHARE` so the Dive reads the latest published snapshot.

## Public Data Source

The Flight uses the Wikimedia Pageviews API:

```text
https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/...
```

The default article set is `DuckDB`, `MotherDuck`, and `Wikipedia` for the last 30 complete days. Wikimedia asks API clients to send a useful `User-Agent`, so update `variables.user_agent` in `blueprint.yml` before deploying this from your repository.

## Deployment Flow

The root `motherduck.yml` includes `blueprints/*/blueprint.yml`, so this blueprint is discovered automatically. No workflow path-filter registration is required.

On pull requests:

1. `.github/workflows/deploy_blueprints.yaml` computes changed blueprint packages.
2. `tools/md_blueprints validate` validates all manifests and rendered targets.
3. `tools/md_blueprints plan --target preview --branch <branch>` inspects live resources without mutating them.
4. `tools/md_blueprints deploy --target preview --branch <branch>` deploys changed blueprints.
5. The preview Flight name and Dive title include the branch name.
6. The preview database and share include `${target.branch_slug}`.
7. The Flight runs once, waits for success, waits for the share URL, and deploys the Dive.
8. A PR comment lists the plan plus preview Flights, shares, and Dives.

On merge to `main`, production deployment writes a live plan to the GitHub job summary, runs through the protected `motherduck-production` environment, and uses stable names.

## Preview Behavior

The `preview` target disables schedules and requires cleanup-sensitive data resources to include the branch slug. The rendered preview share for branch `feature/mock-test` is:

```text
wikipedia_pageviews_preview_feature_mock_test
```

Preview cleanup deletes the Dive first, then the Flight, then the preview share and database. Use `tools/md_blueprints cleanup --dry-run --target preview --branch <branch>` to inspect those actions without deleting anything. The cleanup guard refuses to drop preview data resources whose names do not include the rendered branch slug.

## Local Checks

```bash
make validate
make render-preview wikipedia-pageviews
make preview-smoke wikipedia-pageviews
make mock-test
```

`make preview-smoke` builds the Dive through the local Vite preview harness without starting a long-running development server.
