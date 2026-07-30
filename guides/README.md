# Guides

Place version-controlled Guides below this root. Guides default to validation-only for backward compatibility; set `deploy: true` to create and version them in MotherDuck.

Use `access: user` for the deployment identity or `access: organization` for organization-wide access. Organization Guides require an admin deployment identity. References may point at catalog objects, Dives, Flights, or other Guides.

Create a package with:

```bash
make new-guide revenue-metrics
```

The generated package keeps `deploy: false` until its content is ready to publish. When enabling deployment, add a branch-scoped preview title or topic:

```yaml
resources:
  guides:
    guide:
      title: Revenue metrics
      topic: finance/revenue
      source: guide.md
      access: organization
      deploy: true
      targets:
        preview:
          title: Revenue metrics:${target.branch} (Preview)
          access: user
```

Read [Manage Guides as code](../docs/guides-as-code.md) for the complete workflow and [blueprint.yml Reference](../docs/blueprint-yml-reference.md#guides) for all Guide and reference fields.
