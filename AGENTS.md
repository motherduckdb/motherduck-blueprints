# Agent Guide

This repository contains the versioned MotherDuck Blueprints for Dives, Flights, and future context-layer assets.

## Token Handling

Never invent, print, or commit MotherDuck tokens. Local Dives preview uses `.dive-preview/.env`, which is ignored by Git. CI uses the `MOTHERDUCK_TOKEN` repository secret. Shared repositories should use a MotherDuck service account token so deployments are not tied to a personal account.

## Dives

Each Dive lives in `dives/<dive-name>/` and contains:

- `<dive-name>.tsx` - React component with a default export.
- `dive_metadata.json` - title, description, and required MotherDuck resources.

The `title` in metadata is the stable production matching key. If `PREVIEW_BRANCH` is set, `scripts/deploy-dive.sh` deploys the Dive as `<Title>:<branch> (Preview)`.

Keep `export const REQUIRED_DATABASES = ...` on one line in Dive source when using it for local preview. The deploy script strips that export and passes `requiredResources` from metadata to MotherDuck. A required resource can use `url` for a known `md:_share/...` URL or `shareName` when CI should resolve a generated share URL from `MD_LIST_DATABASE_SHARES()`. For PR previews, use `previewUrl` or `previewShareName` to point preview Dives at branch-scoped resources.

Register every deployable Dive in `.github/workflows/deploy_dives.yaml`.

## Flights

Each Flight lives in `flights/<flight-name>/` and contains:

- `flight.py` - Python source code for the Flight.
- `flight_metadata.json` - name, schedule, access token name, secret names, and string config.
- `requirements.txt` - Python dependencies sent with the Flight.

The `name` in metadata is the stable production matching key. Pull requests validate changed Flights; production deploys happen only from `main` through the `motherduck-production` GitHub Environment.

Use `"runOnDeploy": true` when a Flight should be started once immediately after deployment. Use `.preview.enabled: true` only for Flights that are safe to run from pull requests; preview Flights run without schedules and should write to branch-scoped preview databases/shares.

Register every deployable Flight in `.github/workflows/deploy_flights.yaml`.

## Bundles

Bundles live in `bundles/<bundle-name>/blueprint.json`. Use a bundle when one or more Flights must run before one or more Dives deploy. Bundle deployment runs Flights first, waits for declared shares, then deploys Dives. Preview bundle cleanup should delete preview Dives before preview Flights so data resources are dropped last.

Register every deployable bundle in `.github/workflows/deploy_bundles.yaml`. Do not also register its component Flight or Dive in the standalone workflows unless you intentionally want independent deployments.

## Context

Use `context/` for versioning proposed context-layer files until MotherDuck exposes a deployable API. Keep files structured and documented so a future workflow can treat this directory as the canonical Blueprint set.
