# Guides

Place version-controlled Guides below this root. Guides default to validation-only for backward compatibility; set `deploy: true` to create and version them in MotherDuck.

[`blueprint-authoring/`](blueprint-authoring/) is a complete validation-only example. Use this root when a Guide has its own owner or lifecycle; colocate it in `projects/<name>/` when it must change and roll back with that project's other resources.

Use `access: user` for the deployment identity or `access: organization` for organization-wide access. Organization Guides require an admin deployment identity. References may point at catalog objects, Dives, Flights, or other Guides.

Create a package with:

```bash
make new-guide revenue-metrics
```

The generated package keeps `deploy: false` until its content is ready to publish and includes a branch-scoped preview title. Enabling deployment only requires changing `deploy` to `true`; customize access, topic, and references as needed:

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
