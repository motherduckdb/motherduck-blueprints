"""Load official SODIR field and reserve data into MotherDuck."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import duckdb


DEFAULT_CONFIG = {
    "database": "ncs_field_recovery",
    "schema": "main",
    "share": "ncs_field_recovery",
    "share_access": "ORGANIZATION",
    "share_visibility": "DISCOVERABLE",
    "source_service": (
        "https://factmaps.sodir.no/api/rest/services/"
        "DataService/Data/MapServer"
    ),
    "user_agent": (
        "motherduck-blueprints-ncs-field-recovery/1.0 "
        "(https://github.com/motherduckdb/motherduck-blueprints)"
    ),
}

FIELD_LAYER = 7100
FIELD_OUT_FIELDS = (
    "OBJECTID",
    "fldName",
    "fldCurrentActivitySatus",
    "fldDiscoveryYear",
    "cmpLongName",
    "fldHcType",
    "fldMainArea",
    "fldFactPageUrl",
    "fldNpdidField",
    "fldDateUpdatedMax",
)

RESERVE_LAYER = 7113
RESERVE_OUT_FIELDS = (
    "OBJECTID",
    "fldDateOffResEstDisplay",
    "fldRecoverableOil",
    "fldRecoverableGas",
    "fldRecoverableNGL",
    "fldRecoverableCondensate",
    "fldRecoverableOE",
    "fldRemainingOil",
    "fldRemainingGas",
    "fldRemainingNGL",
    "fldRemainingCondensate",
    "fldRemainingOE",
    "fldInplaceOil",
    "fldInplaceAssLiquid",
    "fldInplaceAssGas",
    "fldInplaceFreeGas",
    "fldVersion",
    "fldNpdidField",
)

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PAGE_SIZE = 1000


def load_runtime_config() -> dict[str, str]:
    """Accept config from common Flight shapes, falling back to direct env vars."""
    raw = (
        os.getenv("MOTHERDUCK_FLIGHT_CONFIG")
        or os.getenv("FLIGHT_CONFIG")
        or os.getenv("CONFIG")
    )
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}


RUNTIME_CONFIG = load_runtime_config()


def setting(name: str) -> str:
    for key in (f"SODIR_NCS_{name.upper()}", name.upper(), name):
        value = os.getenv(key)
        if value:
            return value

    for key in (name, name.lower(), name.upper()):
        value = RUNTIME_CONFIG.get(key)
        if value:
            return value

    return DEFAULT_CONFIG[name]


def quote_ident(value: str) -> str:
    if not SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def fetch_json(url: str, user_agent: str, retries: int = 4) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("SODIR returned a non-object JSON payload")
            if payload.get("error"):
                raise RuntimeError(f"SODIR API error: {payload['error']}")
            return payload
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == retries:
                raise
            time.sleep(attempt * 2)
        except urllib.error.URLError:
            if attempt == retries:
                raise
            time.sleep(attempt * 2)

    raise RuntimeError(f"Failed to fetch {url}")


def fetch_layer(
    source_service: str,
    layer_id: int,
    out_fields: tuple[str, ...],
    user_agent: str,
) -> list[dict[str, Any]]:
    """Fetch every ArcGIS REST page for a SODIR layer."""
    rows: list[dict[str, Any]] = []
    offset = 0
    source_root = source_service.rstrip("/")

    while True:
        query = urllib.parse.urlencode(
            {
                "where": "1=1",
                "outFields": ",".join(out_fields),
                "returnGeometry": "false",
                "orderByFields": "OBJECTID",
                "resultOffset": str(offset),
                "resultRecordCount": str(PAGE_SIZE),
                "f": "json",
            }
        )
        payload = fetch_json(
            f"{source_root}/{layer_id}/query?{query}",
            user_agent,
        )
        features = payload.get("features", [])
        if not isinstance(features, list):
            raise RuntimeError(f"SODIR layer {layer_id} returned invalid features")

        page_rows = [
            feature["attributes"]
            for feature in features
            if isinstance(feature, dict)
            and isinstance(feature.get("attributes"), dict)
        ]
        rows.extend(page_rows)

        if not payload.get("exceededTransferLimit"):
            break
        if not page_rows:
            raise RuntimeError(
                f"SODIR layer {layer_id} indicated more data but returned no rows"
            )
        offset += len(page_rows)

    if not rows:
        raise RuntimeError(f"SODIR layer {layer_id} returned no rows")
    return rows


def stage_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def ensure_destination(
    con: duckdb.DuckDBPyConnection,
    database: str,
    schema: str,
) -> tuple[str, str]:
    database_ident = quote_ident(database)
    schema_ident = quote_ident(schema)
    exists = con.execute(
        """
        SELECT 1
        FROM duckdb_databases()
        WHERE database_name = ?
        """,
        [database],
    ).fetchone()
    if not exists:
        con.execute(f"CREATE DATABASE IF NOT EXISTS {database_ident}")
    con.execute(
        f"CREATE SCHEMA IF NOT EXISTS {database_ident}.{schema_ident}"
    )
    return database_ident, schema_ident


def _load_tables(
    con: duckdb.DuckDBPyConnection,
    database: str,
    schema: str,
    fields_path: Path,
    reserves_path: Path,
    source_service: str,
) -> tuple[int, int, int]:
    """Bulk-load staged JSON and rebuild the latest-recovery analytical view."""
    database_ident, schema_ident = ensure_destination(con, database, schema)
    namespace = f"{database_ident}.{schema_ident}"
    loaded_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    con.execute(
        f"""
        CREATE OR REPLACE TABLE {namespace}.fields AS
        SELECT
          OBJECTID::BIGINT AS object_id,
          fldNpdidField::BIGINT AS field_id,
          fldName::VARCHAR AS field_name,
          fldCurrentActivitySatus::VARCHAR AS activity_status,
          fldDiscoveryYear::INTEGER AS discovery_year,
          cmpLongName::VARCHAR AS operator_name,
          fldHcType::VARCHAR AS hydrocarbon_type,
          fldMainArea::VARCHAR AS main_area,
          fldFactPageUrl::VARCHAR AS fact_page_url,
          CASE
            WHEN fldDateUpdatedMax IS NULL THEN NULL
            ELSE epoch_ms(fldDateUpdatedMax::BIGINT)
          END AS source_updated_at,
          ?::TIMESTAMPTZ AS loaded_at_utc
        FROM read_json_auto(?, format = 'array')
        """,
        [loaded_at, str(fields_path)],
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE {namespace}.field_reserve_history AS
        SELECT
          OBJECTID::BIGINT AS object_id,
          fldNpdidField::BIGINT AS field_id,
          fldVersion::INTEGER AS reserve_version,
          CASE
            WHEN fldDateOffResEstDisplay IS NULL THEN NULL
            ELSE epoch_ms(fldDateOffResEstDisplay::BIGINT)::DATE
          END AS official_estimate_date,
          fldRecoverableOil::DOUBLE AS recoverable_oil_mill_sm3,
          fldRecoverableGas::DOUBLE AS recoverable_gas_bill_sm3,
          fldRecoverableNGL::DOUBLE AS recoverable_ngl_mill_tonnes,
          fldRecoverableCondensate::DOUBLE AS recoverable_condensate_mill_sm3,
          fldRecoverableOE::DOUBLE AS recoverable_oe_mill_sm3,
          fldRemainingOil::DOUBLE AS remaining_oil_mill_sm3,
          fldRemainingGas::DOUBLE AS remaining_gas_bill_sm3,
          fldRemainingNGL::DOUBLE AS remaining_ngl_mill_tonnes,
          fldRemainingCondensate::DOUBLE AS remaining_condensate_mill_sm3,
          fldRemainingOE::DOUBLE AS remaining_oe_mill_sm3,
          fldInplaceOil::DOUBLE AS inplace_oil_mill_sm3,
          fldInplaceAssLiquid::DOUBLE AS inplace_associated_liquid_mill_sm3,
          fldInplaceAssGas::DOUBLE AS inplace_associated_gas_bill_sm3,
          fldInplaceFreeGas::DOUBLE AS inplace_free_gas_bill_sm3,
          ?::TIMESTAMPTZ AS loaded_at_utc
        FROM read_json_auto(?, format = 'array')
        """,
        [loaded_at, str(reserves_path)],
    )

    con.execute(
        f"""
        CREATE OR REPLACE VIEW {namespace}.field_recovery_latest AS
        WITH latest_reserve AS (
          SELECT *
          FROM {namespace}.field_reserve_history
          QUALIFY row_number() OVER (
            PARTITION BY field_id
            ORDER BY
              reserve_version DESC NULLS LAST,
              official_estimate_date DESC NULLS LAST,
              object_id DESC
          ) = 1
        )
        SELECT
          f.field_id,
          f.field_name,
          f.activity_status,
          f.discovery_year,
          f.operator_name,
          f.hydrocarbon_type,
          f.main_area,
          f.fact_page_url,
          f.source_updated_at,
          r.reserve_version,
          r.official_estimate_date,
          r.recoverable_oil_mill_sm3,
          r.recoverable_gas_bill_sm3,
          r.recoverable_ngl_mill_tonnes,
          r.recoverable_condensate_mill_sm3,
          r.recoverable_oe_mill_sm3,
          r.remaining_oil_mill_sm3,
          r.remaining_gas_bill_sm3,
          r.remaining_ngl_mill_tonnes,
          r.remaining_condensate_mill_sm3,
          r.remaining_oe_mill_sm3,
          r.inplace_oil_mill_sm3,
          r.inplace_associated_liquid_mill_sm3,
          r.inplace_associated_gas_bill_sm3,
          r.inplace_free_gas_bill_sm3,
          CASE
            WHEN f.hydrocarbon_type IN ('OIL', 'OIL/GAS', 'OIL/CONDENSATE')
              AND r.inplace_oil_mill_sm3 > 0
              AND r.recoverable_oil_mill_sm3 IS NOT NULL
            THEN 100.0 * r.recoverable_oil_mill_sm3
              / r.inplace_oil_mill_sm3
          END AS oil_recovery_factor_pct,
          greatest(
            coalesce(r.recoverable_oil_mill_sm3, 0)
              - coalesce(r.remaining_oil_mill_sm3, 0),
            0
          ) AS recovered_oil_mill_sm3,
          CASE
            WHEN r.recoverable_oil_mill_sm3 > 0
            THEN least(
              100.0,
              greatest(
                0.0,
                100.0
                  * (
                    r.recoverable_oil_mill_sm3
                      - coalesce(r.remaining_oil_mill_sm3, 0)
                  )
                  / r.recoverable_oil_mill_sm3
              )
            )
          END AS produced_share_of_recoverable_oil_pct,
          greatest(
            coalesce(r.recoverable_oe_mill_sm3, 0)
              - coalesce(r.remaining_oe_mill_sm3, 0),
            0
          ) AS recovered_oe_mill_sm3,
          greatest(
            coalesce(r.remaining_oe_mill_sm3, 0),
            0
          ) AS remaining_oe_mill_sm3_nonnegative,
          greatest(f.loaded_at_utc, r.loaded_at_utc) AS loaded_at_utc
        FROM {namespace}.fields AS f
        LEFT JOIN latest_reserve AS r USING (field_id)
        """
    )

    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {namespace}.ingestion_runs (
          loaded_at_utc TIMESTAMPTZ,
          source_service VARCHAR,
          field_rows BIGINT,
          reserve_history_rows BIGINT,
          latest_reserve_version INTEGER
        )
        """
    )

    field_count = con.execute(
        f"SELECT count(*) FROM {namespace}.fields"
    ).fetchone()[0]
    reserve_count = con.execute(
        f"SELECT count(*) FROM {namespace}.field_reserve_history"
    ).fetchone()[0]
    latest_version = con.execute(
        f"SELECT max(reserve_version) FROM {namespace}.field_reserve_history"
    ).fetchone()[0]
    con.execute(
        f"INSERT INTO {namespace}.ingestion_runs VALUES (?, ?, ?, ?, ?)",
        [
            loaded_at,
            source_service,
            field_count,
            reserve_count,
            latest_version,
        ],
    )
    return int(field_count), int(reserve_count), int(latest_version)


def load_tables(
    con: duckdb.DuckDBPyConnection,
    database: str,
    schema: str,
    fields_path: Path,
    reserves_path: Path,
    source_service: str,
) -> tuple[int, int, int]:
    """Atomically replace the analytical tables and record the ingestion."""
    ensure_destination(con, database, schema)
    con.execute("BEGIN TRANSACTION")
    try:
        result = _load_tables(
            con,
            database,
            schema,
            fields_path,
            reserves_path,
            source_service,
        )
    except Exception:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")
    return result


def publish_share(
    con: duckdb.DuckDBPyConnection,
    database: str,
    share: str,
    share_access: str,
    share_visibility: str,
) -> str:
    access = share_access.upper()
    visibility = share_visibility.upper()
    if access not in {"ORGANIZATION", "UNRESTRICTED", "RESTRICTED"}:
        raise ValueError(
            "share_access must be ORGANIZATION, UNRESTRICTED, or RESTRICTED"
        )
    if visibility not in {"DISCOVERABLE", "HIDDEN"}:
        raise ValueError("share_visibility must be DISCOVERABLE or HIDDEN")
    if visibility == "HIDDEN" and access != "RESTRICTED":
        raise ValueError("HIDDEN shares must use RESTRICTED access")

    database_ident = quote_ident(database)
    share_ident = quote_ident(share)
    con.execute(
        f"""
        CREATE SHARE IF NOT EXISTS {share_ident}
        FROM {database_ident}
        (ACCESS {access}, VISIBILITY {visibility})
        """
    )
    con.execute(f"UPDATE SHARE {share_ident}")
    row = con.execute(
        "SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = "
        + sql_string(share)
    ).fetchone()
    if not row:
        raise RuntimeError(f"Share {share!r} was not found after creation")
    return str(row[0])


def main() -> None:
    database = setting("database")
    schema = setting("schema")
    share = setting("share")
    source_service = setting("source_service")
    user_agent = setting("user_agent")

    fields = fetch_layer(
        source_service,
        FIELD_LAYER,
        FIELD_OUT_FIELDS,
        user_agent,
    )
    reserves = fetch_layer(
        source_service,
        RESERVE_LAYER,
        RESERVE_OUT_FIELDS,
        user_agent,
    )

    with tempfile.TemporaryDirectory(prefix="sodir-ncs-") as temp_dir:
        fields_path = Path(temp_dir) / "fields.json"
        reserves_path = Path(temp_dir) / "reserves.json"
        stage_rows(fields_path, fields)
        stage_rows(reserves_path, reserves)

        con = duckdb.connect("md:")
        try:
            con.execute("SET TimeZone = 'UTC'")
            field_count, reserve_count, latest_version = load_tables(
                con,
                database,
                schema,
                fields_path,
                reserves_path,
                source_service,
            )
            share_url = publish_share(
                con,
                database,
                share,
                setting("share_access"),
                setting("share_visibility"),
            )
        finally:
            con.close()

    print(
        f"Loaded {field_count} fields and {reserve_count} reserve estimates "
        f"(latest version {latest_version}) into md:{database}.{schema}"
    )
    print(f"Published share {share}: {share_url}")


if __name__ == "__main__":
    main()
