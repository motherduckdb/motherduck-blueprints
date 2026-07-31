# Projects

Use this root when Flights, Dives, Guides, and configuration genuinely ship, preview, and roll back as one owned unit.

`make new-project revenue-overview` creates a Flight, share, Dive, and validation-only Guide in one package. The Guide includes references to the generated Flight and Dive plus a branch-scoped preview title, so it can be published later by changing `deploy` to `true`.

[`ncs-field-recovery/`](ncs-field-recovery/) is the complete project example. Use the separate `guides/` root instead when documentation has a different owner or lifecycle from the resources it describes.
