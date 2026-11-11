# Documentation index

Find the page for a task or an error. Each page stands on its own; start with the row that matches what you are doing.

## By task

| I want to | Read |
| --- | --- |
| Deploy the first preview and production | [Set up your first deployment](setup-your-repository.md) |
| Fix a failed or stuck workflow run | [If something does not work](setup-your-repository.md#if-something-does-not-work) |
| Look up a `blueprint.yml` field, default, or target override | [blueprint.yml reference](blueprint-yml-reference.md) |
| Understand package layout, the dependency graph, targets, and local commands | [Repository reference](repository-reference.md) |
| Bring existing Flights, Dives, and Guides under version control | [Import existing MotherDuck resources](adopt-existing-resources.md) |
| Stop deploying a package and delete what it created | [Retire a package](repository-reference.md#retire-a-package) |
| Separate preview and production credentials | [Add staging](setup-your-repository.md#add-staging-optional) |
| Use the action or the reusable workflows, and change runners or timeouts | [Use the GitHub Action](github-action.md) |
| Write or update Guides with an agent | [Create and update Guides with your agent](guides-as-code.md) |
| Use the `motherduck` CLI next to Blueprints | [Work with the MotherDuck CLI](motherduck-cli.md) |
| Manage accounts, tokens, roles, or shares with Terraform | [Use Blueprints with the MotherDuck Terraform provider](use-with-terraform.md) |
| Upgrade the tooling or migrate a schema version | [Tooling and schema versioning](tooling-and-schema-versioning.md) |
| See what an upgrade changes | [Breaking changes](breaking-changes.md) |
| Start from a working package for ingestion, transformation, monitoring, or Guides | [Examples](examples/README.md) |
| See how previews, production, and staging relate | [CI/CD](repository-reference.md#cicd) |

## By error or symptom

| What you see | Read |
| --- | --- |
| An error that ends with `see docs/breaking-changes.md#<entry>` | That entry in [breaking changes](breaking-changes.md). It gives the symptom, how to find affected files, and the fix. |
| `Unknown field ... Did you mean ...` or a field that is rejected for one target | [blueprint.yml reference](blueprint-yml-reference.md), then [rendering](blueprint-yml-reference.md#rendering) for target overrides |
| `MOTHERDUCK_TOKEN is required` or a rejected token | [If something does not work](setup-your-repository.md#if-something-does-not-work) |
| `Plan contains errors` for a share or input that is missing | [Inputs, outputs, and deployment graph](repository-reference.md#inputs-outputs-and-deployment-graph) |
| `configured ... id is missing or inaccessible`, or an owner mismatch | [Check identity and settings](adopt-existing-resources.md#4-check-identity-and-settings-before-enabling-deployment) |
| `RBAC preflight failed` | [Roles](blueprint-yml-reference.md#roles) |
| `refusing to delete preview ...` during cleanup | [Targets and safety](repository-reference.md#targets-and-safety) |
| A production deploy failed, was rejected, or stays queued | [CI/CD](repository-reference.md#cicd) |
| A removed package's Flight still runs | [Retire a package](repository-reference.md#retire-a-package) |

## For agents

Read `AGENTS.md` at the repository root first. It lists the constraints that `validate`, `plan`, and `deploy` enforce and the order to work in. Then:

1. Run `make validate` after every manifest or source edit. It needs no token and reports the file, resource, and target of each problem.
2. For a field, read its section in the [blueprint.yml reference](blueprint-yml-reference.md) before editing. Defaults and target-override rules are stated per resource type.
3. For a changed Dive, run `make preview-smoke NAME`.
4. Before writing a new Flight, Dive, or Guide, read the closest [example](examples/README.md) and reuse its patterns.
5. Run live commands (`plan`, `deploy`, `verify`, `cleanup`) only with the token of the intended target, and report the resource IDs the plan shows.

Errors name the next step after `Next:`. Follow it before trying another approach.
