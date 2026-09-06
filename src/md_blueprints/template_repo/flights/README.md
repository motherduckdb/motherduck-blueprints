# Flights

Use one package per independently managed pipeline. Its `blueprint.yml` points at Python source and a requirements file; both stay inside the package. `make new-flight NAME` creates the directory when needed.

For an existing Flight, [export and review its baseline](../docs/adopt-existing-resources.md) first. Use the importer to bind its UUID and owner. Unbound manifests still match the exact remote name; bound manifests can rename the original object. Preview schedules are disabled, but imported source may still write to production; do not enable `runOnDeploy` before auditing source and config.
