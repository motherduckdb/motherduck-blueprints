# __BLUEPRINT_NAME__ Blueprint

This generated blueprint is a complete starter project. It deploys a Flight that writes sample daily metrics, publishes the database as a share, and deploys a Dive that reads that share through the `__DATABASE_NAME__` alias.

## Resources

- Flight: `loader`
- Share: `data`
- Dive: `dashboard`

The production target writes to the stable `__DATABASE_NAME__` database and share. The preview target writes to `__DATABASE_NAME___preview_${target.branch_slug}`, disables schedules, runs once on deploy, and cleans up the preview share and database when the branch closes.

## Replace the Starter Logic

- Update `src/flight.py` with your real load or transformation code.
- Update `src/dive.tsx` with the queries and UI for your data product.
- Keep `blueprint.yml` as the resource manifest that connects the Flight, share, and Dive.

## Local Checks

```bash
make validate
make render-preview __BLUEPRINT_NAME__
make preview-smoke __BLUEPRINT_NAME__
```
