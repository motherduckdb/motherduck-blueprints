# Context Layer

This directory is reserved for MotherDuck context-layer assets once the deployment interface is available.

Until then, use it to review and version proposed context files, for example:

- `schemas/` - entity, metric, and relationship definitions.
- `policies/` - governance, safety, or access notes.
- `README.md` files beside concrete assets explaining ownership and review expectations.

When MotherDuck exposes the deploy/update SQL functions or API for the context layer, add:

- `scripts/deploy-context.sh`
- `.github/workflows/deploy_context.yaml`
- a registration or discovery convention that mirrors the Dives and Flights workflows.

