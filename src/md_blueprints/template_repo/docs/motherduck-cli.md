# Work with the MotherDuck CLI

Use the native CLI to inspect an account or work on an individual resource. Use Blueprints to export resources into a managed repository and deploy the repository's targets together.

## Export an existing account into code

From your Blueprints repository:

```bash
make install-deploy
motherduck login
motherduck status
make export
make validate
```

Open a new terminal after installation if the `motherduck` command is not on your PATH. For automation, supply `MOTHERDUCK_TOKEN` through your secret manager instead of logging in.

`make export` reads every visible Flight, Dive, and Guide, follows all catalog pages, and writes disabled packages. It preserves IDs, owners, exact source versions, settings, and references. Existing packages are kept. Use `make export TARGET=staging` for a configured staging target. See [adoption](adopt-existing-resources.md) for a dry run and the review required before activation.

“All” covers these three resource types visible to the identity. It does not copy database contents, secret values, shares, roles, or grants. This is a code export, not an account backup or ownership transfer.

## Inspect one resource

```bash
motherduck flight list --all --output json
motherduck dive list --all --output json
motherduck guide list --all --output json
```

Each list defaults to one page of 100 results. Use `--limit` and `--offset` to page manually. `--all` broadens visibility, but does not remove pagination.

Pull a selected UUID into a fresh directory under the ignored `.imports/` directory:

```bash
motherduck flight pull FLIGHT_UUID --dir .imports/flight --output json
motherduck dive pull DIVE_UUID --dir .imports/dive --output json
motherduck guide pull GUIDE_UUID --dir .imports/guide --output json
```

Pull overwrites local files. Use `--version` to select a version. The native metadata files are useful for local authoring but omit adoption information such as owner identity and paused schedule state. Blueprints exports through `motherduck query` to retain that information.

## Command map

Checked against the installed `v1.5.5-2026-09-35` help on 2026-09-09. Run `motherduck <group> <command> --help` for current flags and examples.

| Area | Commands | Use |
| --- | --- | --- |
| Authentication | `login`, `logout`, `status` | Browser or headless sign-in, removing saved credentials, checking identity. |
| Account setup | `new`, `new claim` | Create an account or claim an unclaimed organization. Existing-account export does not need these. |
| SQL | `query` | SQL text or `--file`, with table, JSON, or CSV output and a query timeout. |
| Installation | `upgrade` | Update the local native CLI. |
| Dive authoring | `dive guide`, `dive init`, `dive watch` | Read the runtime guide, scaffold locally, and preview with reload. |
| Dive operations | `dive list`, `dive list-versions`, `dive pull`, `dive push`, `dive delete` | Inspect, fetch, publish a new version, or delete a Dive. |
| Flight authoring | `flight guide`, `flight init` | Read the runtime guide and scaffold locally. |
| Flight operations | `flight list`, `flight list-versions`, `flight pull`, `flight push`, `flight delete` | Inspect, fetch, publish, or delete a Flight. |
| Flight runs | `flight run`, `flight cancel`, `flight list-runs`, `flight logs` | Start, cancel, inspect, and diagnose runs. |
| Flight secrets | `flight create-secret`, `flight list-secrets`, `flight delete-secret` | Manage runtime secrets. Listing exposes names and structure, not values. |
| Guides | `guide init`, `guide list`, `guide list-versions`, `guide pull`, `guide push`, `guide delete` | Work with Markdown guidance, access settings, and object references. |

Read `dive guide` or `flight guide` before authoring source. `init` writes local files. `push`, run controls, deletes, and secret changes mutate MotherDuck. After adopting a package, make managed changes through its repository workflow so its identity checks and target policies apply.

## CI and compatibility

The Blueprints action uses the native CLI for import. Deployment, planning, verification, and cleanup use the Python runtime to avoid starting a CLI process for each SQL call. The repository CI also tests the real CLI's local commands without credentials. Blueprints supplies SQL through private temporary files and decodes `query --output json`, which emits one JSON array per result-producing statement and no array for DDL. Blueprints consumes every result and rejects malformed output. Resource commands use a `success` envelope instead. Failed or malformed responses fail the operation, with no retry through another backend.

Environment tokens stay in the process environment. CI uses an isolated `MOTHERDUCK_HOME` under the runner's temporary directory. All CI live operations require the target token. Local import alone can use a saved CLI login when the target uses the default token variable.

Local Blueprints commands automatically prefer the native CLI when available. The existing Python runtime remains a compatibility fallback when it is absent. Set `MD_BLUEPRINTS_SQL_BACKEND=duckdb` to select that backend explicitly after installing `md-blueprints[deploy]`. CI import and `make export` explicitly select the native CLI. Other CI live operations select the Python backend.

The native version is managed inside the Blueprints release. `make install-deploy` installs that tested version. `motherduck upgrade` can update your local installation independently.

See the official [CLI overview](https://motherduck.com/docs/getting-started/interfaces/motherduck-cli/), [installation guide](https://motherduck.com/docs/getting-started/interfaces/motherduck-cli/install/), and [command reference](https://motherduck.com/docs/sql-reference/motherduck-cli/).
