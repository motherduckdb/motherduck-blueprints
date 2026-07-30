# Set Up Your Repository

Use `md-blueprints init` to generate a typed MotherDuck Blueprints repository, connect it to MotherDuck with a service account token, then customize or add independently deployable packages.

Use `flights/`, `dives/`, `guides/`, and `roles/` when those resources have different owners or lifecycles. Use `projects/` when several resource types genuinely ship, preview, and roll back together. Existing `blueprints/` packages remain supported.

## 1. Generate the Repository

Install the released CLI and generate the customer file set:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "md-blueprints @ git+https://github.com/motherduckdb/motherduck-blueprints.git@v0"
.venv/bin/md-blueprints init motherduck-blueprints
cd motherduck-blueprints
```

Create a GitHub repository and push the generated files:

```bash
git init
git add .
git commit -m "Initial MotherDuck Blueprints repo"
gh repo create <your-org>/motherduck-blueprints --private --source . --remote origin --push
```

## 2. Create a MotherDuck Service Account Token

In your MotherDuck organization:

1. Create a service account for CI deployments.
2. Grant it the minimum database privileges needed by the blueprints. Use the `admin` preset role when the repository manages custom roles or organization-wide Guides.
3. Generate a read/write token.
4. Store the token somewhere secure long enough to add it to GitHub.

Use a service account token rather than a personal token so deployed Dives, Flights, tables, and shares are owned by a shared automation identity.

## 3. Add GitHub Secrets

In your repository:

1. Open Settings.
2. Open Secrets and variables, then Actions.
3. Add a repository secret named `MOTHERDUCK_TOKEN`.
4. Paste the MotherDuck service account token.

Do not commit tokens to the repository.

## 4. Configure Deployment Approvals

Create a GitHub Environment named `motherduck-production`.

Recommended settings:

- Add required reviewers.
- Restrict who can approve production deployments if needed.
- Keep the environment name exactly `motherduck-production`, because production jobs reference it.

## 5. Protect `main`

Add branch protection for `main`.

Recommended settings:

- Require a pull request before merging.
- Require approvals.
- Require review from Code Owners after `.github/CODEOWNERS` is updated.
- Require the relevant workflow checks after the first PR has run them.

## 6. Run Local Validation

Before touching MotherDuck, run:

```bash
make setup
make validate
make preview-smoke wikipedia-pageviews
```

`make validate` checks manifests and rendered targets. `make preview-smoke` builds a selected Dive locally without contacting MotherDuck.

If you keep a Dive in the repo, also run a finite local preview build:

```bash
make preview-smoke <blueprint-name>
```

PR validation still runs if `MOTHERDUCK_TOKEN` has not been added yet, but live preview deployment is skipped until the secret exists.

## 7. Run a Preview PR

Create a branch and make a small change, for example edit the Wikipedia Dive docs or metadata.

```bash
git checkout -b test/wikipedia-blueprint
git commit --allow-empty -m "Test Wikipedia blueprint preview"
git push -u origin test/wikipedia-blueprint
gh pr create --fill
```

Expected preview flow:

1. `Deploy Blueprints` validates manifests.
2. Directly changed packages are discovered from `motherduck.yml`, then the preview selection expands upstream and downstream.
3. The workflow runs a read-only preview plan.
4. Preview Flights deploy with schedules disabled.
5. Preview Flights run when `runOnDeploy` is true.
6. Preview databases and shares are created with the branch slug.
7. Dives deploy after required shares are resolvable.
8. Preview Dives are enforced as `draft`.
9. Opt-in preview Guides deploy after their references resolve.
10. A PR comment lists the plan plus preview Flight, share, Dive, and Guide details.

## 8. Verify Cleanup

Close the PR or delete the branch.

Expected cleanup flow:

1. Preview Guides are deleted.
2. Preview Dives are deleted.
3. Preview Flights are deleted.
4. Preview shares are dropped.
5. Preview databases are dropped when `dropDatabase: true`.

Cleanup refuses to drop share/database names that do not include the branch slug.

You can preview cleanup locally before closing a PR:

```bash
md-blueprints cleanup --dry-run --target preview --branch test/wikipedia-blueprint
```

## 9. Deploy to Production

Merge the PR to `main`.

Expected production flow:

1. `Deploy Blueprints` runs on `main`.
2. GitHub waits for approval in `motherduck-production`.
3. The workflow writes a read-only production plan to the GitHub job summary.
4. Production roles and memberships reconcile.
5. Production Flights deploy.
6. Flights run when `runOnDeploy` is true.
7. Required shares, filters, and grants reconcile.
8. Production Dives deploy and reconcile explicitly declared governance statuses.
9. Production Guides deploy after their references resolve.

The generated examples use `ready` in production and `draft` in preview. Omitting production `status` preserves the live value. Endorsing a Dive requires an organization-admin deployment identity.

## 10. Customize the Blueprints

You can then:

- Scaffold a producer with `make new-flight events-ingest` and consume it with `make new-dive events-dashboard INPUT=events-ingest.data`.
- Scaffold a complete co-owned package with `make new-project revenue-overview`.
- Connect same-repository packages through `outputs` and `inputs`; use literal share URLs for external repositories.
- Replace the bundled Wikipedia and NCS public-data examples with your own packages.
- Add target `deployment.tokenEnvVar` and `deployment.identity` metadata in `motherduck.yml` if preview and production use different service account secrets.
- Publish versioned Guide assets below `guides/` with `resources.guides` and `deploy: true`; follow [Manage Guides as code](guides-as-code.md) for preview naming, access, and references.
- Manage custom roles below `roles/` with `resources.roles`; use `mode: authoritative` only when the repository owns the complete membership set.
- Update `.github/CODEOWNERS`.

## 11. Keep Tooling in Sync

After repository creation, treat the versioned `md-blueprints` repository tags as the long-term upgrade surface. The generated files are the starting point, while the CLI source and action carry schema validation, deployment behavior, and migrations.

The generated `Makefile` pins the CLI version in `CLI_VERSION` and installs it from the matching Git tag, so local installs stay aligned with the release that generated the repository. Install and validate with:

```bash
make setup
make validate
```

Use `make install-deploy` before live local plan/deploy/cleanup commands. It installs the deploy extra, which includes the DuckDB Python runtime dependencies needed for MotherDuck connections:

```bash
make install-deploy
```

To upgrade, bump `CLI_VERSION` in `Makefile`. Change the action tag in `.github/workflows/` when adopting a new major release; the floating major tag receives compatible minor and patch updates automatically.

The action tag is the preferred CI path for customer repositories.

When using the repository action, pin the action major version in customer workflows:

```yaml
- uses: motherduckdb/motherduck-blueprints@v0
  with:
    command: validate
```

Before adopting a new schema version, run:

```bash
md-blueprints doctor
md-blueprints migrate --to latest
```

Review migration output before applying it with `--write`.

When you change repository commands, resource behavior, target policies, or package layout, update the matching docs in the same pull request.
