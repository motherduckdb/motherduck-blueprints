# Customer Onboarding

This repository is intended to act as a reusable MotherDuck Blueprints template. Customers copy it into their own GitHub organization, connect it to their MotherDuck organization with a service account token, and then customize or add their own Dives, Flights, Bundles, and future context assets.

## 1. Copy the Template Repo

Create a customer-owned repository from the template.

Recommended GitHub flow once `motherduckdb/motherduck-blueprints` is public:

1. Open the template repository.
2. Click "Use this template".
3. Select the customer's GitHub organization.
4. Name the new repository, for example `motherduck-blueprints`.
5. Create the repository as private unless the customer explicitly wants it public.

CLI alternative:

```bash
gh repo create <customer-org>/motherduck-blueprints --private --template motherduckdb/motherduck-blueprints
git clone git@github.com:<customer-org>/motherduck-blueprints.git
cd motherduck-blueprints
```

If GitHub template mode is not enabled yet, copy by clone and push:

```bash
git clone git@github.com:motherduckdb/motherduck-blueprints.git motherduck-blueprints
cd motherduck-blueprints
git remote remove origin
gh repo create <customer-org>/motherduck-blueprints --private --source . --remote origin --push
```

## 2. Create a MotherDuck Service Account Token

In the customer's MotherDuck organization:

1. Create a service account for CI deployments.
2. Generate a read/write token.
3. Store the token somewhere secure long enough to add it to GitHub.

Use a service account token rather than a personal token so deployed Dives, Flights, tables, and shares are owned by a shared automation identity.

## 3. Add GitHub Secrets

In the customer repository:

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

## 6. Run the Local Mock Test

Before touching MotherDuck, run:

```bash
make mock-test
```

This shadows `duckdb` with a local fake CLI and exercises the Wikipedia bundle preview deploy, production deploy, and cleanup paths without contacting MotherDuck.

## 7. Run a Preview PR

Create a branch in the customer repo and make a small change, for example edit the Wikipedia bundle docs or metadata.

```bash
git checkout -b test/wikipedia-blueprint
git commit --allow-empty -m "Test Wikipedia blueprint preview"
git push -u origin test/wikipedia-blueprint
gh pr create --fill
```

Expected preview flow:

1. `Deploy Bundles` validates the bundle.
2. The preview Flight is deployed with schedules disabled.
3. The preview Flight runs once if `preview.runOnDeploy` is true.
4. The preview database and share are created with the branch slug.
5. The preview Dive is deployed after the preview share is available.
6. A PR comment lists the preview Flight, share, and Dive links.

## 8. Verify Cleanup

Close the PR or delete the branch.

Expected cleanup flow:

1. Preview Dive is deleted.
2. Preview Flight is deleted.
3. Preview share is dropped.
4. Preview database is dropped when `cleanupDatabase` is true.

## 9. Deploy to Production

Merge the PR to `main`.

Expected production flow:

1. `Deploy Bundles` runs on `main`.
2. GitHub waits for approval in `motherduck-production`.
3. The production Flight deploys.
4. The Flight runs if `runOnDeploy` is true.
5. The production share is updated.
6. The production Dive deploys after the share is available.

## 10. Customize the Blueprints

Customers can then:

- Replace the Wikipedia example with their own Bundle.
- Add standalone Dives or Flights and register them in the standalone workflows.
- Add new Bundles and register them in `.github/workflows/deploy_bundles.yaml`.
- Update `.github/CODEOWNERS`.
- Add context-layer assets under `context/` once the deployment surface exists.

