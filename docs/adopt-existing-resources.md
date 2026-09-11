# Import existing MotherDuck resources

The importer reads existing Flights, Dives, and Guides, creates UUID-bound packages, and preserves their source and deployment settings. It never changes remote resources. Every imported package starts with deployment disabled.

## 1. Use the current tooling and intended identity

Import and UUID-bound Flight/Dive updates require Blueprints 0.4.3 or newer. Keep your Makefile and action pins aligned; use `make upgrade VERSION=0.6.0` when upgrading an existing generated repository.

Run `make install-deploy` to install the supported MotherDuck CLI, which bundles its DuckDB runtime. Open a new terminal if `motherduck` is not on your PATH. Run `motherduck login` and `motherduck status` for local read-only export, or provide the selected target's token through your secret manager. For example, `--target prod` reads the token configured by `targets.prod.deployment.tokenEnvVar`, normally `MOTHERDUCK_TOKEN`. Import from the account where the existing resources live; a new service account is not an ownership transfer.

If adding Blueprints to an existing code repository, generate support files in a separate directory and integrate them deliberately. Do not use `init --force` over customer work.

## 2. Preview the import

From the repository root:

```bash
.venv/bin/md-blueprints import --all --target prod
```

This is a dry run. It fetches all three catalogs visible to that identity, follows pagination to the end, reads exact source versions, and validates the proposed packages in a temporary directory. The output is an inventory of IDs, owners, versions, package paths, and warnings; it does not print source code or configuration values.

For selected objects, repeat `--resource`:

```bash
.venv/bin/md-blueprints import --target prod \
  --resource flight:FLIGHT_UUID \
  --resource dive:DIVE_UUID \
  --resource guide:GUIDE_UUID
```

Replace the UUID placeholders. Choose either `--all` or explicit selectors. Preview is not an import target; use prod or a configured staging target.

“All” means the objects returned by the account's permission-scoped APIs, not every object in the organization. If an object is excluded from catalog discovery, select its UUID explicitly. Unknown owners, unsupported source shapes, inconsistent versions, repeated pagination IDs, and invalid mounts fail the batch rather than silently dropping information.

## 3. Write the reviewed packages

Export every visible Flight, Dive, and Guide into disabled packages with:

```bash
make export
```

Use `make export TARGET=staging` for an existing staging target. This runs the same reviewed importer through `motherduck query --file ... --output json`. The equivalent CLI command is below. For selected UUIDs, repeat your earlier `--resource` selection with `--write`:

```bash
.venv/bin/md-blueprints import --all --target prod --write
```

The command reads a fresh baseline, validates every proposal before writing, and creates packages such as `flights/imported-flight-<uuid>-prod/`. UUID-based package names are stable even if remote names change.

Each package contains:

- `blueprint.yml`: source paths and settings, with UUID/owner bound only to the selected target.
- Source files: `main.py` and `requirements.txt`, `index.tsx`, or `guide.md`.
- `import.json`: original identity/version, source hashes, state, and review warnings.
- `README.md`: activation instructions.

All deployment flags are false, including preview. There are no automatic Flight runs. Source files and config can contain hard-coded credentials even though the importer never fetches secret values: inspect them before committing.

The root's `requiredCliVersion` is raised to at least 0.4.3 so an older action cannot ignore the identity bindings. Existing compatible constraints are preserved; conflicting constraints fail. Update tooling pins before CI validation. A manifest change can select other existing packages in your deployment workflow, so review the complete plan.

Existing paths are never overwritten. Re-importing an already-bound UUID reports `already_managed` and keeps customer edits; it is not a source refresh. Local write failures remove only the new packages created by that attempt.

## 4. Check identity and settings before enabling deployment

| Resource | What is preserved | Deployment behavior |
| --- | --- | --- |
| Flight | UUID, owner, name, source, requirements, config, secret names, runtime-token name, timeout, cron | Updates the UUID, even after a rename. Requires the Flight creator's identity. Missing/inaccessible IDs never fall back to creation. |
| Dive | UUID, owner, title, description, source, mount URLs and aliases | Updates the UUID; production status is left unchanged unless you explicitly declare a desired status. A local mount export is generated from the authoritative version metadata. |
| Guide | UUID, owner, title/topic, description, content, access, references | Updates the UUID. Reference UUIDs are retained and resolved directly, not through a name search. Organization access still requires an admin deployment identity. |

Imported Flights use `manageSchedule: false`. Their live schedule, including paused state, is left untouched during updates. The exported cron remains in the manifest for review. Set `manageSchedule: true` only when you explicitly want repository deployments to apply that cron; do not accidentally reactivate an existing paused schedule.

