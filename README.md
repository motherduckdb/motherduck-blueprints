# MotherDuck Blueprints

Deploy MotherDuck data pipelines and dashboards from a GitHub repository.

**Open a pull request → try a preview → merge to deploy production.**

## Start here

[Create a repository from the template](https://github.com/motherduckdb/blueprints-template/generate), choose a private repository, then follow the steps below in your new repository. The workflows and public-data examples are already included.

## Deploy the example

You need a MotherDuck service-account token and permission to configure your GitHub repository. No local installation is required.

1. In GitHub, open **Settings → Environments**, create `motherduck-production`, and add your token as an environment secret named `MOTHERDUCK_TOKEN`.
2. Open [`flights/wikipedia-pageviews-ingest/blueprint.yml`](flights/wikipedia-pageviews-ingest/blueprint.yml), change its `description`, and commit the change to a **new branch**. Open a pull request.
3. Wait for **Deploy Blueprints** to finish. Its PR comment links to your preview dashboard, backed by public Wikipedia pageview data.
4. Merge the PR to deploy production. Closing the PR removes its preview resources.

If the environment requires approval, approve the deployment in GitHub Actions. Fork pull requests validate but do not deploy.

The default setup uses the same service account for previews and production. For separate credentials and release-based production deployment, [add staging](docs/setup-your-repository.md#add-staging-optional).

## Make it yours

Each `blueprint.yml` describes what to deploy; the source files beside it contain your code. Start by editing the Wikipedia example:

- [Flight](flights/wikipedia-pageviews-ingest/): Python that loads data and publishes a share.
- [Dive](dives/wikipedia-pageviews/): the dashboard that reads that share.

The repository also includes an [NCS field recovery example](projects/ncs-field-recovery/README.md). All included examples can deploy; remove unwanted example packages before your first deployment.

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
- uses: motherduckdb/motherduck-blueprints@v0.4.1
```

Validation is the default. Deployment uses `command: deploy` and named inputs such as `target: prod`. See the [action guide](docs/github-action.md) for a complete workflow.

This is the tooling source repository. For contributions, see [CONTRIBUTING.md](CONTRIBUTING.md); report tooling bugs here, not in the generated template.
