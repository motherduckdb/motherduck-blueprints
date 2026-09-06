# Use the GitHub Action

The template already includes deployment and cleanup workflows. You do not need to write a workflow to use it.

Use the action directly when adding Blueprints to an existing repository with a `motherduck.yml` manifest.

## Validate pull requests

Save this as `.github/workflows/validate.yaml`:

```yaml
name: Validate Blueprints
on: [pull_request]
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: motherduckdb/motherduck-blueprints@v0.4.3
```

The action installs its own Python dependencies. Validation is the default command and needs no token.

## Deploy manually

Create the `motherduck-production` GitHub Environment and add your service-account token as its `MOTHERDUCK_TOKEN` secret. Save this as `.github/workflows/deploy.yaml`:

```yaml
name: Deploy Blueprints
on: [workflow_dispatch]
permissions:
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: motherduck-production
    concurrency:
      group: motherduck-production
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v7
      - uses: motherduckdb/motherduck-blueprints@v0.4.3
        env:
          MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}
        with:
          command: deploy
          target: prod
```

Run it from **Actions → Deploy Blueprints → Run workflow**. It deploys all packages and checks the deployment plan before applying changes. To deploy a subset, add `blueprints: revenue`.

This minimal workflow runs only when you request it. For automatic PR previews, comments, and cleanup, use the template's existing workflows.

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `command` | `validate` | CLI command, such as `plan`, `deploy`, `cleanup`, or `doctor`. |
| `target` | Command default | `prod` for deploy/plan; `preview` for cleanup; validation checks every target. |
| `branch` | Empty | Required for preview deployment and cleanup. Pass the branch name directly; no extra quotes are needed. |
| `blueprints` | All packages | Comma-separated package names, such as `orders,revenue`. Dependencies expand according to the target. |
| `root` | Checkout directory | Directory containing `motherduck.yml`, such as `analytics`. |
| `args` | Empty | Advanced CLI flags, such as `--json`, `--offline`, or `--dry-run`. |
| `verify-after-deploy` | `true` | Read back live identities, declared shares/inputs, and Dive status after deploy. Set `"false"` only to opt out of the postcheck. |
| `python-version` | `3.11` | Python runtime installed by the action. |

Named inputs override matching flags in `args`. Existing workflows using only `args` continue to work. The action passes named inputs as literal argument values, including spaces and quotes.

Live commands read `MOTHERDUCK_TOKEN` from the step environment. Select the GitHub Environment on the **job**; the action's `target` input does not select a GitHub Environment for you.

The `stdout` output contains the command's text or JSON result. Assign an `id` to the step to read `steps.<id>.outputs.stdout`. Command failures fail the step.

Pin the action and your local CLI to the same release. See [upgrades](tooling-and-schema-versioning.md).

## Checks before and after deployment

Every `deploy` performs manifest validation, authorization preflights, and a fresh live plan before the first write. Missing bound IDs, owner mismatches, and duplicate update identities fail before any resource is changed. This check cannot be disabled.

By default, deployment then reads back resource identities and checks declared shares/inputs and intended Dive status. Newly created IDs are captured and compared too. Verification results appear in the Actions summary; a failed postcheck fails the job and reports that deployment already ran. No automatic rollback is attempted.

For a separate read-only check of existing resources, including disabled imported bindings, use:

```yaml
- uses: motherduckdb/motherduck-blueprints@v0.4.3
  env:
    MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}
  with:
    command: verify
    target: prod
    blueprints: YOUR_PACKAGE
```

Run this in the same GitHub Environment as the deployment job. Use `command: plan` instead for new resources that do not exist yet: `verify` requires existing identities. The CLI equivalent is `md-blueprints verify --target prod --blueprints YOUR_PACKAGE --json`.

These are lifecycle checks, not customer data tests: they do not execute arbitrary assertions, compare all source/configuration fields, or prove every external query permission. Flight run success still uses `waitForRun: success`. Customers with a separate verification stage can set `verify-after-deploy: "false"`; pre-deploy validation and planning still run.
