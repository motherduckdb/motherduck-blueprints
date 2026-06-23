# GitHub Setup

## 1. Create the Repository

Create an empty GitHub repository named `motherduck-blueprints`, then push this folder to it.

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

Use a service account token for shared repositories.

## 3. Add Production Environment Approval

In GitHub:

1. Open Settings.
2. Open Environments.
3. Create an environment named `motherduck-production`.
4. Add required reviewers.

The production Dives and Flights jobs target this environment, so GitHub will pause deployment until an approved reviewer allows it.

## 4. Protect Main

In GitHub:

1. Open Settings.
2. Open Branches.
3. Add a branch protection rule for `main`.
4. Enable "Require a pull request before merging".
5. Enable required approvals.
6. Enable "Require review from Code Owners" after updating `.github/CODEOWNERS`.
7. Require status checks once the first workflow runs have created them.

The repo includes cleanup workflows for preview Dives, Flights, and Bundles. Keep those workflows enabled so PR previews do not linger after branches are closed or deleted.

## 5. Register Assets

The workflows intentionally use explicit filters. Add every deployable asset to the correct workflow:

```yaml
filters: |
  revenue-overview: dives/revenue-overview/**
```

```yaml
filters: |
  daily-refresh: flights/daily-refresh/**
```
