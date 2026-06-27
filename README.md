# MotherDuck Blueprints

Canonical, version-controlled MotherDuck Blueprints for deployable Flights, Dives, shares, and future context-layer assets.

The repository uses a project-first layout inspired by Databricks Declarative Automation Bundles: source code, resource metadata, target overrides, validation, preview deployment, and production deployment live together in self-contained `blueprints/<name>/` packages.

## Start Here

For a new customer repo:

1. Copy this repository into the customer's GitHub organization.
2. Add the `MOTHERDUCK_TOKEN` repository secret, preferably from a MotherDuck service account.
3. Create the protected `motherduck-production` GitHub Environment.
4. Run `make validate` and `make mock-test`.
5. Open a small PR and confirm the preview deployment comment appears.

See [docs/customer-onboarding.md](docs/customer-onboarding.md) for the full setup flow and [docs/github-setup.md](docs/github-setup.md) for a shorter GitHub-only checklist.

## Repository Layout

```text
motherduck.yml
CHANGELOG.md

blueprints/
  <blueprint-name>/
    blueprint.yml
    README.md
    src/
      flight.py
      requirements.txt
      dive.tsx

schemas/
  motherduck-root.schema.json
  blueprint.schema.json

tools/
  md_blueprints

context/
  README.md
  policies/
  schemas/
```

`motherduck.yml` is the canonical repository manifest. It declares included blueprint manifests, shared variables, and the `preview` and `prod` targets. GitHub Actions discover changed blueprints from this manifest instead of requiring manual path-filter registration.

`CHANGELOG.md` records notable repository changes. Update it in every pull request.

## Project Granularity

A `blueprints/<name>/` package is the MotherDuck equivalent of a Databricks bundle: one logical project or data product that should be reviewed, previewed, deployed, rolled back, and understood as a unit.

Use a blueprint package for examples like `customer-360`, `revenue-ops`, `support-insights`, or `wikipedia-pageviews`. Do not use a blueprint package for an entire organization, all databases owned by a user, all resources owned by a service account, or all production assets across unrelated projects.

MotherDuck differs from Databricks here because a single MotherDuck user or service account can own many databases, and one project can occasionally involve more than one service account. That does not change the package boundary:

- Databases are resources or variables inside a project package.
- Service accounts are deployment/runtime identity choices for a target or resource.
- Targets such as `preview`, `staging`, and `prod` describe environment behavior.
- The root `motherduck.yml` is a repository catalog and policy file, not an organization-wide bundle.

Prefer one deployment service account per project/environment. If a project must use multiple service accounts, model that explicitly as identity configuration for the affected target or resource instead of splitting one project into artificial packages.

## Blueprint Packages

Each deployable project lives under `blueprints/<name>/` and declares resources in `blueprint.yml`:

- `resources.flights` for Python Flights.
- `resources.dives` for React/SQL Dives.
- `resources.shares` for produced data products used by Flights and Dives.
- `resources.context` for context-layer files that validate now but do not deploy until MotherDuck exposes that API.

Standalone Dives or Flights are represented as one-resource blueprints. A Flight + Dive pair should usually be one blueprint so preview deployment, share waiting, and cleanup stay coordinated.

Blueprint names are lowercase slugs (`a-z`, `0-9`, and `-`) because they are used as directory names, CI selectors, and deployment identifiers.

Create a package with:

```bash
make new-blueprint <blueprint-name>
```

Then edit `blueprints/<blueprint-name>/blueprint.yml` and the files under `src/`.

The generated package is the recommended starting example. It creates a small `starter_metrics` table, publishes a branch- or production-scoped share, and deploys a Dive that reads the share. Replace the starter data and query with your project logic while keeping the same package boundary: one logical project or data product per blueprint.

## Deployment Targets

The repo defines two targets:

- `preview`: branch-scoped resource names, schedules disabled, preview cleanup enabled.
- `prod`: stable production names, protected by the `motherduck-production` GitHub Environment.

Preview resources must include `${target.branch_slug}` in cleanup-sensitive share/database names. This prevents cleanup from dropping stable production resources.

## Local Commands

```bash
make setup
make preview <blueprint-name>
make preview-smoke <blueprint-name>
make new-blueprint <blueprint-name>
make validate
make render-preview <blueprint-name>
make mock-test
```

`make validate` parses `motherduck.yml`, expands included blueprints, validates against the committed schemas, renders preview and production targets, checks uniqueness, checks Flight Python syntax, and validates Dive required resources.

`make preview-smoke <blueprint-name>` writes that blueprint's Dive into the local Vite preview harness and runs a production build without starting a server.

`make mock-test` shadows `duckdb` with a fake CLI and exercises validation, preview deploy, production deploy, cleanup, and failed Flight run reporting without contacting MotherDuck.

Run this minimum set before opening a PR:

```bash
make validate
make mock-test
make preview-smoke <blueprint-name> # when the blueprint has a Dive
```

## CI/CD Flow

- Pull requests validate all manifests, discover changed blueprint packages from `motherduck.yml`, deploy the `preview` target, and comment with preview links.
- Preview cleanup runs when a PR closes or a branch is deleted. Dives are deleted before Flights, shares, and preview databases.
- Pushes to `main` deploy the `prod` target through the protected `motherduck-production` environment.
- No workflow file needs per-blueprint path filters or manual asset registration.

## Examples

Start with the scaffolded starter example:

```bash
make new-blueprint revenue-overview
make validate
make render-preview revenue-overview
make preview-smoke revenue-overview
```

This repo also includes one richer public-data example:

- [blueprints/wikipedia-pageviews/blueprint.yml](blueprints/wikipedia-pageviews/blueprint.yml) defines the Flight, share, and Dive resources.
- [blueprints/wikipedia-pageviews/src/flight.py](blueprints/wikipedia-pageviews/src/flight.py) loads Wikimedia pageview data into MotherDuck and publishes a share.
- [blueprints/wikipedia-pageviews/src/dive.tsx](blueprints/wikipedia-pageviews/src/dive.tsx) reads the share through the `wikipedia_pageviews` alias.

See [docs/examples/wikipedia-pageviews.md](docs/examples/wikipedia-pageviews.md).

## Context Layer

The `context/` directory is intentionally lightweight for now. Keep proposed schemas, prompts, relationship definitions, or policy files there until MotherDuck publishes the context-layer deployment interface. Blueprint `resources.context` entries validate files and intentionally refuse deployment while that API does not exist.
