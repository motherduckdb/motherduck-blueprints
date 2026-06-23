# MotherDuck Blueprints

Canonical, version-controlled MotherDuck Blueprints for:

- `dives/` - React/SQL Dives deployed through PR preview and main-branch production workflows.
- `flights/` - Python Flight definitions validated on PRs, optionally previewed on PRs, and deployed to MotherDuck after merge.
- `bundles/` - orchestration manifests for Flight + Dive combinations that need ordered deployment.
- `context/` - reserved Blueprint area for the context layer once the production API and deploy surface are available.

This repository is the GitHub home for deployable MotherDuck Blueprints. Changes land through pull requests, reviewers approve the diff, GitHub Actions validates or previews the change, and production deployment runs from `main`.

## Required GitHub Setup

1. Create a GitHub repository named `motherduck-blueprints` from this folder.
2. Add a repository secret named `MOTHERDUCK_TOKEN`.
   - Use a MotherDuck service account token for shared repos.
   - A personal read/write token works for local development, but deployed assets will be owned by that person.
3. Create a GitHub Environment named `motherduck-production`.
   - Add required reviewers to the environment so production deploys require approval.
4. Enable branch protection on `main`.
   - Require pull requests before merging.
   - Require approvals.
   - Require review from Code Owners after you update `.github/CODEOWNERS`.
   - Require status checks for the workflows you register.

See [docs/customer-onboarding.md](docs/customer-onboarding.md) for the full customer setup flow and [docs/github-setup.md](docs/github-setup.md) for the shorter GitHub setup reference.

## Repository Layout

```text
dives/
  <dive-name>/
    <dive-name>.tsx
    dive_metadata.json

flights/
  <flight-name>/
    flight.py
    flight_metadata.json
    requirements.txt

bundles/
  <bundle-name>/
    blueprint.json

context/
  README.md
  policies/
  schemas/

scripts/
  deploy-bundle.sh
  cleanup-preview-bundle.sh
  deploy-dive.sh
  deploy-flight.sh
  validate-flight.sh
```

## Local Dive Preview

```bash
make setup
make preview <dive-name>
```

The preview uses the committed `.dive-preview/` Vite app in this repository. Copy `.dive-preview/.env.example` to `.dive-preview/.env` and set `VITE_MOTHERDUCK_TOKEN` before previewing.

## Creating a Dive

```bash
make new-dive revenue-overview
```

Then:

1. Edit `dives/revenue-overview/dive_metadata.json`.
2. Build `dives/revenue-overview/revenue-overview.tsx`.
3. Register the folder in `.github/workflows/deploy_dives.yaml`:

```yaml
filters: |
  revenue-overview: dives/revenue-overview/**
```

On pull requests, changed registered Dives deploy as previews named `<Title>:<branch> (Preview)`. On merge to `main`, changed registered Dives deploy as production Dives.

Required resources can reference a fixed share URL or a share name:

```json
{
  "shareName": "wikipedia_pageviews",
  "previewShareName": "wikipedia_pageviews_preview_${BRANCH_SLUG}",
  "alias": "wikipedia_pageviews"
}
```

When `shareName` is present, CI resolves it to the generated `md:_share/...` URL before deploying the Dive. On PR previews, `previewShareName` can point the preview Dive at a branch-scoped preview share.

## Creating a Flight

```bash
make new-flight daily-refresh
```

Then:

1. Edit `flights/daily-refresh/flight_metadata.json`.
2. Implement `flights/daily-refresh/flight.py`.
3. Add dependencies to `flights/daily-refresh/requirements.txt`.
4. Register the folder in `.github/workflows/deploy_flights.yaml`:

```yaml
filters: |
  daily-refresh: flights/daily-refresh/**
```

On pull requests, changed registered Flights are validated locally. If a Flight opts into previews, CI deploys a non-scheduled branch-scoped preview Flight and comments on the PR. On merge to `main`, changed registered Flights deploy through the protected `motherduck-production` environment.

Set `"runOnDeploy": true` in `flight_metadata.json` when a Flight should run immediately after CI creates or updates it.

Flights can opt in to PR previews:

```json
{
  "preview": {
    "enabled": true,
    "runOnDeploy": true,
    "cleanupShare": true,
    "cleanupDatabase": true,
    "config": {
      "database": "example_preview_${BRANCH_SLUG}",
      "share": "example_preview_${BRANCH_SLUG}"
    }
  }
}
```

Preview Flights are deployed with schedules disabled. Cleanup runs on PR close and branch deletion, deleting the preview Flight and optionally dropping branch-scoped preview shares/databases.

## Creating a Bundle

Use a bundle when a Flight and Dive need to deploy together in order.

```text
bundles/wikipedia-pageviews/blueprint.json
```

The manifest links existing Flight and Dive folders:

```json
{
  "name": "wikipedia-pageviews",
  "title": "Wikipedia Pageviews",
  "preview": { "enabled": true, "cleanup": true },
  "flights": [
    {
      "name": "wikipedia-pageviews",
      "path": "flights/wikipedia-pageviews",
      "waitForShares": [
        {
          "production": "wikipedia_pageviews",
          "preview": "wikipedia_pageviews_preview_${BRANCH_SLUG}"
        }
      ]
    }
  ],
  "dives": [
    {
      "name": "wikipedia-pageviews",
      "path": "dives/wikipedia-pageviews"
    }
  ]
}
```

Bundle deployment runs Flights first, waits for declared shares, then deploys Dives. PR previews post one coordinated comment with Flight, share, and Dive links. Register bundles in `.github/workflows/deploy_bundles.yaml`.

## Example Blueprint

This repo includes a paired public-data example:

- `flights/wikipedia-pageviews/` loads recent Wikimedia pageview data, creates tables and views, and publishes a MotherDuck share.
- `dives/wikipedia-pageviews/` reads the published share through the `wikipedia_pageviews` alias.
- `bundles/wikipedia-pageviews/` coordinates the Flight and Dive deployment.

See [docs/examples/wikipedia-pageviews.md](docs/examples/wikipedia-pageviews.md).

## Context Layer

The `context/` directory is intentionally lightweight for now. Keep proposed schemas, prompts, relationship definitions, or policy files there until MotherDuck publishes the context-layer deployment interface. When that API is available, add a dedicated deploy script and workflow beside the Dives and Flights lanes.

## Useful Commands

```bash
make help
make setup
make preview <dive-name>
make new-dive <dive-name>
make new-flight <flight-name>
make validate-flight <flight-name>
make validate-bundle <bundle-name>
make mock-test
```

`make mock-test` shadows `duckdb` with a local fake CLI and exercises the Wikipedia bundle preview deploy, production deploy, and cleanup flow without contacting MotherDuck.
