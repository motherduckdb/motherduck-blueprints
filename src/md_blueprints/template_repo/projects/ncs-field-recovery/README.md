# NCS Field Recovery Explorer

This project loads official Norwegian Continental Shelf field and reserve data from the Norwegian Offshore Directorate (SODIR), publishes it through a MotherDuck share, deploys an interactive Dive for comparing public recovery estimates, and versions trusted interpretation guidance beside those resources.

It is an open-data alternative to the authenticated OREC NCS Insight experience. It does not reproduce OREC's proprietary calculations or reservoir-property filters.

## Resources

- Flight: `loader`
- Share: `data`
- Dive: `explorer`
- Guide: `field-recovery` (validation-only until `deploy: true`)

The Flight runs once on deploy and is intentionally unscheduled. The SODIR source is public and requires no secret. Preview deployments use branch-scoped database, share, Flight, and Dive names and are cleaned up when the branch closes.

The Guide references the package's Flight and Dive and records source, metric, and interpretation rules in `guide.md`. Its preview title is already branch-scoped, so enabling deployment only requires changing `deploy` to `true`.

## Official Sources

The Flight reads two layers from SODIR's public FactMaps REST service:

- [`field`](https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer/7100): field name, status, operator, hydrocarbon type, main area, discovery year, and FactPages URL.
- [`field_reserves`](https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer/7113): archived yearly official estimates for recoverable, remaining, and in-place volumes.

SODIR describes FactPages and FactMaps as public open data published under the Norwegian Licence for Open Government Data in its [technical information and update log](https://www.sodir.no/en/facts/data-and-analyses/open-data/factpages-and-factmaps-technical-information/). Source data can be revised; the Flight records the load time and preserves the complete reserve-estimate history returned by the service.

## Metric Definitions

The Dive labels its central metric **official oil recovery ratio** for SODIR's oil-bearing field classifications (`OIL`, `OIL/GAS`, and `OIL/CONDENSATE`):

```text
original recoverable oil / original oil in place × 100
```

It is only calculated where both official source values are present and original oil in place is greater than zero. Gas and gas/condensate fields remain available for remaining-resource analysis, but the Dive does not calculate this oil ratio for them because incidental liquid volumes can make the two source fields non-comparable.

The **produced share of recoverable oil** is a separate depletion measure:

```text
(original recoverable oil − remaining oil) / original recoverable oil × 100
```

Neither metric should be described as OREC's “Final OE Recovery.” SODIR's published field estimates do not include OREC's porosity, permeability, pressure, temperature, GOR, oil-density, or recovery-mechanism inputs.

## Tables and View

- `fields`: current field metadata.
- `field_reserve_history`: all archived annual official reserve estimates returned by SODIR.
- `field_recovery_latest`: one latest reserve estimate per field with the transparent ratios used by the Dive.
- `ingestion_runs`: append-only load audit records.

## Local Checks

```bash
make validate
make mock-test
make example-smoke
make preview-smoke ncs-field-recovery
```

To smoke-test only the public source and transformation locally, import `src/flight.py`, call `fetch_layer` for layers `7100` and `7113`, attach a local DuckDB database under the configured database name, and pass the staged JSON files to `load_tables`.
