# Context Layer

This directory is reserved for shared MotherDuck context-layer assets. Context files can be reviewed and versioned here today, but deployment must remain disabled.

Until then, use it to review and version proposed context files, for example:

- `schemas/` - entity, metric, and relationship definitions.
- `policies/` - governance, safety, or access notes.
- `README.md` files beside concrete assets explaining ownership and review expectations.

Until deployment is supported, package-local `resources.context` entries must use `deploy: false`.
Document ownership, review expectations, and intended consumers beside concrete context assets. Update `docs/blueprint-yml-reference.md` and `docs/repository-reference.md` if context resource behavior changes.

When MotherDuck exposes the deploy/update SQL functions or API for the context layer, add:

- `resources.context` deployment support in the `md-blueprints` package
- schema conventions in `schemas/`
- target behavior in `motherduck.yml`
