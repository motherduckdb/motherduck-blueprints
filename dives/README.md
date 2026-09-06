# Dives

Use one package per independently managed dashboard. Its manifest declares the source file and the database/share mounts, including aliases. `make new-dive NAME INPUT=producer.output` creates a package backed by another repository package; `URL=<share-url>` uses an external share.

For an existing Dive, [export and review it](../docs/adopt-existing-resources.md) before adding a manifest. Bind the UUID with the importer and compare the planned identity; unbound definitions still match by exact title. CLI metadata is not read by Blueprints. Omit production status to preserve the current value; preview Dives use draft.
