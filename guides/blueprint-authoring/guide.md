# Blueprint Authoring Guide

## Choose the package boundary

- Use `flights/`, `dives/`, or `guides/` when the resource has its own owner and deployment lifecycle.
- Use `projects/` when a Flight, share, Dive, and Guide must preview and roll back together.
- Connect independently deployed packages with named `outputs` and `inputs`.

## Before opening a pull request

1. Run `make validate`.
2. Run `make preview-smoke <blueprint-name>` for packages containing a Dive.
3. Inspect a live plan before deployment when a MotherDuck token is configured.

Never commit MotherDuck tokens or other credentials. Keep Guide content limited to trusted context that every intended reader may access.
