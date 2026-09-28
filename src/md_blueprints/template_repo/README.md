# Your MotherDuck project

This repository uses MotherDuck Blueprints to deploy your data pipelines and dashboards.

**Open a pull request → try a preview → merge to deploy production.**

If you are viewing the original template, [create your own repository first](https://github.com/motherduckdb/blueprints-template/generate).

## Already using MotherDuck?

In your repository created from the template, with Python 3.10+ and Git installed, export your existing Flights, Dives, and Guides into code before enabling deployment:

```bash
make install-deploy
motherduck login
motherduck status
make export
make validate
```

`make install-deploy` installs the supported MotherDuck CLI. Open a new terminal if `motherduck` is not yet on your PATH. Use the account that owns the resources, or provide its `MOTHERDUCK_TOKEN` through your secret manager instead of logging in. Only a Flight's creator can update it, so check [ownership](docs/adopt-existing-resources.md#1-use-the-current-tooling-and-intended-identity) before letting CI deploy exported Flights.

`make export` writes all visible resources of these three types as disabled, UUID-bound packages. It preserves source and settings and makes no remote changes. Review the files and remove any unwanted starter packages before opening a deployment PR. Follow [adopt existing resources](docs/adopt-existing-resources.md) to check ownership, schedules, and dependencies before enabling them.

Agents: read [the operating guide](AGENTS.md) for the workflow, constraints, and adoption limits.

## Deploy the example

You need:

- A [MotherDuck service account](https://motherduck.com/docs/key-tasks/service-accounts-guide/create-and-configure-service-accounts/) with a read/write token.
- Admin access to your GitHub repository. Private repositories need GitHub Pro, Team, or Enterprise for Environments.

No local installation is required.

1. In GitHub, open **Settings → Environments**, create `motherduck-production`, and add your token as an environment secret named `MOTHERDUCK_TOKEN`.
2. Open [`flights/wikipedia-pageviews-ingest/blueprint.yml`](flights/wikipedia-pageviews-ingest/blueprint.yml), change its `description`, and commit the change to a **new branch**. Open a pull request.
3. Wait for **Deploy Blueprints** to finish. Its PR comment links to your preview dashboard, backed by public Wikipedia pageview data.
4. Merge the PR to deploy production. Closing the PR removes its preview resources.

The Wikipedia Flight then refreshes daily in production. To remove the starter later, see [remove the example](docs/setup-your-repository.md#remove-the-example).

If the environment requires approval, approve the deployment in GitHub Actions. Fork pull requests validate but do not deploy.

The default setup uses the same service account for previews and production. For separate credentials and release-based production deployment, [add staging](docs/setup-your-repository.md#add-staging-optional).

## Make it yours

You normally edit only `motherduck.yml`, package manifests, and their source files. Deployment, cleanup, and upgrade checks run through versioned workflows maintained by Blueprints. Use `make upgrade` to update the tooling together. Optional roots such as `guides/`, `roles/`, and `projects/` appear when you create those packages; you do not need every resource type.

Each `blueprint.yml` describes what to deploy; the source files beside it contain your code. Start by editing the Wikipedia example:

- [Flight](flights/wikipedia-pageviews-ingest/): Python that loads data and publishes a share.
- [Dive](dives/wikipedia-pageviews/): the dashboard that reads that share.

Wikipedia is the only active starter. The [optional NCS example](docs/examples/ncs-field-recovery.md) stays outside deployment discovery until you enable it.

For local checks, install Python 3.10+ and Git, then run:

```bash
make validate
```

To build the example dashboard locally, also install Node.js 22+:

```bash
make setup
make preview-smoke wikipedia-pageviews
```

These checks do not need a MotherDuck token. A preview build checks the dashboard; it does not open a live preview.

Create your own data pipeline and dashboard with:

```bash
make new-project revenue
make validate
```

Edit the generated files in `projects/revenue/`, then open a pull request.

Ask your Claude, ChatGPT, or Codex agent: **"Initialize or update this repository's MotherDuck Guides. Follow `docs/guides-as-code.md`."** The agent reads the source and writes Markdown that explains the data and workflows. `make guides` gathers context, and `make guides DBT="/path/to/dbt-project"` adds dbt YAML documentation and relationship hints. See [the agent workflow](docs/guides-as-code.md).

Run **Actions → Prepare Guide context** to collect context in CI, with an optional dbt path. Download the `guide-context` artifact or pass it to your existing agent runner. See [Guide CI integration](docs/github-action.md#prepare-guides-in-ci).

## More help

- [Setup and troubleshooting](docs/setup-your-repository.md)
- [Blueprint fields and options](docs/blueprint-yml-reference.md)
- [GitHub Action inputs](docs/github-action.md)
- [Adapt names, environments, and branches](docs/repository-reference.md#adapt-the-defaults-to-your-organization)
- [Use with the MotherDuck Terraform provider](docs/use-with-terraform.md)
- [Guides as code](docs/guides-as-code.md) · [Repository reference](docs/repository-reference.md) · [Upgrades](docs/tooling-and-schema-versioning.md)
