# Set up your first deployment

Start with the [template repository](https://github.com/motherduckdb/blueprints-template/generate). Choose a private repository. It includes the workflows and public-data examples, so you can try deployment without installing anything locally.

If you already have resources in MotherDuck, follow [adopt existing resources](adopt-existing-resources.md) first. The walkthrough below deploys a new example. It is not an import procedure. If you manage MotherDuck with Terraform, also read [use with Terraform](use-with-terraform.md).

## Before you start

- **A GitHub plan with Environments for your repository.** Private repositories need GitHub Pro, Team, or Enterprise. [GitHub Free offers Environments only for public repositories](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
- **Admin access to the GitHub repository**, to create Environments and secrets.
- **A MotherDuck service account and a read/write token.** In MotherDuck, open **Settings → Service Accounts**, create an account, and create a read/write token for it. See [create and configure service accounts](https://motherduck.com/docs/key-tasks/service-accounts-guide/create-and-configure-service-accounts/). A shared service account keeps deployments working when people leave the team.

## 1. Connect MotherDuck

In your new GitHub repository, open **Settings → Environments**, create `motherduck-production`, and add the service-account token as an environment secret named `MOTHERDUCK_TOKEN`. Do not add it as a repository secret. Environment secrets are only released to jobs that pass that environment's rules.

The default setup uses this account for both previews and production. Never commit the token. To use another environment name, change `environment` for each target in `motherduck.yml`. See [adapt the defaults](repository-reference.md#adapt-the-defaults-to-your-organization).

## 2. Open your first preview

In GitHub, edit the `description` in `flights/wikipedia-pageviews-ingest/blueprint.yml`. Choose **Create a new branch for this commit** and open a pull request. Start with the Flight package so the first production deployment creates the data before the dashboard.

Wait for **Deploy Blueprints** to finish. It loads public Wikipedia data and posts a comment containing the plan and preview links. Open the Dive link to see the dashboard.

Change an example file for this first PR: an empty commit or a top-level README-only change does not trigger deployment. Fork PRs validate without deployment credentials.

## 3. Deploy production

Merge the PR into `main`. The workflow deploys the changed packages to production and shows its plan in the Actions job summary. Preview resources are cleaned up when the PR closes.

A manual deployment with no package selection deploys the Wikipedia pipeline and dashboard, plus any projects you add. The optional NCS example under `examples/` is not deployed. See [enable NCS](examples/ncs-field-recovery.md).

The Wikipedia Flight has a daily schedule (`scheduleCron: 17 6 * * *`) in production. Preview schedules are always disabled.

### Remove the example

When you no longer need the starter, delete `flights/wikipedia-pageviews-ingest/` and `dives/wikipedia-pageviews/` in a pull request. Removing source files never deletes deployed production resources. If the example already reached production, delete the **Wikipedia Pageviews** Dive, the `wikipedia-pageviews` Flight, and the `wikipedia_pageviews` share and database in MotherDuck yourself. Check the exact names in the package manifests first.

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

Validation and preview builds do not connect to MotherDuck. To open a live local preview after deploying the data, set `VITE_MOTHERDUCK_TOKEN` in the ignored `.dive-preview/.env`, then run `make preview wikipedia-pageviews`. A personal read/write token works for local preview, which only reads data. Keep it private. CI always uses the service-account token.

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
| `Unable to resolve action motherduckdb/motherduck-blueprints@vX.Y.Z` | The pinned release does not exist. Run `make upgrade` to move every pin to a published release. |
| `requiredCliVersion` error | The repository needs a newer CLI than the one installed. Run `make upgrade`, then `make setup`. |
| Flight run failed during deploy | Open the Flight in MotherDuck or run `motherduck flight logs` to read the run output. Fix the source and push again. |
| Error about the Flight owner or creator | Adopted Flights can only be updated by the identity that owns them. Deploy with that identity's token, or recreate the Flight under the service account. |
| Environments are missing from **Settings** | Private repositories on GitHub Free cannot use Environments. See [before you start](#before-you-start). |

Before team use, [configure branch protection and deployment approvals](#protect-your-github-repository). In the default setup, environment approval rules apply to previews and cleanup as well as production.

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

Run `make upgrade` to update the CLI, reusable workflows, and any direct action pins together and show the diff. It does not commit, push, or overwrite workflow settings. Use `make upgrade VERSION=X.Y.Z` to select a release, or `.venv/bin/md-blueprints upgrade` for a dry run. The scheduled Doctor workflow reports outdated tooling and configuration problems. See [upgrades and migrations](tooling-and-schema-versioning.md).

For existing resources, run `make install-deploy`, authenticate with `motherduck login`, check `motherduck status`, then run `make export`. Follow the [adoption guide](adopt-existing-resources.md) before enabling deployment. Other live local commands require the target token through your secret manager. For a custom workflow, see [GitHub Action inputs](github-action.md).

## Protect your GitHub repository

Complete the [first deployment](#2-open-your-first-preview) before adding required checks, so GitHub can list the workflow names.

### Protect main

In **Settings → Branches** (or your repository rulesets), require pull requests, reviews, and the validation checks before merging to `main`. If you enable Code Owner reviews, first replace the examples in `.github/CODEOWNERS` with your own users or teams.

### Require deployment approval

Open **Settings → Environments → motherduck-production** and add required reviewers if your team needs deployment approval.

In the default setup, previews, production, and cleanup all use this environment, so its approval and branch rules apply to all three. Allow PR branches if you want previews to deploy. To approve production separately, [add staging](#add-staging-optional).

### Keep credentials and cleanup configured

Store `MOTHERDUCK_TOKEN` as an environment secret containing a MotherDuck service-account read/write token. Same-repository deployments fail with a configuration message if it is missing. Fork PRs validate without secrets.

Keep **Cleanup Preview Blueprints** enabled. It removes preview resources on PR close or branch deletion, checking both branch and base manifests on PR close.

For custom workflows, see the [GitHub Action guide](github-action.md). For version updates, see [tooling upgrades](tooling-and-schema-versioning.md).
