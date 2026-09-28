# Use Blueprints with the MotherDuck Terraform provider

Many teams manage their MotherDuck platform with the [MotherDuck Terraform provider](https://github.com/motherduckdb/terraform-provider-motherduck) and their pipelines, dashboards, and Guides with Blueprints. The two tools work well together when every object has exactly one owner.

The provider documents the same split from its side in [Deploy pipelines and dashboards with Blueprints](https://github.com/motherduckdb/terraform-provider-motherduck/blob/main/docs/guides/blueprints-deployment.md).

## Choose one owner for every object

| Object | Recommended owner | Terraform resources |
| --- | --- | --- |
| Service accounts and access tokens | Terraform | `motherduck_service_account`, `motherduck_access_token` |
| Compute settings | Terraform | `motherduck_duckling_config` |
| Shared platform databases, secrets, and custom roles | Terraform | `motherduck_database`, `motherduck_secret`, `motherduck_role`, `motherduck_role_grant` |
| Platform shares and their grants | Terraform | `motherduck_share`, `motherduck_share_grant` |
| Flight code, Dive content, Guide content | Blueprints | Do not also use `motherduck_flight`, `motherduck_dive`, or `motherduck_guide` for the same object |
| Databases and shares created by a package's Flight | Blueprints | Do not also declare them in Terraform |
| Branch-scoped preview resources | Blueprints only | Never manage previews with Terraform |

Blueprints finds Flights, Dives, and Guides by name or title when a manifest has no `id`. If Terraform already manages an object with the same name, both tools update it and overwrite each other's changes. On staging and production targets, `plan` notes every name match. Bind adopted objects with `id` and `owner`, as described in [adopt existing resources](adopt-existing-resources.md).

## Supply the deployment token from Terraform

Blueprints reads the service-account token from the GitHub Environment named by each target in `motherduck.yml`. Terraform can create the service account and its token, then write the token into that environment:

```hcl
resource "motherduck_service_account" "blueprints_prod" {
  username = "svc_acme_blueprints_prod"
}

resource "motherduck_access_token" "blueprints_prod" {
  username   = motherduck_service_account.blueprints_prod.username
  name       = "blueprints-deploy"
  token_type = "read_write"
  ttl        = 7776000 # 90 days
}

# integrations/github provider
resource "github_repository_environment" "prod" {
  repository  = "acme-analytics"
  environment = "motherduck-production" # must match targets.prod.environment
}

resource "github_actions_environment_secret" "motherduck_token" {
  repository  = github_repository_environment.prod.repository
  environment = github_repository_environment.prod.environment
  secret_name = "MOTHERDUCK_TOKEN"
  value       = motherduck_access_token.blueprints_prod.token
}
```

- The token is stored in Terraform state. Use an encrypted, access-controlled backend.
- Changing `ttl` replaces the token. The GitHub secret updates in the same apply.
- Older GitHub provider versions name the argument `plaintext_value`.
- Repeat the pattern for a staging environment if you [add staging](setup-your-repository.md#add-staging-optional).

Blueprints needs an admin identity only when it deploys custom roles or organization-wide Guides. If Terraform owns roles, keep the Blueprints service account non-admin. Otherwise grant the preset role explicitly:

```hcl
resource "motherduck_role_grant" "blueprints_admin" {
  role_name    = "admin"
  grantee_name = motherduck_service_account.blueprints_prod.username
}
```

## Use Terraform-owned data from a package

**A share owned by the deployment account.** Declare it without `includePattern` or `grants`, and turn off cleanup. Blueprints then checks that the share exists and never changes it:

```yaml
resources:
  shares:
    orders:
      name: acme_orders_curated # created by motherduck_share
      database: orders
      cleanup: false
  dives:
    orders:
      title: Orders
      source: src/dive.tsx
      requiredResources:
        - share: orders
          alias: orders
```

**A share owned by another account.** Mount it by URL. Use a target variable so each environment can point to its own share:

```yaml
# motherduck.yml
targets:
  prod:
    variables:
      orders_share_url: md:_share/orders/...
```

```yaml
# blueprint.yml
requiredResources:
  - url: ${var.orders_share_url}
    alias: orders
```

Share URLs are committed to Git in this form. The provider marks `motherduck_share.url` as sensitive because unrestricted share URLs grant access. Mount only organization or restricted shares by URL, and keep unrestricted share URLs out of the repository.

**Terraform-owned roles, secrets, and tokens.** Reference them by name. Share `grants.roles` can name a role that only Terraform declares. A Flight's `secrets` can list `motherduck_secret` names, and `accessTokenName` can name a `motherduck_access_token`. Put Terraform database names in a Flight's `config`.

## Avoid fights between the tools

- Do not use `mode: authoritative` on a Blueprints role or share `grants` when Terraform also grants it. Authoritative mode revokes every undeclared grant, including grants from `motherduck_role_grant` and `motherduck_share_grant`. Terraform then re-adds them on its next apply. The default `additive` mode leaves them alone. `md-blueprints doctor` warns about authoritative mode.
- Do not set `includePattern` on a share that `motherduck_share.include_pattern` manages.
- Do not declare the same role in both tools. Blueprints runs `CREATE ROLE IF NOT EXISTS`, so it would recreate a role Terraform destroyed.
- Use `dropDatabase: true` only for preview databases the package's Flight creates. Never point it at a Terraform database.
- Apply Terraform first, then open the Blueprints pull request. A package whose prerequisites are missing fails during `plan`, before any writes.

## Move Flights, Dives, or Guides from Terraform to Blueprints

1. Export the objects into disabled, ID-bound packages with `make export`, or select them with `md-blueprints import`. See [adopt existing resources](adopt-existing-resources.md).
2. Remove them from Terraform without destroying them. On Terraform 1.7 or later, use a `removed` block with `lifecycle { destroy = false }`. See the provider's [resource scope and migration guide](https://github.com/motherduckdb/terraform-provider-motherduck/blob/main/docs/guides/resource-scope.md).
3. Confirm the next `terraform plan` proposes neither deletion nor recreation.
4. Run `.venv/bin/md-blueprints verify --target prod`, then set `deploy: true` in a reviewed pull request.

Moving objects the other way works the same: set `deploy: false` in Blueprints first, then `terraform import` the object by ID.
