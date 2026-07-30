from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, urlparse

import duckdb
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FLIGHT_PATH = REPO_ROOT / "projects/ncs-field-recovery/src/flight.py"


def load_flight_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ncs_field_recovery_flight", FLIGHT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def field_row(field_id: int, name: str, hydrocarbon_type: str = "OIL") -> dict[str, Any]:
    return {
        "OBJECTID": field_id,
        "fldNpdidField": field_id,
        "fldName": name,
        "fldCurrentActivitySatus": "Producing",
        "fldDiscoveryYear": 2000,
        "cmpLongName": "Example Operator",
        "fldHcType": hydrocarbon_type,
        "fldMainArea": "North sea",
        "fldFactPageUrl": f"https://example.test/field/{field_id}",
        "fldDateUpdatedMax": 1_735_689_600_000,
    }


def reserve_row(
    field_id: int,
    version: int,
    *,
    recoverable_oil: float,
    remaining_oil: float,
    inplace_oil: float,
) -> dict[str, Any]:
    return {
        "OBJECTID": field_id * 10_000 + version,
        "fldNpdidField": field_id,
        "fldVersion": version,
        "fldDateOffResEstDisplay": 1_735_689_600_000,
        "fldRecoverableOil": recoverable_oil,
        "fldRecoverableGas": 0,
        "fldRecoverableNGL": 0,
        "fldRecoverableCondensate": 0,
        "fldRecoverableOE": recoverable_oil,
        "fldRemainingOil": remaining_oil,
        "fldRemainingGas": 0,
        "fldRemainingNGL": 0,
        "fldRemainingCondensate": 0,
        "fldRemainingOE": remaining_oil,
        "fldInplaceOil": inplace_oil,
        "fldInplaceAssLiquid": 0,
        "fldInplaceAssGas": 0,
        "fldInplaceFreeGas": 0,
    }


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows), encoding="utf-8")


def test_fetch_layer_paginates_until_transfer_limit_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_flight_module()
    urls: list[str] = []
    pages = [
        {
            "features": [{"attributes": {"OBJECTID": 1}}],
            "exceededTransferLimit": True,
        },
        {
            "features": [{"attributes": {"OBJECTID": 2}}],
            "exceededTransferLimit": False,
        },
    ]

    def fake_fetch_json(url: str, user_agent: str) -> dict[str, Any]:
        assert user_agent == "test-agent"
        urls.append(url)
        return pages[len(urls) - 1]

    monkeypatch.setattr(module, "fetch_json", fake_fetch_json)

    rows = module.fetch_layer("https://example.test/service/", 42, ("OBJECTID",), "test-agent")

    assert rows == [{"OBJECTID": 1}, {"OBJECTID": 2}]
    assert [
        parse_qs(urlparse(url).query)["resultOffset"][0] for url in urls
    ] == ["0", "1"]


def test_load_tables_builds_latest_metrics_atomically(tmp_path: Path) -> None:
    module = load_flight_module()
    fields_path = tmp_path / "fields.json"
    reserves_path = tmp_path / "reserves.json"
    write_json(
        fields_path,
        [
            field_row(1, "Alpha"),
            field_row(2, "Beta", hydrocarbon_type="GAS"),
        ],
    )
    write_json(
        reserves_path,
        [
            reserve_row(1, 2024, recoverable_oil=30, remaining_oil=12, inplace_oil=60),
            reserve_row(1, 2025, recoverable_oil=40, remaining_oil=10, inplace_oil=80),
            reserve_row(2, 2025, recoverable_oil=5, remaining_oil=2, inplace_oil=10),
        ],
    )
    con = duckdb.connect(":memory:")

    assert module.load_tables(
        con,
        "memory",
        "main",
        fields_path,
        reserves_path,
        "https://example.test/service",
    ) == (2, 3, 2025)
    assert con.execute(
        """
        SELECT field_name, reserve_version, oil_recovery_factor_pct,
               produced_share_of_recoverable_oil_pct
        FROM memory.main.field_recovery_latest
        ORDER BY field_name
        """
    ).fetchall() == [
        ("Alpha", 2025, 50.0, 75.0),
        ("Beta", 2025, None, 60.0),
    ]
    assert con.execute("SELECT count(*) FROM memory.main.ingestion_runs").fetchone() == (1,)

    write_json(fields_path, [field_row(3, "Replacement")])
    write_json(reserves_path, [{"invalid": True}])

    with pytest.raises(duckdb.Error):
        module.load_tables(
            con,
            "memory",
            "main",
            fields_path,
            reserves_path,
            "https://example.test/service",
        )

    assert con.execute("SELECT field_name FROM memory.main.fields ORDER BY field_name").fetchall() == [
        ("Alpha",),
        ("Beta",),
    ]
    assert con.execute("SELECT count(*) FROM memory.main.ingestion_runs").fetchone() == (1,)
