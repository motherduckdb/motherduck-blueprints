# Wikipedia Pageviews Blueprint

This blueprint deploys a MotherDuck Flight that loads public Wikimedia pageview data, publishes a branch- or production-scoped share, and then deploys a Dive that reads that share.

## Resources

- Flight: `pageviews_loader`
- Share: `pageviews`
- Dive: `pageviews`

The production target writes to the stable `wikipedia_pageviews` database and share. The preview target writes to `wikipedia_pageviews_preview_${target.branch_slug}`, disables the schedule, runs once, and cleans up the preview share and database when the branch closes.

## Local Preview

```bash
make setup
make preview wikipedia-pageviews
```

For a finite build check without starting the dev server:

```bash
make preview-smoke wikipedia-pageviews
```

## Validation

```bash
make validate
make mock-test
make example-smoke
./tools/md_blueprints render --target preview --branch feature/example --blueprints wikipedia-pageviews
```
