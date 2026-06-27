# GitHub Setup

## 1. Create the Repository

For a customer-owned repo, prefer creating a new repository from the MotherDuck Blueprints template. See [customer-onboarding.md](customer-onboarding.md) for the full template-copy flow.

If you are pushing from a local copy manually, create an empty GitHub repository named `motherduck-blueprints`, then push this folder to it.

```bash
git init
git add .
git commit -m "Initial MotherDuck Blueprints repo"
git branch -M main
git remote add origin git@github.com:<owner>/motherduck-blueprints.git
git push -u origin main
```

## 2. Add MotherDuck Secret

In GitHub:

1. Open Settings.
2. Open Secrets and variables, then Actions.
3. Create a repository secret named `MOTHERDUCK_TOKEN`.
4. Paste a MotherDuck read/write token.

Use a service account token for shared repositories so deployed resources are owned by automation rather than by an individual user.

## 3. Add Production Environment Approval

In GitHub:

1. Open Settings.
2. Open Environments.
3. Create an environment named `motherduck-production`.
4. Add required reviewers.

Production blueprint deploys target this environment, so GitHub pauses deployment until an approved reviewer allows it.

## 4. Protect Main

In GitHub:

1. Open Settings.
2. Open Branches.
3. Add a branch protection rule for `main`.
4. Enable "Require a pull request before merging".
5. Enable required approvals.
6. Enable "Require review from Code Owners" after updating `.github/CODEOWNERS`.
7. Require status checks once the first workflow runs have created them.

The repo includes cleanup workflows for preview blueprints. Keep those workflows enabled so PR previews do not linger after branches are closed or deleted.

Pull requests validate even when `MOTHERDUCK_TOKEN` is not configured. Preview deployment is skipped in that case; add the secret when you want PRs to create live MotherDuck previews.

## 5. Add Assets

Add every deployable asset inside a blueprint package:

```text
blueprints/<name>/blueprint.yml
blueprints/<name>/src/...
```

Use lowercase slug names for blueprint packages. No workflow filter registration is needed: the deploy workflow computes changed blueprints from `motherduck.yml` includes and `blueprints/<name>/**` paths.

For a new project, start with:

```bash
make new-blueprint <blueprint-name>
```

The generated package is intentionally small but deployable: it creates starter metrics, publishes a share, and renders a Dive that reads the share.

Before opening a PR, run:

```bash
make validate
make mock-test
make preview-smoke <blueprint-name>
```

Skip `make preview-smoke` only when the changed blueprint has no Dive.