Database/share URLs and Guide reference UUIDs remain external dependencies. The importer does not infer a producer from a SQL string, create shares, copy data, or rebuild grants. Preserve mount aliases. Before enabling preview, audit production URLs, hard-coded writes, secrets, and reference UUIDs and make the intended isolation explicit.

You can verify bound identities before enabling deployment with `.venv/bin/md-blueprints verify --target prod --blueprints PACKAGE --json`. This is read-only and includes imported IDs even when their deployment flags are false.

For each package you intend to adopt, set `deploy: true` only inside its selected stable-target override, retaining `id` and `owner`. Leave the base and preview flags false. Then run:

```bash
make validate
.venv/bin/md-blueprints plan --target prod --blueprints PACKAGE --json
```

For a Dive also run `make preview-smoke PACKAGE`. Compare planned IDs against `import.json`. Missing IDs, owner changes, unexpected creates, or insufficient permissions are blockers. Do not delete the ID to bypass them.

Automated deployment validates IDs before writing and verifies live identities afterward by default; failures make the CD job fail. See [action verification](github-action.md#checks-before-and-after-deployment).

Planning is read-only. It verifies identity and dependencies, not every source/configuration difference; compare local files with the exported baseline before the first deploy. Updates may create new versions. Once ready, review and merge the change through your normal deployment workflow.

## CLI, MCP, and offline snapshots

The importer uses the documented read-only SQL APIs through the MotherDuck CLI. `make export` requires that CLI. Other Blueprints live commands prefer it when installed and retain the Python DuckDB backend for older installations. CI import selects the native CLI. Other CI live operations use the Python runtime.

The native `list` and `pull` commands are useful for individual assets, but there is no native bulk-export command. Their local metadata does not include every adoption guard, such as owner identity and paused schedule state. Blueprints reads authoritative metadata and exact source versions through `motherduck query`, then creates the disabled packages without requiring you to reconcile separate metadata files. See the [CLI workflow and command map](motherduck-cli.md).

Local import can use the CLI's saved login only for the default token variable outside CI. A custom target token variable must be supplied explicitly. Deployment, planning, verification, cleanup, and CI always require the selected target's token.

The product CLI remains useful for inspection: `motherduck flight pull UUID --dir PATH`, `motherduck dive pull UUID --dir PATH`, and `motherduck guide pull UUID --dir PATH`. Pull overwrites local files, so use a fresh ignored `.imports/` directory. MCP alternatives are `get_flight`, `read_dive`, and `get_guide`.

For disconnected preparation or tests, use `--snapshot PATH` instead of catalog selection. The file is a JSON array of `{kind, metadata, content}` objects:

- Flight: metadata from `MD_GET_FLIGHT`, content from `MD_GET_FLIGHT_VERSION`.
- Dive: metadata from `MD_GET_DIVE`, content from `MD_GET_DIVE_VERSION`, including required_resources and api_version.
- Guide: metadata and content from `MD_GET_GUIDE`.

This is the importer snapshot contract, not arbitrary product CLI metadata JSON or an MCP text transcript. Identity and version fields must agree. Offline snapshots cannot verify the current owner or permissions; the bound deployment plan does that before mutation.

## Limits

- There is no ownership transfer, full history migration, automatic source refresh, or two-way sync. Seeing another person's Flight does not grant permission to update it.
- Missing or inaccessible bound objects produce errors, never replacement objects. To redeploy under a new identity, make that an explicit new-resource decision with new IDs and a separate cutover.
- Import does not fetch secret values, database contents, or access grants, and does not automatically redirect references to preview objects.
- Source/API shapes that cannot be represented without loss are rejected. Dive API version 1 and static REQUIRED_DATABASES arrays are supported, including JavaScript comments, single quotes, unquoted keys, trailing commas, and `as const`. Expressions and function calls are rejected without evaluation.
- A resource changing while it is read causes a retryable error. The batch is not a transaction across the remote account; re-check the baseline before deployment.
- Disabled imports do not deploy or clean up remote objects. Removing their files does not delete production resources.

## API references

Contracts checked against the official docs on 2026-09-06:
[Flight read](https://motherduck.com/docs/sql-reference/motherduck-sql-reference/flights/md-get-flight/),
[Flight version](https://motherduck.com/docs/sql-reference/motherduck-sql-reference/flights/md-get-flight-version/),
[Dive read](https://motherduck.com/docs/sql-reference/motherduck-sql-reference/dives/md-get-dive/),
[Dive version](https://motherduck.com/docs/sql-reference/motherduck-sql-reference/dives/md-get-dive-version/),
[Guide read](https://motherduck.com/docs/sql-reference/motherduck-sql-reference/guides/md-get-guide/).
