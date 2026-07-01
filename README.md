# MotherDuck Blueprints

MotherDuck Blueprints gives you a repository pattern for shipping MotherDuck Flights, Dives, shares, and future context assets. Pull requests validate blueprints, deploy branch-scoped previews, and leave a PR comment with the deployment plan and preview links; merges to `main` deploy stable production resources through a protected GitHub Environment.

Preview comments look like this:

```md
### Preview Blueprints

#### Deployment Plan

| Blueprint | Type | Key | Name | Action | Exists | ID | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wikipedia-pageviews | flight | loader | wikipedia-pageviews:feature/example (Preview) | create | no |  |  |

#### Wikipedia Pageviews

##### Shares

| Share | Link |
|-------|------|
| wikipedia_pageviews_preview_feature_example | Open Share |
```

## Prerequisites

- Python 3.10 or newer.
- GitHub Actions secrets and a protected `motherduck-production` environment.
- A MotherDuck service account token for CI deployments.

Use a service account token so deployed resources are owned by automation rather than by one person's account.

## Quickstart

Generate a customer repository from the released CLI:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "md-blueprints==0.3.0"
.venv/bin/md-blueprints init motherduck-blueprints
cd motherduck-blueprints
```

Start without touching MotherDuck:

```bash
make setup
make validate
make preview-smoke wikipedia-pageviews
```

Then connect MotherDuck:

1. Add a GitHub Actions secret named `MOTHERDUCK_TOKEN`.
2. Create a GitHub Environment named `motherduck-production`.
3. Open a small pull request and confirm the preview deployment comment appears.
4. Merge after review to deploy production through the protected environment.

See [Set Up Your Repository](docs/setup-your-repository.md) for the full setup flow and [GitHub Setup](docs/github-setup.md) for the GitHub checklist.

## Add a Blueprint

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

Start with the scaffold:

```bash
make new-blueprint revenue-overview
make validate
make preview-smoke revenue-overview
```

Then replace the starter Flight and Dive with your real project logic.

When you have a MotherDuck token configured, inspect live create/update/delete actions before applying them:

```bash
.venv/bin/md-blueprints plan --target preview --branch feature/example --blueprints revenue-overview
.venv/bin/md-blueprints cleanup --dry-run --target preview --branch feature/example --blueprints revenue-overview
```

## Versioning

Customer repositories upgrade by bumping the pinned action or package version. The template is the starting point; the `md-blueprints` package and action are the long-term tooling contract.

Use the current major action tag in workflows:

```yaml
- uses: motherduckdb/motherduck-blueprints@v0
  with:
    command: validate
```

Install the CLI locally from PyPI:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "md-blueprints==0.3.0"
.venv/bin/md-blueprints validate
```

Live `plan`, `deploy`, and `cleanup` commands need the deploy extra, which includes the DuckDB Python runtime dependencies for MotherDuck:

```bash
.venv/bin/python -m pip install "md-blueprints[deploy]==0.3.0"
```

| action / CLI | schemaVersions supported | upgrade path |
| --- | --- | --- |
| v0.x | 1 | Current pre-1.0 contract |
| v1.x | 1 | First stable customer contract |
| v2.x | 1 deprecated, removed in v3; 2 current | Run `md-blueprints doctor` and `md-blueprints migrate --to latest` before bumping |

Minor releases are additive and should be safe to accept through Dependabot after preview validation. Major releases can introduce a new `schemaVersion`; run `doctor` and `migrate` first.

## Best Practices

- Keep one project or data product per `blueprints/<name>/` package.
- Use lowercase slug names such as `account-360` or `revenue-ops`.
- Keep preview resources branch-scoped and production resources stable.
- Run a deployment plan before live deploys and use cleanup dry-runs before deleting previews.
- Deploy from CI with a service account token.
- Store secrets in GitHub Actions, never in the repo.

## More Detail

- [Repository Reference](docs/repository-reference.md): layout, targets, local commands, CI/CD, and context-layer notes.
- [blueprint.yml Reference](docs/blueprint-yml-reference.md): complete field reference for blueprint manifests.
- [Tooling and Schema Versioning](docs/tooling-and-schema-versioning.md): package/action pinning, schema compatibility, migrations, release engineering, and future repo-split guidance.
- [Wikipedia Pageviews example](docs/examples/wikipedia-pageviews.md): a Flight that loads public data, publishes a share, and deploys a Dive that reads that share.
