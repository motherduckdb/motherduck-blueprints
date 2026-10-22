# Flights

Use one package per independently managed pipeline. Its `blueprint.yml` points at Python source and a requirements file; both stay inside the package. `make new-flight NAME` creates the directory when needed. The starter source opens only its own database with `md:<database>?attach_mode=single`, which starts faster than attaching the whole workspace, and falls back to `md:` on the first run, before the database exists. A Flight that reads another database attaches it with `ATTACH 'md:<name>'`.

For an existing Flight, [export and review its baseline](../docs/adopt-existing-resources.md) first. Use the importer to bind its UUID and owner. Unbound manifests still match the exact remote name; bound manifests can rename the original object. Preview schedules are disabled, but imported source may still write to production; do not enable `runOnDeploy` before auditing source and config.
