# GitHub Setup

## 1. Create the Repository

Prefer generating your repository with `md-blueprints init`. See [setup-your-repository.md](setup-your-repository.md) for the full generation and push flow.

If you are pushing from a local copy manually, create an empty GitHub repository named `motherduck-blueprints`, then push this folder to it.

```bash
git init
git add .
git commit -m "Initial MotherDuck Blueprints repo"
git branch -M main
git remote add origin git@github.com:<your-org>/motherduck-blueprints.git
git push -u origin main
```

## 2. Add MotherDuck Secret

In GitHub:

1. Open Settings.
2. Open Secrets and variables, then Actions.
3. Create a repository secret named `MOTHERDUCK_TOKEN`.
4. Paste a MotherDuck read/write token.

Use a service account token so deployed resources are owned by automation rather than by an individual user.

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

The repo includes cleanup workflows for preview blueprints. On pull-request close, cleanup checks both the branch and base manifests so resources introduced or removed by the branch are covered. Keep those workflows enabled so PR previews do not linger after branches are closed or deleted.

Pull requests validate even when `MOTHERDUCK_TOKEN` is not configured. Preview deployment is skipped in that case; add the secret when you want PRs to create live MotherDuck previews.

If a target uses a different service account secret, set `targets.<target>.deployment.tokenEnvVar` in `motherduck.yml` and expose that env var in your workflow. The default remains `MOTHERDUCK_TOKEN`.

## 5. Add Assets

Add every deployable asset inside a typed or project package:

```text
flights/<name>/blueprint.yml
dives/<name>/blueprint.yml
guides/<name>/blueprint.yml
roles/<name>/blueprint.yml
projects/<name>/blueprint.yml
```

Use lowercase slug names. No per-package workflow registration is needed: the deploy workflow computes direct changes from `motherduck.yml`, then expands dependencies according to the target.

For a new project, start with:

```bash
make new-project <blueprint-name>
```

For separately owned resources, use `make new-flight`, `make new-dive`, `make new-guide`, and `make new-role` instead.

Before opening a PR, run:

```bash
make setup
make validate
make preview-smoke <blueprint-name>
```

Skip `make preview-smoke` only when the changed blueprint has no Dive.
For docs-only changes, keep the relevant README or `docs/` page in sync with any behavior you describe.

Live workflows run `md-blueprints plan` before deploy. You can run the same check locally with a MotherDuck token:

```bash
md-blueprints plan --target preview --branch feature/example --blueprints <blueprint-name>
```

Pin the exact CLI and action release together when maintaining a customer repository over time. See [Tooling and Schema Versioning](tooling-and-schema-versioning.md) for upgrade and migration guidance.
