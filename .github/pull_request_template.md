## What changed?

- [ ] Dives
- [ ] Flights
- [ ] Shares
- [ ] Context layer
- [ ] CI or scripts
- [ ] Docs only

## Deployment notes

- [ ] New or renamed assets are declared in `blueprints/<name>/blueprint.yml`.
- [ ] Dives list required resources in `blueprint.yml`.
- [ ] Preview shares/databases that can be cleaned up include `${target.branch_slug}`.
- [ ] Blueprints validate with `make validate`.
- [ ] Dives build with `make preview-smoke <blueprint-name>` when changed.
- [ ] Package/action/schema docs are updated when tooling behavior changed.
- [ ] Release version checks pass when package metadata changed.
- [ ] Docs are updated when layout, commands, target behavior, or resource semantics changed.
- [ ] `CHANGELOG.md` is updated.
- [ ] Production deploy has an owner/reviewer.
