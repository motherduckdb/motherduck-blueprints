# Working in this MotherDuck project

Read [README.md](README.md) first. This is a customer deployment repository, not the Blueprints tool's source code.

## Choose the right task

- New pipeline or dashboard: edit the Wikipedia starter or use `make new-project NAME`.
- Existing MotherDuck assets: follow [adopt existing resources](docs/adopt-existing-resources.md) before creating manifests.
- Package layout and command reference: [repository reference](docs/repository-reference.md).
- Field definitions and target overrides: [manifest reference](docs/blueprint-yml-reference.md).
- Product runtime APIs and limits: read the current `motherduck flight guide` or `motherduck dive guide`. Product guides do not override this repository's deployment policy.

## Files and tools

`motherduck.yml` selects packages using include globs. Each package has one `blueprint.yml` and its source files. Optional roots are created when needed: `flights/`, `dives/`, `guides/`, `roles/`, and `projects/`. A package directory must match its lowercase manifest slug. Source files must stay inside their package; do not move executable source into `shared/`.

`motherduck` is the product CLI: it can list and pull remote resources into files. `md-blueprints` validates and deploys this repository's manifests. CLI metadata JSON is not a Blueprints manifest and its IDs are not automatically adopted.

The GitHub workflows, `schemas/`, and `.dive-preview/` are support files. Do not edit them to add a package. Starter templates live in the installed CLI; there is no customer `templates/` directory to maintain. `examples/` is optional and does not deploy.

## Operating constraints

- Preserve existing files and live resource identities. Export into a fresh ignored directory first; pull commands overwrite local files.
- Never run `init --force` over a customer's existing repository to add Blueprints. Generate into a separate directory and integrate the needed files.
- Inventory the owner, ID, version, name, schedule, data dependencies, and access before adopting resources. Admin visibility is not proof of update permission.
- Use `md-blueprints import --all` or repeated `--resource KIND:UUID` selectors for a read-only proposal; `--write` creates validated packages with deployment disabled. Imports bind UUIDs and owners only in the selected stable target, and require CLI 0.4.3+. Existing paths and already-bound resources are never overwritten.
- A configured ID takes precedence over names and titles; missing/inaccessible bound IDs never create replacements. Unbound Flights still match by name, Dives by title, and Guides by topic/title. Confirm the plan's IDs against import.json. Owner guards are not ownership transfers.
- Keep existing schedules, config, secret names, mounts, aliases, Guide references, and access explicit during adoption. Omission can reset settings. Do not commit secret values.
- Imported Flights use manageSchedule: false to preserve the current schedule, including paused state, and runOnDeploy: false. Enable deploy only in the bound target after reviewing the baseline; audit external URLs and production writes before enabling preview.
- Exporting source does not copy databases, secret values, ownership, history, or grants. Do not create missing shares or change permissions without that being part of the requested work.
- Preview resource names must be branch-scoped. Flight schedules are disabled in preview, but source/config may still point at production data. Audit those references before enabling immediate runs.
- Do not use a production Guide ID in preview. Put an adopted ID under `targets.prod` only.
- New Guides are validation-only until `deploy: true`. Roles never deploy in preview. Organization Guides and role administration require an admin identity.
- Production selection expands downstream, not upstream. Deploy missing producers first or include them explicitly.
- `plan` checks live identity and dependencies; it is not a complete source/config diff and does not promise a no-op deployment.
- Deleting a manifest does not delete its production resource. Preview cleanup is a separate destructive operation.
- CI credentials belong in the selected GitHub Environment as `MOTHERDUCK_TOKEN`. Do not print tokens or commit local exports before checking source/config for embedded secrets.

## Validate and hand off

Use `md-blueprints verify --target prod --blueprints NAME` to check existing IDs before enabling deployment; bound imports are checked even while disabled. Deploy always runs preflight and checks live results afterward by default. A postcheck failure means deployment already ran, not that it rolled back. See the action guide for the explicit postcheck opt-out; preflight cannot be disabled.

Run `make validate`. For a changed Dive, run `make preview-smoke NAME`. Run a live plan only with the intended identity and target; report the exact resource IDs, any creates, and unresolved dependencies. Request deployment only after the import baseline and plan have been reviewed.

After adoption, use one writer for managed settings: the repository workflow. Pulling from MotherDuck is an explicit reconciliation step, not continuous two-way sync. Report whether changes are local, merged, deployed, or published; these are different outcomes.
