# NCS Field Recovery Explorer

The NCS Field Recovery Explorer is a complete project package that loads public Norwegian Continental Shelf data, publishes a share, and deploys an interactive Dive. It demonstrates when related resources belong together below `projects/` instead of in independently deployed typed packages.

The implementation lives in [`projects/ncs-field-recovery/`](../../projects/ncs-field-recovery/).

## What the project deploys

```text
projects/ncs-field-recovery/
  blueprint.yml
  guide.md
  src/
    flight.py
    requirements.txt
    dive.tsx
```

The manifest owns four resources:

- `loader`: an unscheduled Flight that loads official SODIR FactMaps data and runs on deploy.
- `data`: a share over the loaded database.
- `explorer`: a Dive that reads the share and compares official field recovery estimates.
- `field-recovery`: a validation-only Guide containing source, metric, and interpretation rules plus references to the Flight and Dive.

Because the resources share one lifecycle, preview and production selection treat them as one package. `waitForRun: success` also prevents the Dive from resolving its share until the ingestion run succeeds.

## Why this is a project package

Use `projects/` when changing one resource should preview, deploy, and roll back the complete set. The NCS example has that ownership boundary:

1. The Flight creates the tables and analytical view expected by the Dive.
2. The share publishes that database.
3. The Dive queries the shared view.
4. The Guide versions the definitions and operating context beside the implementation.

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

Opening a pull request runs the same selection through GitHub Actions. Preview database, share, Flight, and Dive names include the branch scope, and cleanup removes them after the branch closes. The production target uses stable names and runs through the protected `motherduck-production` environment.

## Reuse the pattern

Start a co-owned package with:

```bash
make new-project field-analytics
```

Then carry over the patterns that fit your project:

- Use target variables for stable production names and branch-scoped preview names.
- Set `runOnDeploy: true` when a deployment needs fresh data.
- Set `waitForRun: success` when downstream resources must wait for the Flight.
- Keep source-specific metric definitions and limitations in the package README.
- Keep agent-facing rules in `guide.md`; change `deploy` to `true` when the project should publish the Guide.
- Use an output and input instead of a project package when the producer and consumer need independent owners or release schedules.

See the [project README](../../projects/ncs-field-recovery/README.md) for source provenance, metric definitions, tables, and the transformation-only smoke path.
