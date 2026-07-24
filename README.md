# MotherDuck Blueprints

MotherDuck Blueprints lets you manage MotherDuck resources the same way you manage application code: in a Git repository, reviewed through pull requests, and deployed by CI.

A blueprint is an independently deployable package with a `blueprint.yml` manifest next to its source. Typed roots make [Flights](https://motherduck.com/docs/concepts/flights/), [Dives](https://motherduck.com/docs/key-tasks/ai-and-motherduck/dives/), Guides, and RBAC roles easy to find; explicit inputs and outputs connect packages that share data. From there:

- **Pull requests** validate every blueprint, deploy branch-scoped previews, and leave a comment on the PR with the deployment plan and preview links.
- **Merges to `main`** deploy stable production resources through a protected GitHub Environment.
- **Branch cleanup** removes preview resources when the branch is deleted.

Dive governance travels with the code: previews are always `draft`, while production manifests can declare `ready`, `endorsed`, or `archived`. Deployment plans show live-to-desired status transitions before anything changes.

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

The repository ships with a working [Wikipedia Pageviews](docs/examples/wikipedia-pageviews.md) graph: a Flight producer publishes a named output and an independently owned Dive consumes it.

### 3. Connect MotherDuck

1. Add a GitHub Actions secret named `MOTHERDUCK_TOKEN` containing your service account token.
2. Create a GitHub Environment named `motherduck-production` with required reviewers.
3. Open a small pull request and confirm the preview deployment comment appears.
4. Merge after review to deploy production through the protected environment.

See [Set Up Your Repository](docs/setup-your-repository.md) for the full setup flow and [GitHub Setup](docs/github-setup.md) for the GitHub checklist.

## Add a Blueprint

Use the root that matches the package's ownership boundary:

```text
flights/   # producers, shares, and named outputs
dives/     # dashboards with declared inputs
guides/    # version-controlled agent context
roles/     # production RBAC roles and memberships
projects/  # resources that genuinely ship together
shared/    # human convention; no deployment behavior
```

Create a producer and consumer:

```bash
make new-flight events-ingest
make new-dive events-dashboard INPUT=events-ingest.data
make validate
make preview-smoke events-dashboard
```

Use `make new-project revenue-overview` when a Flight and Dive genuinely preview and roll back as one unit. Existing `blueprints/<name>/` repositories remain supported indefinitely; no migration is required.

Guide packages can publish versioned Markdown with catalog, Dive, Flight, and Guide references. Role packages and share grants provide declarative RBAC; admin-only operations run a capability preflight before any mutation.

Once a MotherDuck token is configured, you can inspect live create/update/delete actions before applying them:

```bash
.venv/bin/md-blueprints plan --target preview --branch feature/example --blueprints events-dashboard
.venv/bin/md-blueprints cleanup --dry-run --target preview --branch feature/example --blueprints events-dashboard
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
- **Dive status** is reconciled only when declared. Omitting it preserves the live status; setting `endorsed` requires an organization-admin deployment identity.
- **Dependency selection** expands both upstream and downstream for preview. Production expands downstream only, so a consumer-only change does not rerun an unchanged producer.

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

- Use typed roots for independently owned assets and `projects/` only for resources that truly ship together.
- Declare same-repository dependencies through `inputs` and `outputs`; use literal share URLs across repositories.
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
