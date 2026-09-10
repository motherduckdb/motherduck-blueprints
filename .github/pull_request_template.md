## What changed?

- [ ] Dives
- [ ] Flights
- [ ] Shares
- [ ] Context layer
- [ ] CI or scripts
- [ ] Docs only

## Deployment notes

- [ ] For adopted resources, planned IDs and settings match the exported baseline; no unintentional creates or ownership changes.

- [ ] New or renamed assets are declared in a typed-root or `projects/<name>/blueprint.yml` package.
- [ ] Dives list required resources in `blueprint.yml`.
- [ ] Dive statuses are intentional: previews are `draft`, and `endorsed` production changes have an organization-admin reviewer.
- [ ] Preview shares/databases that can be cleaned up include `${target.branch_slug}`.
- [ ] If `staging` is configured, staging shares have names distinct from production while database names may intentionally match.
- [ ] Deployment tokens are GitHub Environment secrets named `MOTHERDUCK_TOKEN`, not repository-level secrets or tracked values.
- [ ] Blueprints validate with `make validate`.
- [ ] Dives build with `make preview-smoke <blueprint-name>` when changed.
- [ ] Package/action/schema docs are updated when tooling behavior changed.
- [ ] Shared assets are declared in the asset map, and package smoke checks pass when asset ownership changes.
- [ ] Generated workflow jobs are current (`make sync-workflows`) when reusable providers change.
- [ ] Release version checks pass when package metadata changed.
- [ ] Docs are updated when layout, commands, target behavior, or resource semantics changed.
- [ ] `CHANGELOG.md` is updated.
- [ ] Production deploy has an owner/reviewer; staged repositories promote production only from a published release.
