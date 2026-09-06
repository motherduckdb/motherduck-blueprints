# Protect your GitHub repository

Complete the [first deployment](setup-your-repository.md) before adding required checks, so GitHub can list the workflow names.

## Protect main

In **Settings → Branches** (or your repository rulesets), require pull requests, reviews, and the validation checks before merging to `main`. If you enable Code Owner reviews, first replace the examples in `.github/CODEOWNERS` with your own users or teams.

## Require deployment approval

Open **Settings → Environments → motherduck-production** and add required reviewers if your team needs deployment approval.

In the default setup, previews, production, and cleanup all use this environment, so its approval and branch rules apply to all three. Allow PR branches if you want previews to deploy. To approve production separately, [add staging](setup-your-repository.md#add-staging-optional).

## Keep credentials and cleanup configured

Store `MOTHERDUCK_TOKEN` as an environment secret containing a MotherDuck service-account read/write token. Same-repository deployments fail with a configuration message if it is missing. Fork PRs validate without secrets.

Keep **Cleanup Preview Blueprints** enabled. It removes preview resources on PR close or branch deletion, checking both branch and base manifests on PR close.

For custom workflows, see the [GitHub Action guide](github-action.md). For version updates, see [tooling upgrades](tooling-and-schema-versioning.md).
