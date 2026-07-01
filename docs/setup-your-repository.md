# Set Up Your Repository

Use `md-blueprints init` to generate a MotherDuck Blueprints repository, connect it to MotherDuck with a service account token, then customize or add blueprint packages under `blueprints/`.

Blueprints are project-level packages. Each package should represent one logical project or data product, not an entire organization, service account, user, or database owner. Do not create top-level `dives/`, `flights/`, or `bundles/` directories in your repo.

## 1. Generate the Repository

Install the released CLI and generate the customer file set:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "md-blueprints==0.3.0"
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
2. Grant it the minimum database privileges needed by the blueprints.
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

Create a branch in your repo and make a small change, for example edit the Wikipedia blueprint docs or metadata.

```bash
git checkout -b test/wikipedia-blueprint
git commit --allow-empty -m "Test Wikipedia blueprint preview"
git push -u origin test/wikipedia-blueprint
gh pr create --fill
```

Expected preview flow:

1. `Deploy Blueprints` validates manifests.
2. The changed blueprint packages are discovered from `motherduck.yml`.
3. The workflow runs a read-only preview plan.
4. Preview Flights deploy with schedules disabled.
5. Preview Flights run when `runOnDeploy` is true.
6. Preview databases and shares are created with the branch slug.
7. Dives deploy after required shares are resolvable.
8. A PR comment lists the plan plus preview Flight, share, and Dive links.

## 8. Verify Cleanup

Close the PR or delete the branch.

Expected cleanup flow:

1. Preview Dives are deleted.
2. Preview Flights are deleted.
3. Preview shares are dropped.
4. Preview databases are dropped when `dropDatabase: true`.

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
4. Production Flights deploy.
5. Flights run when `runOnDeploy` is true.
6. Required shares are resolved.
7. Production Dives deploy.

## 10. Customize the Blueprints

You can then:

- Scaffold a starter package with `make new-blueprint <blueprint-name>`. The generated Flight creates daily metric tables and a share, and the generated Dive reads that share.
- Replace the Wikipedia example with your own blueprint package.
- Add standalone Dives or Flights as one-resource blueprints.
- Add paired Flight + Dive packages that declare shared data products in `resources.shares`.
- Add target `deployment.tokenEnvVar` and `deployment.identity` metadata in `motherduck.yml` if preview and production use different service account secrets.
- Version context-layer assets under `context/` or package-local `resources.context` entries with `deploy: false`.
- Update `.github/CODEOWNERS`.

## 11. Keep Tooling in Sync

After repository creation, treat `md-blueprints` as the long-term upgrade surface. The generated files are the starting point, while the package and action carry schema validation, deployment behavior, and migrations.

Pin the package locally or in CI:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "md-blueprints==0.3.0"
.venv/bin/md-blueprints validate
```

Use the deploy extra for live local plan/deploy/cleanup commands. It includes the DuckDB Python runtime dependencies needed for MotherDuck connections:

```bash
.venv/bin/python -m pip install "md-blueprints[deploy]==0.3.0"
```

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
