# MotherDuck Blueprints

Deploy MotherDuck data pipelines and dashboards from a GitHub repository.

**Open a pull request → try a preview → merge to deploy production.**

## Start here

[Create a repository from the template](https://github.com/motherduckdb/blueprints-template/generate), choose a private repository, then follow the steps below in your new repository. The workflows and public-data examples are already included.

## Already using MotherDuck?

With Python 3.10+ and Git installed, export your existing Flights, Dives, and Guides into code before enabling deployment:

```bash
make install-deploy
motherduck login
motherduck status
make export
make validate
```

`make install-deploy` installs the supported MotherDuck CLI. Open a new terminal if `motherduck` is not yet on your PATH. Use the account that owns the resources, or provide its `MOTHERDUCK_TOKEN` through your secret manager instead of logging in.

`make export` writes all visible resources of these three types as disabled, UUID-bound packages. It preserves source and settings and makes no remote changes. Review the files and remove any unwanted starter packages before opening a deployment PR. Follow [adopt existing resources](docs/adopt-existing-resources.md) to check ownership, schedules, and dependencies before enabling them.

Agents: read [the operating guide](src/md_blueprints/template_repo/AGENTS.md) for the workflow, constraints, and adoption limits.

## Deploy the example

You need a MotherDuck service-account token and permission to configure your GitHub repository. No local installation is required.

1. In GitHub, open **Settings → Environments**, create `motherduck-production`, and add your token as an environment secret named `MOTHERDUCK_TOKEN`.
2. Open [`flights/wikipedia-pageviews-ingest/blueprint.yml`](flights/wikipedia-pageviews-ingest/blueprint.yml), change its `description`, and commit the change to a **new branch**. Open a pull request.
3. Wait for **Deploy Blueprints** to finish. Its PR comment links to your preview dashboard, backed by public Wikipedia pageview data.
4. Merge the PR to deploy production. Closing the PR removes its preview resources.

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

## More help

- [Setup and troubleshooting](docs/setup-your-repository.md)
- [Blueprint fields and options](docs/blueprint-yml-reference.md)
- [GitHub Action inputs](docs/github-action.md)
- [Guides as code](docs/guides-as-code.md) · [Repository reference](docs/repository-reference.md) · [Upgrades](docs/tooling-and-schema-versioning.md)

## Using the action in an existing repository

Once your repository has a `motherduck.yml` manifest and blueprints, this step validates them:

```yaml
- uses: actions/checkout@v7
- uses: motherduckdb/motherduck-blueprints@v0.5.0
```

Validation is the default. Deployment uses `command: deploy` and named inputs such as `target: prod`. See the [action guide](docs/github-action.md) for a complete workflow.

This is the tooling source repository. For contributions, see [CONTRIBUTING.md](CONTRIBUTING.md); report tooling bugs here, not in the generated template.
