"""Parser con un recorte de una respuesta real de la API (10/10/2026).

Estaciones: 7764 (Las Palmas, Canarias), 14612 (solo GNC y GNL), 14123 (con
GLP) y 4375. Todas tienen combustibles con el precio vacío.
"""

import json
from pathlib import Path

import pytest

from src.ingestion.parser import parse_response

SAMPLE = Path(__file__).parents[1] / "fixtures" / "real_sample.json"


@pytest.fixture(scope="module")
def parsed():
    return parse_response(json.loads(SAMPLE.read_bytes()))


def prices_of(parsed, station_id):
    return {p.fuel: p.price for p in parsed.prices if p.station_id == station_id}


def test_stations_and_source_date(parsed):
    assert [s.id for s in parsed.stations] == ["7764", "14612", "14123", "4375"]
    assert parsed.source_date == "2026-10-10T20:31:26"


def test_no_warnings(parsed):
    assert parsed.warnings == []


def test_gnc_station(parsed):
    assert prices_of(parsed, "14612") == {
        "Gas Natural Comprimido": 1.958,
        "Gas Natural Licuado": 1.799,
    }


def test_glp_station(parsed):
    assert prices_of(parsed, "14123") == {
        "Gases licuados del petróleo": 1.154,
        "Gasoleo A": 1.955,
        "Gasoleo Premium": 2.054,
        "Gasolina 95 E5": 1.833,
        "Gasolina 98 E5": 1.918,
    }


def test_empty_prices_are_not_saved(parsed):
    raw = json.loads(SAMPLE.read_bytes())["ListaEESSPrecio"]
    empty_fuels = {key[len("Precio "):] for key, value in raw[3].items() if key.startswith("Precio ") and value == ""}
    assert "Hidrogeno" in empty_fuels
    assert set(prices_of(parsed, "4375")) == {"Gasoleo A", "Gasoleo B", "Gasolina 95 E5"}
    assert not empty_fuels & set(prices_of(parsed, "4375"))


def test_canary_islands_station(parsed):
    canary = parsed.stations[0]
    assert canary.province == "PALMAS (LAS)"
    assert (canary.latitude, canary.longitude) == (28.101861, -15.702083)
    assert prices_of(parsed, "7764") == {
        "Gasoleo A": 1.709,
        "Gasolina 95 E5": 1.569,
        "Gasolina 98 E5": 1.699,
    }
