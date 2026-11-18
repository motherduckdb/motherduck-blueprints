## Highlights

- `make install-deploy` installs the MotherDuck CLI on macOS when Python comes from python.org. Blueprints now checks the certificates of its own HTTPS requests against the `certifi` bundle. [#175](https://github.com/motherduckdb/motherduck-blueprints/pull/175)
- The Terraform guide covers the provider's `motherduck_dive_grant` and `motherduck_flight_grant` resources and states which tool should own each grant. [#174](https://github.com/motherduckdb/motherduck-blueprints/pull/174)

## Upgrading from v0.10.5

v0.10.6 is a patch release. Manifests, deployed resources, and the pinned MotherDuck CLI are unchanged. Generated repositories pin exact versions, so the upgrade must name this version explicitly. Workflows that reference the floating `@v0` tag receive the release automatically. The local Dive preview is unchanged, so `make sync-preview` is not required.

1. Run `make upgrade VERSION=0.10.6`. The next `make` target installs the new tooling, including its new `certifi` dependency.
2. On a network that inspects TLS with its own certificate authority, set `SSL_CERT_FILE` to a PEM bundle that contains that authority.
3. Run `make validate`. Then open a pull request and review the preview plan before merging.

Changes to review:

- [HTTPS requests no longer use the system certificate store](#compatibility)

## Bug Fixes

- `make install-deploy` no longer fails with `CERTIFICATE_VERIFY_FAILED` on macOS when Python was installed from python.org. Those Python builds have no certificate store until `Install Certificates.command` runs, so the CLI installer download failed. Blueprints now checks the certificates of the CLI installer download, the GitHub latest-release check, and the MotherDuck users API against the `certifi` bundle, a new runtime dependency. Certificate verification stays enabled. Refer to the [MotherDuck CLI page](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.6/docs/motherduck-cli.md#ci-and-compatibility). [#175](https://github.com/motherduckdb/motherduck-blueprints/pull/175)

## Compatibility

- **HTTPS requests no longer use the system certificate store.** The requests that Blueprints makes itself trust the `certifi` bundle, or the file named by `SSL_CERT_FILE` when that file exists. Certificate authorities trusted only through the operating system store or `SSL_CERT_DIR` are no longer used for these requests. On a network that inspects TLS, set `SSL_CERT_FILE` to a PEM bundle that contains the inspecting certificate authority. Requests made by the MotherDuck CLI and by `pip` are not affected. Refer to [https-uses-certifi-bundle](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.6/docs/breaking-changes.md#https-uses-certifi-bundle). [#175](https://github.com/motherduckdb/motherduck-blueprints/pull/175)

## Maintenance

- The [Terraform guide](https://github.com/motherduckdb/motherduck-blueprints/blob/v0.10.6/docs/use-with-terraform.md) covers the `motherduck_dive_grant` and `motherduck_flight_grant` resources added in provider v0.4.1. It previously stated that the provider had no grant resources for Dives or Flights. [#174](https://github.com/motherduckdb/motherduck-blueprints/pull/174)
  - Flight `run` grants remain in Blueprints, because only the owner of a Flight can add them.
  - Dive `read` grants can be managed by either tool, but by only one tool for each Dive.
  - The guide also covers the organization grant and embedding service accounts.
- The package and action pins are updated to 0.10.6. [#174](https://github.com/motherduckdb/motherduck-blueprints/pull/174)

**Full diff:** https://github.com/motherduckdb/motherduck-blueprints/compare/v0.10.5...v0.10.6
