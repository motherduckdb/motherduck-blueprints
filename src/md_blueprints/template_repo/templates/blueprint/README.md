# __BLUEPRINT_NAME__ Blueprint

This generated blueprint is a complete `projects/` starter. It deploys a Flight that writes sample daily metrics, exports the database share as the `data` output, deploys a Dive that reads it through the `__DATABASE_NAME__` alias, and versions project guidance beside the resources it documents.

## Resources

- Flight: `loader`
- Share: `data`
- Dive: `dashboard`
- Guide: `project-guide` (validation-only until `deploy: true`)

The Dive deploys as `draft` in pull-request previews and `ready` in production. Change the production status to `endorsed` only when an organization admin has approved it as a trusted source of truth; use `archived` to retire it without deleting its URL and history.

The production target writes to the stable `__DATABASE_NAME__` database and share. The preview target writes to `__DATABASE_NAME___preview_${target.branch_slug}`, disables schedules, runs once on deploy, and cleans up the preview share and database when the branch closes.

## Replace the Starter Logic

- Update `src/flight.py` with your real load or transformation code.
- Update `src/dive.tsx` with the queries and UI for your data product.
- Update `guide.md` with the definitions and operating context agents need.
- Keep `blueprint.yml` as the resource manifest that connects the Flight, share, Dive, and Guide.

## Local Checks

```bash
make validate
make render-preview __BLUEPRINT_NAME__
make preview-smoke __BLUEPRINT_NAME__
md-blueprints doctor
```
