# MotherDuck Blueprints

MotherDuck Blueprints manages Flights, Dives, Guides, shares, and roles as version-controlled packages. Pull requests validate changes and deploy branch-scoped previews; merges to `main` deploy production resources; branch cleanup removes previews.

This repository is the upstream source for that system. It is not the repository customers should copy and fill with their own blueprints.

## Which repository should I use?

| Repository | Purpose | Who changes it? |
| --- | --- | --- |
| [`motherduckdb/motherduck-blueprints`](https://github.com/motherduckdb/motherduck-blueprints) (this repository) | Builds the `md-blueprints` CLI, GitHub Action, schemas, deployment engine, and canonical customer template. | Tooling contributors. |
| [`motherduckdb/blueprints-template`](https://github.com/motherduckdb/blueprints-template) | Provides the released starting point for a new customer repository. It is generated from this repository and overwritten on every release. | Nobody directly; use **Use this template** instead of opening a PR. |
| Your repository created from the template | Contains your `blueprint.yml` manifests, Flight and Dive source, Guides, roles, and deployment configuration. | Your team. |

The release flow is: this repository produces a versioned CLI and Action, generates `blueprints-template` from `src/md_blueprints/template_repo/`, and stamps both with the same release version. A customer then creates an independent repository from that template.

## Start a customer repository

Create a private repository from the generated template:

```bash
gh repo create <your-org>/motherduck-blueprints \
  --template motherduckdb/blueprints-template --private --clone
cd motherduck-blueprints
```

Then follow [Set Up Your Repository](docs/setup-your-repository.md) to add a MotherDuck service-account token, configure the protected production environment, and test the first preview.

The generated repository includes:

- working Flight, Dive, Guide, role, and project examples;
- local validation and Dive preview commands;
- pull-request preview, production deploy, cleanup, and upgrade-check workflows;
- an exact, matching CLI and GitHub Action version pin.

Do not fork or copy this tooling repository to start a customer project. Use `blueprints-template` so the repository contains only the files customers are expected to own.

## Work on the tooling

The main implementation surfaces are:

```text
src/md_blueprints/                 CLI, validation, planning, deployment, and migrations
src/md_blueprints/template_repo/   source of the generated customer template
action.yml                         reusable GitHub Action
schemas/                           public manifest schemas
flights/, dives/, guides/, roles/, projects/
                                    examples used to exercise the tooling
tests/                              unit and contract tests
```

Set up the development environment and run the required pull-request checks:

```bash
make setup
make validate
make mock-test
make example-smoke
```

When a package includes a Dive, also run:

```bash
make preview-smoke <blueprint-name>
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete development and pull-request workflow. Every pull request must update [CHANGELOG.md](CHANGELOG.md).

## Blueprint package model

Customer repositories organize independently deployed packages by ownership and lifecycle:

```text
flights/   producers, shares, and named outputs
dives/     dashboards with declared inputs
guides/    version-controlled context for agents and collaborators
roles/     production RBAC roles and memberships
projects/  resources that genuinely preview, ship, and roll back together
```

Packages declare resources in `blueprint.yml`. Same-repository producers and consumers connect through named `outputs` and `inputs`. Preview selection includes connected producers and consumers; production selection expands downstream only.

The generated repository provides typed scaffolds such as:

```bash
make new-flight events-ingest
make new-dive events-dashboard INPUT=events-ingest.data
make new-guide revenue-metrics
make new-project revenue-overview
```

## Releases and upgrades

Releases keep four things aligned: the CLI version, GitHub Action tag, schema support, and generated template. Customer repositories pin the exact CLI and Action release together; Blueprints Doctor reports newer releases or pin drift.

The template repository is release output, not a second source of truth. Template changes must be made under `src/md_blueprints/template_repo/` in this repository and verified by the template drift and package smoke tests.

See [Tooling and Schema Versioning](docs/tooling-and-schema-versioning.md) for the compatibility, migration, and release contracts.

## Documentation

- [Repository Reference](docs/repository-reference.md): package layout, targets, local commands, and CI/CD.
- [blueprint.yml Reference](docs/blueprint-yml-reference.md): complete manifest field reference.
- [Set Up Your Repository](docs/setup-your-repository.md): customer repository setup.
- [Manage Guides as code](docs/guides-as-code.md): Guide scaffolding, previews, references, and deployment.
- [Wikipedia Pageviews example](docs/examples/wikipedia-pageviews.md): independent Flight producer and Dive consumer.
- [NCS Field Recovery Explorer](docs/examples/ncs-field-recovery.md): a complete Flight, share, Dive, and Guide project.

Issues and pull requests belong in this repository. To report a security issue, see [SECURITY.md](SECURITY.md).
