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
      - uses: motherduckdb/motherduck-blueprints@v0.4.2
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
      - uses: motherduckdb/motherduck-blueprints@v0.4.2
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
| `python-version` | `3.11` | Python runtime installed by the action. |

Named inputs override matching flags in `args`. Existing workflows using only `args` continue to work. The action passes named inputs as literal argument values, including spaces and quotes.

Live commands read `MOTHERDUCK_TOKEN` from the step environment. Select the GitHub Environment on the **job**; the action's `target` input does not select a GitHub Environment for you.

The `stdout` output contains the command's text or JSON result. Assign an `id` to the step to read `steps.<id>.outputs.stdout`. Command failures fail the step.

Pin the action and your local CLI to the same release. See [upgrades](tooling-and-schema-versioning.md).
