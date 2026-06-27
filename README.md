# MotherDuck Blueprints

A lightweight template for shipping MotherDuck Flights, Dives, shares, and future context assets from GitHub.

Use this repo when you want:

- version-controlled MotherDuck projects
- preview deployments on pull requests
- production deployments from `main`
- one clear place to keep each data product's code and metadata

## Start Your Repo

1. Copy this repository into your GitHub organization.
2. Add a GitHub Actions secret named `MOTHERDUCK_TOKEN`.
3. Create a GitHub Environment named `motherduck-production`.
4. Run the local checks:

```bash
make validate
make mock-test
```

5. Open a small pull request and confirm the preview deployment comment appears.

Use a MotherDuck service account token so deployed resources are owned by automation rather than by one person's account.

See [Set Up Your Repository](docs/setup-your-repository.md) for the full setup flow and [GitHub Setup](docs/github-setup.md) for the short GitHub checklist.

## Add a Blueprint

A blueprint is one logical project or data product. Keep its manifest, Flight, Dive, and README together:

```text
blueprints/<blueprint-name>/
  blueprint.yml
  README.md
  src/
    flight.py
    requirements.txt
    dive.tsx
```

Start with the scaffold:

```bash
make new-blueprint revenue-overview
make validate
make preview-smoke revenue-overview
```

Then replace the starter Flight and Dive with your real project logic.

## Best Practices to Copy

- Keep one project or data product per `blueprints/<name>/` package.
- Use lowercase slug names such as `account-360` or `revenue-ops`.
- Keep preview resources branch-scoped and production resources stable.
- Deploy from CI with a service account token.
- Store secrets in GitHub Actions, never in the repo.
- Update [CHANGELOG.md](CHANGELOG.md) in every pull request.

## Examples

The included [Wikipedia Pageviews blueprint](blueprints/wikipedia-pageviews/README.md) shows a Flight that loads public data, publishes a share, and deploys a Dive that reads that share.

For a new project, the generated starter blueprint is usually the best first example because it is small, deployable, and easy to replace.

## More Detail

- [Set Up Your Repository](docs/setup-your-repository.md): copy this template into your repo.
- [GitHub Setup](docs/github-setup.md): configure secrets, environments, and branch protection.
- [Repository Reference](docs/repository-reference.md): layout, targets, local commands, CI/CD, and context-layer notes.
- [blueprint.yml Reference](docs/blueprint-yml-reference.md): complete field reference for blueprint manifests.
