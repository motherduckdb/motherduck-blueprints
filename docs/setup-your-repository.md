# Set up your first deployment

Start with the [template repository](https://github.com/motherduckdb/blueprints-template/generate). Choose a private repository. It includes the workflows and public-data examples, so you can try deployment without installing anything locally.

## 1. Connect MotherDuck

Create a MotherDuck service account with a read/write token and permission to create the example resources. In your new GitHub repository, open **Settings → Environments**, create `motherduck-production`, and add the token as an environment secret named `MOTHERDUCK_TOKEN`.

The default setup uses this account for both previews and production. Never commit the token. If your GitHub plan does not offer Environments for this repository, resolve that before deploying; these workflows require an environment secret.

## 2. Open your first preview

In GitHub, edit the `description` in `flights/wikipedia-pageviews-ingest/blueprint.yml`. Choose **Create a new branch for this commit** and open a pull request. Start with the Flight package so the first production deployment creates the data before the dashboard.

Wait for **Deploy Blueprints** to finish. It loads public Wikipedia data and posts a comment containing the plan and preview links. Open the Dive link to see the dashboard.

Change an example file for this first PR: an empty commit or a top-level README-only change does not trigger deployment. Fork PRs validate without deployment credentials.

## 3. Deploy production

Merge the PR into `main`. The workflow deploys the changed packages to production and shows its plan in the Actions job summary. Preview resources are cleaned up when the PR closes.

A manual deployment with no package selection deploys the Wikipedia pipeline and dashboard, plus any projects you add. The optional NCS example under `examples/` is not deployed. See [enable NCS](examples/ncs-field-recovery.md). Removing source files does not delete already-deployed production resources.

## Work locally (optional)

Install Python 3.10+ and Git, clone your repository, and run:

```bash
make validate
```

For dashboard development, install Node.js 22+ and run:

```bash
make setup
make preview-smoke wikipedia-pageviews
```

Validation and preview builds do not connect to MotherDuck. To open a live local preview after deploying the data, set `VITE_MOTHERDUCK_TOKEN` in the ignored `.dive-preview/.env`, then run `make preview wikipedia-pageviews`. Keep this local development token private.

Create a new pipeline and dashboard with `make new-project revenue`. Edit its files under `projects/revenue/`, run `make validate`, and open a PR. For separate pipeline and dashboard packages, see the [repository reference](repository-reference.md).

## If something does not work

| What you see | What to check |
| --- | --- |
| No deployment run | Change a file inside an example package and open the PR against `main`. |
| Waiting for approval | Approve the deployment in Actions if you configured required environment reviewers. |
| Missing token | Put `MOTHERDUCK_TOKEN` in **Settings → Environments → motherduck-production**, not repository secrets. |
| Permission error from MotherDuck | Check the service account's privileges. Custom roles and organization-wide Guides require an admin identity. |
| Local Python setup fails | Select a working interpreter, for example `make validate PYTHON=python3.13`. |
| No preview comment on a fork PR | Expected: fork PRs validate only. Use a branch in your own repository to deploy. |

Before team use, [configure branch protection and deployment approvals](github-setup.md). In the default setup, environment approval rules apply to previews and cleanup as well as production.

## Add staging (optional)

Add staging when production credentials must not be available to pull requests or ordinary `main` deployments.

1. Create a second MotherDuck service account for staging.
2. Create a GitHub Environment named `motherduck-staging` and add its token as an environment secret named `MOTHERDUCK_TOKEN`.
3. Change `targets.preview.environment` and `targets.preview.deployment.identity` to the staging environment and service account.
4. Add the conventional staging target:

```yaml
targets:
  preview:
    mode: preview
    environment: motherduck-staging
    deployment:
      tokenEnvVar: MOTHERDUCK_TOKEN
      identity: GitHub Actions staging service account
    policies:
      disableSchedules: true
      cleanup: true
      requireBranchSlugInDataResources: true

  staging:
    mode: production
    environment: motherduck-staging
    deployment:
      tokenEnvVar: MOTHERDUCK_TOKEN
      identity: GitHub Actions staging service account

  prod:
    mode: production
    environment: motherduck-production
    deployment:
      tokenEnvVar: MOTHERDUCK_TOKEN
      identity: GitHub Actions production service account
```

5. Give every produced staging share a distinct physical name:

```yaml
resources:
  shares:
    events:
      name: acme_events
      database: events
      targets:
        staging:
          name: acme_events_staging
```

The database can remain `events` because each service account owns its own database. The share name must differ across staging and production. Use a customer-specific logical prefix because Blueprints can detect collisions between declared targets but cannot inspect unrelated accounts.

After staging is present, the workflow changes automatically:

1. Pull requests deploy branch-scoped previews through `motherduck-staging`.
2. Merges to `main` deploy stable staging resources.
3. A published, non-prerelease GitHub Release checks out its exact tag and deploys every blueprint to production.

Promotion reconciles the tagged code under the production service account. It does not copy staging databases or data.

## Keep the tooling current

Run `make upgrade` to update the CLI and all action pins together and show the diff. It does not commit, push, or overwrite workflow settings. Use `make upgrade VERSION=0.4.2` to select a release, or `.venv/bin/md-blueprints upgrade` for a dry run. The scheduled Doctor workflow reports outdated tooling and configuration problems. See [upgrades and migrations](tooling-and-schema-versioning.md).

For live local commands, run `make install-deploy` first. For a custom workflow, see [GitHub Action inputs](github-action.md).
