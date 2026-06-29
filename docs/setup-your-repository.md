# Set Up Your Repository

This repository is a reusable MotherDuck Blueprints template. Copy it into your GitHub organization, connect it to MotherDuck with a service account token, then customize or add blueprint packages under `blueprints/`.

Blueprints are project-level packages. Each package should represent one logical project or data product, not an entire organization, service account, user, or database owner. Do not create top-level `dives/`, `flights/`, or `bundles/` directories in your repo.

## 1. Copy the Template Repo

Create your repository from the template.

Recommended GitHub flow once `motherduckdb/motherduck-blueprints` is public:

1. Open the template repository.
2. Click "Use this template".
3. Select your GitHub organization.
4. Name the new repository, for example `motherduck-blueprints`.
5. Create the repository as private unless you want it public.

CLI alternative:

```bash
gh repo create <your-org>/motherduck-blueprints --private --template motherduckdb/motherduck-blueprints
git clone git@github.com:<your-org>/motherduck-blueprints.git
cd motherduck-blueprints
```

If GitHub template mode is not enabled yet, copy by clone and push:

```bash
git clone git@github.com:motherduckdb/motherduck-blueprints.git motherduck-blueprints
cd motherduck-blueprints
git remote remove origin
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
make validate
make mock-test
make example-smoke
```

`make validate` checks manifests and rendered targets. `make mock-test` shadows `duckdb` with a fake CLI and exercises planning, preview deploy, production deploy, cleanup dry-runs, cleanup, and failed-run reporting without contacting MotherDuck. `make example-smoke` creates, validates, builds, and destroys a generated starter blueprint in a temporary copy of the repo.

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
./tools/md_blueprints cleanup --dry-run --target preview --branch test/wikipedia-blueprint
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

When you change repository commands, resource behavior, target policies, or package layout, update the matching docs in the same pull request and add an entry to `CHANGELOG.md`.
