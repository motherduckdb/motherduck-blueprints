# NCS Field Recovery Guide

## Trusted sources

- Use the Norwegian Offshore Directorate FactMaps service configured by `source_service` as the source of field and reserve data.
- Treat reported reserves and recovery factors as source estimates, not forecasts produced by this project.
- Preserve source dates and units when extending the ingestion model.

## Interpretation

- Official oil recovery ratio is original recoverable oil divided by original oil in place.
- Produced share is original recoverable oil minus remaining oil, divided by original recoverable oil.
- Compare fields only after checking that the source records use compatible reporting periods and units.
- Missing values mean the source did not provide a usable estimate; do not silently replace them with zero.

The project Flight owns ingestion, the `data` share publishes the database, and the `explorer` Dive presents the resulting comparisons.
