# Maintaining Blueprints

This page is for maintainers of the tooling repository. It is not copied into customer repositories. Customer-facing upgrade and schema policy lives in [tooling and schema versioning](docs/tooling-and-schema-versioning.md).

## Customer-facing docs

Root docs, examples, schemas, and preview files are shipped to generated repositories through `src/md_blueprints/asset-map.json`. When you add a customer-facing doc, add it to the map. Maintainer-only pages such as this one stay out of the map, and shipped docs must not link to them or to `src/`, `tests/`, or `scripts/`.

## Release Engineering

Stable `vMAJOR.MINOR.PATCH` tag pushes run the release workflow. The workflow trigger excludes floating tags such as `v0`, requires the tagged commit to be on `main`, and rejects other release-tag shapes:

1. Verify tag, `pyproject.toml`, and `src/md_blueprints/__init__.py` versions match.
2. Build the wheel and source distribution.
3. Smoke test the installed wheel as an internal packaging check.
4. Smoke test the local action wrapper.
5. Generate a reproducible CycloneDX SBOM and attest every release artifact.
6. Verify the generated-template repository and protected release environments.
7. Install the built wheel, generate the customer template with an exact action tag, and validate it before pushing to `motherduckdb/blueprints-template`.
8. Require the generated repository's triggered workflow to pass against that exact action tag.
9. Attach the distributions and SBOM to the GitHub Release, then update the compatibility-only floating major alias.

A patch for an older release line publishes its tags and releases but leaves the template's `main`, the floating major tag, and the "Latest" release on the highest version. Step 8 runs only when the template's `main` moves.

The action installs the tagged checkout directly, generated repositories install local tooling from the matching Git tag, and built Python distributions are attached to the GitHub Release. The floating major tag remains available for compatibility but generated repositories do not depend on it.

Marketplace listing is configured through GitHub's release UI. Any required GitHub Marketplace agreement must be accepted by an authorized organization maintainer. The automated release workflow publishes the repository release and action tags without relying on PyPI.

One-time template setup: create `motherduckdb/blueprints-template`, mark it as a GitHub template repository, and add a `BLUEPRINTS_TEMPLATE_PUSH_TOKEN` secret that can push to that repository. Tagged releases fail before publishing when this setup is missing; the template push is part of the release contract, not an optional best-effort step.

Before creating a release tag:

```bash
make release-check TAG=vX.Y.Z
make release-external-check
make validate
make mock-test
make package-smoke
make example-smoke
make preview-smoke wikipedia-pageviews
```

## Repository Boundary

This repository now carries the customer template as package data and exposes it through:

```bash
md-blueprints init <dir>
```

That command writes the customer file set and stamps the same exact release into the generated `Makefile` and workflows.

The generated customer template is already separate from the tooling:

- Tooling repository (`motherduckdb/motherduck-blueprints`): `src/md_blueprints/`, `pyproject.toml`, the action wrapper, tests, scripts, CI, the release workflow, and the changelog.
- Template repository (`motherduckdb/blueprints-template`): `motherduck.yml`, the active Flight and Dive starter, optional examples, `AGENTS.md`, customer docs, a thin Makefile, customer workflows, schemas, preview support, Dependabot, CODEOWNERS, and `.gitignore`. Optional roots are created by scaffolding. Internal scaffolds stay in the tooling package.

The release workflow generates `motherduckdb/blueprints-template` from the built wheel's `md-blueprints init` package data so the stamped action tag, docs, examples, and CLI behavior cannot drift. The tooling repository's own deploy and doctor workflows use the local action checkout; generated customer workflows use the stamped immutable release tag.

## Agent Maintenance Map

| Task | Files |
| --- | --- |
| CLI parsing and exit codes | `src/md_blueprints/cli.py` |
| Customer template generation | `src/md_blueprints/init.py`, `src/md_blueprints/template_repo/` |
| Schema loading and validation | `src/md_blueprints/schema.py`, `schemas/v*/` |
| Template rendering | `src/md_blueprints/template.py` |
| Project manifest and changed detection | `src/md_blueprints/project.py` |
| Plan/deploy/cleanup behavior | `src/md_blueprints/deploy.py` |
| Migration behavior | `src/md_blueprints/migrations.py` |
| Doctor/update checks | `src/md_blueprints/maintenance.py` |
| Distribution asset assembly | `src/md_blueprints/asset-map.json`, `src/build_support.py` |
| Local compatibility wrapper (deprecated) | `tools/md_blueprints` |
| GitHub Action wrapper | `action.yml` |
| Internal CI | `.github/workflows/ci.yaml` |
| Release automation | `.github/workflows/release.yaml`, `scripts/package-smoke-test.sh`, `scripts/check-release-version.sh` |
| Customer setup docs | `README.md`, `docs/setup-your-repository.md` |
| Field reference | `docs/blueprint-yml-reference.md` |
| Change record | `CHANGELOG.md` |
