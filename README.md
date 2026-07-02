# MotherDuck Blueprints

MotherDuck Blueprints lets you manage MotherDuck resources the same way you manage application code: in a Git repository, reviewed through pull requests, and deployed by CI.

A blueprint is a small package that declares one data project — its [Flights](https://motherduck.com/docs/concepts/flights/) (scheduled Python jobs), [Dives](https://motherduck.com/docs/key-tasks/ai-and-motherduck/dives/) (interactive data apps), and [shares](https://motherduck.com/docs/key-tasks/sharing-data/sharing-overview/) — in a `blueprint.yml` manifest next to its source code. From there:

- **Pull requests** validate every blueprint, deploy branch-scoped previews, and leave a comment on the PR with the deployment plan and preview links.
- **Merges to `main`** deploy stable production resources through a protected GitHub Environment.
- **Branch cleanup** removes preview resources when the branch is deleted.

## What's in this repository

This repository is the source for the Blueprints tooling. As a user, you interact with three artifacts built from it:

| Artifact | What it is |
| --- | --- |
| [`motherduckdb/blueprints-template`](https://github.com/motherduckdb/blueprints-template) | A GitHub template repository — the fastest way to start. It is generated from this repository on each release, so don't open pull requests there. |
| [`md-blueprints` on PyPI](https://pypi.org/project/md-blueprints/) | The CLI for validating, planning, deploying, and migrating blueprints, locally or in CI. |
| `motherduckdb/motherduck-blueprints@v0` | The GitHub Action that the generated workflows use to run the CLI in CI. |

## Prerequisites

- Python 3.10 or newer.
- Node.js 20 or newer (only needed to preview Dives locally).
- A GitHub repository with Actions enabled.
- A MotherDuck [service account](https://motherduck.com/docs/key-tasks/service-accounts-guide/) token for CI deployments, so deployed resources are owned by automation rather than by one person's account.

## Quickstart

### 1. Create your repository

Use the template repository (recommended):

```bash
gh repo create <your-org>/motherduck-blueprints \
  --template motherduckdb/blueprints-template --private --clone
cd motherduck-blueprints
```

Or generate the same file set with the CLI:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install md-blueprints
.venv/bin/md-blueprints init motherduck-blueprints
cd motherduck-blueprints
```

### 2. Try it locally, without a MotherDuck token

```bash
make setup
make validate
make preview-smoke wikipedia-pageviews
```

The repository ships with a working example, [wikipedia-pageviews](docs/examples/wikipedia-pageviews.md): a Flight that loads public data and publishes a share, plus a Dive that reads that share.

### 3. Connect MotherDuck

1. Add a GitHub Actions secret named `MOTHERDUCK_TOKEN` containing your service account token.
2. Create a GitHub Environment named `motherduck-production` with required reviewers.
3. Open a small pull request and confirm the preview deployment comment appears.
4. Merge after review to deploy production through the protected environment.

See [Set Up Your Repository](docs/setup-your-repository.md) for the full setup flow and [GitHub Setup](docs/github-setup.md) for the GitHub checklist.

## Add a blueprint

A blueprint is one logical project or data product. Keep its manifest, Flight, Dive, and README together:

```text
blueprints/<blueprint-name>/
  blueprint.yml
  README.md
  src/
    flight.py
    requirements.txt
    dive.tsx
```

Start from the scaffold, then replace the starter Flight and Dive with your real project logic:

```bash
make new-blueprint revenue-overview
make validate
make preview-smoke revenue-overview
```

Once a MotherDuck token is configured, you can inspect live create/update/delete actions before applying them:

```bash
.venv/bin/md-blueprints plan --target preview --branch feature/example --blueprints revenue-overview
.venv/bin/md-blueprints cleanup --dry-run --target preview --branch feature/example --blueprints revenue-overview
```

## How deployments work

Every pull request gets a comment with the deployment plan and preview links:

```md
### Preview Blueprints

| Blueprint | Type | Key | Name | Action |
| --- | --- | --- | --- | --- |
| wikipedia-pageviews | flight | loader | wikipedia-pageviews:feature/example (Preview) | create |
```

- **Preview** deployments are branch-scoped: preview share and database names include the branch slug, Flight schedules are disabled, and resources are cleaned up when the branch goes away.
- **Production** deployments run only from `main`, through the `motherduck-production` GitHub Environment, so you can require manual approval before anything changes.

## Versioning and upgrades

Your repository pins the tooling in two places: the action tag in `.github/workflows/` and the CLI version installed locally. Upgrade by bumping those pins.

```yaml
- uses: motherduckdb/motherduck-blueprints@v0
  with:
    command: validate
```

Minor releases are additive and safe to accept through Dependabot after preview validation. Major releases can introduce a new manifest `schemaVersion`; run `md-blueprints doctor` and `md-blueprints migrate --to latest` first. See [Tooling and Schema Versioning](docs/tooling-and-schema-versioning.md) for the compatibility policy.

Live `plan`, `deploy`, and `cleanup` commands need the deploy extra, which includes the DuckDB runtime dependencies:

```bash
.venv/bin/python -m pip install "md-blueprints[deploy]"
```

## Best practices

- Keep one project or data product per `blueprints/<name>/` package.
- Use lowercase slug names such as `account-360` or `revenue-ops`.
- Run a deployment plan before live deploys and use cleanup dry-runs before deleting previews.
- Deploy from CI with a service account token; store secrets in GitHub Actions, never in the repo.

## Learn more

- [Repository Reference](docs/repository-reference.md): layout, targets, local commands, CI/CD, and context-layer notes.
- [blueprint.yml Reference](docs/blueprint-yml-reference.md): complete field reference for blueprint manifests.
- [Tooling and Schema Versioning](docs/tooling-and-schema-versioning.md): package/action pinning, schema compatibility, and migrations.
- [Wikipedia Pageviews example](docs/examples/wikipedia-pageviews.md): the end-to-end example blueprint.
- [MotherDuck documentation](https://motherduck.com/docs/getting-started) and the [MotherDuck Community Slack](https://slack.motherduck.com/) for product questions and support.

## Contributing

Issues and pull requests are welcome in this repository — see [CONTRIBUTING.md](CONTRIBUTING.md). Don't open pull requests against `blueprints-template`; it is regenerated on each release. To report a security issue, see [SECURITY.md](SECURITY.md).
