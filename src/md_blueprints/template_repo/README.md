# Your MotherDuck project

This repository uses MotherDuck Blueprints to deploy your data pipelines and dashboards.

**Open a pull request → try a preview → merge to deploy production.**

If you are viewing the original template, [create your own repository first](https://github.com/motherduckdb/blueprints-template/generate).

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
