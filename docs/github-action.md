# Use the GitHub Action

The template includes short callers for versioned deployment, cleanup, and Doctor workflows maintained in the Blueprints repository. You do not need to write deployment jobs or maintain their third-party actions.

Keep event triggers and permissions in your repository. Configure targets and environments in `motherduck.yml`. The reusable jobs select those environments, so existing environment secrets and approval rules still apply. No `secrets: inherit` is needed. This follows [GitHub's reusable workflow environment handling](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows#using-inputs-and-secrets-in-a-reusable-workflow).

Use `make upgrade` to update the CLI and workflow references together. The referenced release supplies the deployment implementation, including preview comments, dependency selection, verification, and cleanup. The composite action remains available for custom jobs.

The reusable deployment workflow accepts `target`, `branch`, and `blueprints` for manual runs. It expects `motherduck.yml` at the repository root. For a different working directory or custom job steps, use the action directly.

## Customize the reusable workflows

Every reusable workflow accepts these optional inputs. Set them under `with:` in your caller workflow. The template callers list them as comments.

| Input | Default | Purpose |
| --- | --- | --- |
| `runs-on` | `ubuntu-latest` | Runner label, or a JSON array of labels such as `'["self-hosted", "linux"]'`. Self-hosted runners need `bash`, `git`, and `jq`. |
| `python-version` | `3.11` | Python used to install Blueprints. |
| `timeout-minutes` | `10` | Job timeout. Prepare Guide context only. |

The workflows also enforce a few rules:

- Manual `staging` or `prod` runs must start from the default branch. Run them from another branch and they fail before deploying.
- Dependabot pull requests are validated but do not deploy previews, because Dependabot runs receive no environment secrets. Preview cleanup skips Dependabot branches before it checks anything out. A pull request runs the workflow version from its own merge commit, so one opened before you upgraded can still start a cleanup run. It has nothing to clean up.
- Preview deploys and preview cleanup for the same branch share one concurrency group, so cleanup waits for a running deploy. A new preview deploy for the same branch, for example after reopening a PR, can still cancel a running cleanup. The next close cleans up again.

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
      - uses: motherduckdb/motherduck-blueprints@v0.7.6
```

The action installs its own Python dependencies. Validation is the default command and needs no token. Import, planning, verification, deployment, and cleanup read the job's environment token. Import also installs the tested MotherDuck CLI. See [CI and compatibility](motherduck-cli.md#ci-and-compatibility) for how commands reach MotherDuck.

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
      - uses: motherduckdb/motherduck-blueprints@v0.7.6
        env:
          MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}
        with:
          command: deploy
          target: prod
```

Run it from **Actions → Deploy Blueprints → Run workflow**. It deploys all enabled packages and checks the deployment plan before applying changes. To deploy a subset, add `blueprints: revenue`.

This minimal workflow runs only when you request it. For automatic PR previews, comments, and cleanup, use the template's existing workflows.

## Inputs

| Input | Default | Purpose |
| --- | --- | --- |
| `command` | `validate` | CLI command: `validate`, `plan`, `deploy`, `verify`, `cleanup`, `import`, `guides`, `doctor`, or `upgrade`. |
| `target` | Command default | `prod` for deploy/plan; `preview` for cleanup; validation checks every target. |
| `branch` | Empty | Required for preview deployment and cleanup. Pass the branch name directly; no extra quotes are needed. |
| `blueprints` | All packages | Comma-separated package names, such as `orders,revenue`. Dependencies expand according to the target. |
| `root` | Checkout directory | Project directory, such as `analytics`. Guides also supports plain SQL and dbt repositories. |
| `dbt` | Empty | dbt project directory or `dbt_project.yml`, relative to the checkout. Only for `command: guides`. |
| `args` | Empty | Advanced CLI flags, such as `--json`, `--offline`, or `--dry-run`. |
| `verify-after-deploy` | `true` | Read back live identities, declared shares/inputs, and Dive status after deploy. Set `"false"` only to opt out of the postcheck. |
| `python-version` | `3.11` | Python used to create the action's isolated environment. |

Named inputs override matching flags in `args`. Existing workflows using only `args` continue to work. The action passes named inputs as literal argument values, including spaces and quotes.

Live commands read `MOTHERDUCK_TOKEN` from the step environment. Select the GitHub Environment on the **job**; the action's `target` input does not select a GitHub Environment for you.

Output streams to the job log while the command runs, except for `guides`. The `stdout` output contains the command's text or JSON result, except for `guides`. Assign an `id` to the step to read `steps.<id>.outputs.stdout`. Every command also returns `stdout-file`, an absolute file path on the current runner. Guide context is file-only so its contents do not appear in logs or exceed GitHub job-output limits. Command failures fail the step.

The action installs Blueprints into its own virtual environment under the runner's temporary directory and puts only `md-blueprints` on `PATH`. It does not change the job's Python. If a later step needs to import `md_blueprints` or PyYAML, run it with the `python` output, for example `"${{ steps.blueprints.outputs.python }}" script.py`.

Pin the action and your local CLI to the same release. See [upgrades](tooling-and-schema-versioning.md).

## Prepare Guides in CI

Guide CI support requires Blueprints 0.7.0 or newer. New customer templates include **Prepare Guide context** under Actions. Run it manually with an optional dbt path, then download its `guide-context` artifact. It contains `guide-context.md`, with the agent instructions and discovered sources. It needs no MotherDuck token or model credentials and does not write Guide files.

For an existing repository, save this as `.github/workflows/guide-context.yaml`:

```yaml
name: Prepare Guide context
on: [pull_request, workflow_dispatch]
permissions:
  contents: read
jobs:
  context:
    uses: motherduckdb/motherduck-blueprints/.github/workflows/reusable_prepare_guide_context.yaml@v0.7.6
    with:
      root: .
      # dbt: analytics/dbt # Optional path inside the checkout.
```

This workflow prepares context. An LLM still needs to read the source and author the Guides. The reusable job uploads an artifact with seven-day retention. Download it in another job or outside CI, alongside a checkout of the same commit. Artifacts inherit repository access. File-only handling applies to the Blueprints preparation step; an agent runner may log prompts or tool results, so configure its logging for your data.

To integrate an existing agent in the same job, use the composite action:

```yaml
- uses: actions/checkout@v7
  with:
    persist-credentials: false
- uses: motherduckdb/motherduck-blueprints@v0.7.6
  id: context
  with:
    command: guides
    # dbt: analytics/dbt # Optional, paths with spaces are supported.
# Your existing agent step goes here. Give it the same checkout and pass
# steps.context.outputs.stdout-file through an environment variable.
# Instruct it to read that file and follow the Guide authoring workflow.
- uses: motherduckdb/motherduck-blueprints@v0.7.6
  with:
    command: validate
```

The agent runner and its authentication belong to the customer. Give a credentialed or write-capable agent only trusted branch runs, not untrusted fork content. Discovery itself can run with read-only permissions. Keep newly authored Guides private and disabled until publishing is explicitly enabled through the normal deployment workflow. `validate` checks manifests and references, not the factual correctness of the Markdown. A standalone dbt repository without `motherduck.yml` can use discovery but should skip Blueprints validation.

For other CI systems, the installed CLI needs no GitHub-specific environment:

```bash
md-blueprints guides --root . > guide-context.md
```

Save that file as a CI artifact or hand it to your configured agent. Add `--dbt /path/to/project` when needed. See [the Guide authoring instructions](guides-as-code.md) for the agent's task and evidence checks.

### Let Codex author a draft patch

For customers without an existing agent job, this optional example uses the [Codex GitHub Action](https://learn.chatgpt.com/docs/github-action). Add `OPENAI_API_KEY` as a repository secret. It runs only on manual dispatch, runs Codex last in its job, and checks the draft in a fresh job with no model credentials. No commit, PR, or deployment is created automatically.

Save this as `.github/workflows/draft-guides.yaml` in a Blueprints repository:

```yaml
name: Draft Guides
on: [workflow_dispatch]
permissions:
  contents: read
jobs:
  author:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    outputs:
      patch: ${{ steps.agent.outputs.final-message }}
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: motherduckdb/motherduck-blueprints@v0.7.6
        id: context
        with:
          command: guides
          # dbt: analytics/dbt
      - uses: openai/codex-action@86365089eb2b84e0a8fb0717b304f8bdcb13b20e # v1
        id: agent
        env:
          GUIDE_CONTEXT_FILE: ${{ steps.context.outputs.stdout-file }}
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          sandbox: workspace-write
          safety-strategy: drop-sudo
          prompt: |
            Read the file named by GUIDE_CONTEXT_FILE and follow its authoring instructions.
            Use the installed md-blueprints CLI directly. Do not install tools or log in.
            Create or update concise Markdown Guides under guides/ only, with new Guides
            private and deploy: false. Preserve existing knowledge and resource identities.
            Skip live database enrichment. Run md-blueprints validate.
            Do not commit, push, publish, or change other files.
            Return a git patch as your entire final message, without Markdown fences.
            Use git diff --binary -- guides for tracked files. For each new untracked Guide
            file, append git diff --no-index --binary -- /dev/null FILE (exit 1 means a diff).
            Do not write Git metadata. Include new files, not just changes to tracked files.
            If nothing changed, return an empty final message.
  check-draft:
    needs: author
    if: needs.author.outputs.patch != ''
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - name: Apply only Guide changes
        env:
          GUIDE_PATCH: ${{ needs.author.outputs.patch }}
        run: |
          printf '%s\n' "$GUIDE_PATCH" > "$RUNNER_TEMP/agent.patch"
          git apply --check --include='guides/**' "$RUNNER_TEMP/agent.patch"
          git apply --include='guides/**' "$RUNNER_TEMP/agent.patch"
          git add -N -- guides
          git diff --binary -- guides > "$RUNNER_TEMP/guide-updates.patch"
      - uses: motherduckdb/motherduck-blueprints@v0.7.6
        with:
          command: validate
      - uses: actions/upload-artifact@v7
        with:
          name: guide-updates
          path: ${{ runner.temp }}/guide-updates.patch
          retention-days: 7
```

The example intentionally scopes edits to `guides/` and suits small draft updates that fit GitHub's job-output limit. A malformed agent patch fails the check job. For larger updates or other package layouts, use your existing agent runner's artifact handoff. Apply the resulting patch through your normal repository workflow. The model-authenticated example requires customer configuration and is not exercised by Blueprints' token-free CI tests.

## Checks before and after deployment

Every `deploy` performs manifest validation, authorization preflights, and a fresh live plan before the first write. Missing bound IDs, owner mismatches, and duplicate update identities fail before any resource is changed. This check cannot be disabled.

By default, deployment then reads back resource identities and checks declared shares/inputs and intended Dive status. Newly created IDs are captured and compared too. Verification results appear in the Actions summary; a failed postcheck fails the job and reports that deployment already ran. No automatic rollback is attempted.

For a separate read-only check of existing resources, including disabled imported bindings, use:

```yaml
- uses: motherduckdb/motherduck-blueprints@v0.7.6
  env:
    MOTHERDUCK_TOKEN: ${{ secrets.MOTHERDUCK_TOKEN }}
  with:
    command: verify
    target: prod
    blueprints: YOUR_PACKAGE
```

Run this in the same GitHub Environment as the deployment job. Use `command: plan` instead for new resources that do not exist yet: `verify` requires existing identities. The CLI equivalent is `md-blueprints verify --target prod --blueprints YOUR_PACKAGE --json`.

These are lifecycle checks, not customer data tests: they do not execute arbitrary assertions, compare all source/configuration fields, or prove every external query permission. Flight run success still uses `waitForRun: success`. Customers with a separate verification stage can set `verify-after-deploy: "false"`; pre-deploy validation and planning still run.
