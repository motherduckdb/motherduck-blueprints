# NCS Field Recovery Explorer

The NCS Field Recovery Explorer is a complete project package that loads public Norwegian Continental Shelf data, publishes a share, and deploys an interactive Dive. It demonstrates when related resources belong together below `projects/` instead of in independently deployed typed packages.

The optional implementation lives in [`examples/ncs-field-recovery/`](../../examples/ncs-field-recovery/). It is not discovered or deployed by default.

## Enable the example

From your repository root, copy it into the active projects directory, then validate:

```bash
mkdir -p projects
cp -R examples/ncs-field-recovery projects/ncs-field-recovery
make validate
```

If `projects/ncs-field-recovery` already exists, use that copy instead of overwriting it.

## What the project deploys

```text
projects/ncs-field-recovery/
  blueprint.yml
  src/
    flight.py
    requirements.txt
    dive.tsx
```

The manifest owns three resources:

- `loader`: an unscheduled Flight that loads official SODIR FactMaps data and runs on deploy.
- `data`: a share over the loaded database.
- `explorer`: a Dive that reads the share and compares official field recovery estimates.

Because the resources share one lifecycle, preview and production selection treat them as one package. `waitForRun: success` also prevents the Dive from resolving its share until the ingestion run succeeds.

## Why this is a project package

Use `projects/` when changing one resource should preview, deploy, and roll back the complete set. The NCS example has that ownership boundary:

1. The Flight creates the tables and analytical view expected by the Dive.
2. The share publishes that database.
3. The Dive queries the shared view.

The split [Wikipedia Pageviews example](wikipedia-pageviews.md) shows the alternative: a Flight producer and Dive consumer with independent lifecycles connected through an output and input.

## Validate the example

Run the repository checks without contacting MotherDuck:

```bash
make validate
make mock-test
make example-smoke
```

Build the local Dive preview without starting a development server:

```bash
make preview-smoke ncs-field-recovery
```

## Deploy a branch-scoped preview

With `MOTHERDUCK_TOKEN` configured, inspect the live plan before deployment:

```bash
make install-deploy
.venv/bin/md-blueprints plan \
  --target preview \
  --branch feature/ncs-review \
  --blueprints ncs-field-recovery
```

Opening a pull request runs the same selection through GitHub Actions. Preview database, share, Flight, and Dive names include the branch scope, and cleanup removes them after the branch closes. Without staging, merging deploys the stable production target. With staging, merging deploys the `_staging` share through `motherduck-staging`, and a published release deploys the unsuffixed production share through `motherduck-production`. Both accounts may use the `ncs_field_recovery` database name.

## Reuse the pattern

Start a co-owned package with:

```bash
make new-project field-analytics
```

Then carry over the patterns that fit your project:

- Use target overrides for distinct staging/production share names and branch-scoped preview names.
- Set `runOnDeploy: true` when a deployment needs fresh data.
- Set `waitForRun: success` when downstream resources must wait for the Flight.
- Keep source-specific metric definitions and limitations in the package README.
- Use an output and input instead of a project package when the producer and consumer need independent owners or release schedules.

See the [project README](../../examples/ncs-field-recovery/README.md) for source provenance, metric definitions, tables, and the transformation-only smoke path.
