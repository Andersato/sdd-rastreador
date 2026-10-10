"""Requisitos de conversión, precios vacíos, combustibles y precios inválidos (parser)."""

import pytest

from src.ingestion.models import IngestionWarning, PriceRecord
from src.ingestion.parser import parse_response
from tests.builders import response, station


def parse_prices(drop=(), **prices):
    result = parse_response(response(station("4375", drop=drop, **prices)))
    found = {p.fuel: p.price for p in result.prices}
    return found, result.warnings


def warning(fuel, value, reason):
    return IngestionWarning("4375", fuel, value, reason)


# Conversión de números con coma decimal
def test_price_with_decimal_comma():
    found, warnings = parse_prices(**{"Precio Gasoleo A": "1,459"})
    assert found == {"Gasoleo A": 1.459}
    assert warnings == []


def test_spaces_and_more_decimals():
    found, _ = parse_prices(**{"Precio Gasolina 95 E5": " 1,5290 "})
    assert found == {"Gasolina 95 E5": 1.529}


def test_tabs_and_newlines_around():
    found, warnings = parse_prices(**{"Precio Gasoleo A": "\t1,459\n"})
    assert found == {"Gasoleo A": 1.459}
    assert warnings == []


def test_decimal_point_is_invalid():
    found, warnings = parse_prices(**{"Precio Gasoleo A": "1.459"})
    assert found == {}
    assert warnings == [warning("Gasoleo A", "1.459", "formato no válido")]


# Precio vacío o ausente
def test_empty_price_not_saved():
    found, warnings = parse_prices(**{"Precio Gasoleo A": "1,459", "Precio Hidrogeno": ""})
    assert found == {"Gasoleo A": 1.459}
    assert warnings == []


def test_spaces_only_price_not_saved():
    found, warnings = parse_prices(**{"Precio Gasolina 98 E5": "   "})
    assert found == {}
    assert warnings == []


def test_missing_price_key():
    found, warnings = parse_prices(**{"Precio Gasoleo A": "1,459"})
    assert "Hidrogeno" not in found
    assert warnings == []


def test_null_price():
    found, warnings = parse_prices(**{"Precio Gasoleo A": "1,459", "Precio Hidrogeno": None})
    assert found == {"Gasoleo A": 1.459}
    assert warnings == []


def test_station_without_any_price():
    result = parse_response(
        response(station("4375", **{"Precio Gasoleo A": "", "Precio Gasolina 95 E5": ""}))
    )
    assert len(result.stations) == 1
    assert result.prices == []


# Combustibles guardados
def test_several_fuels():
    result = parse_response(
        response(
            station(
                "4375",
                **{
                    "Precio Gasolina 95 E5": "1,529",
                    "Precio Gasoleo A": "1,459",
                    "Precio Gases licuados del petróleo": "0,899",
                },
            )
        )
    )
    assert sorted(result.prices, key=lambda p: p.fuel) == [
        PriceRecord("4375", "Gases licuados del petróleo", 0.899),
        PriceRecord("4375", "Gasoleo A", 1.459),
        PriceRecord("4375", "Gasolina 95 E5", 1.529),
    ]


# Precios inválidos
def test_unexpected_format_keeps_other_prices():
    found, warnings = parse_prices(
        **{"Precio Gasoleo A": "1,4a9", "Precio Gasolina 95 E5": "1,529"}
    )
    assert found == {"Gasolina 95 E5": 1.529}
    assert warnings == [warning("Gasoleo A", "1,4a9", "formato no válido")]


def test_price_not_text():
    found, warnings = parse_prices(**{"Precio Gasoleo A": 1.459})
    assert found == {}
    assert warnings == [warning("Gasoleo A", "1.459", "formato no válido")]


@pytest.mark.parametrize("value", ["0,000", "-1,459"])
def test_zero_or_negative_price(value):
    found, warnings = parse_prices(**{"Precio Gasoleo A": value})
    assert found == {}
    assert warnings == [warning("Gasoleo A", value, "precio cero o negativo")]


def test_huge_price_is_invalid_not_infinite():
    huge = "1" * 400
    found, warnings = parse_prices(**{"Precio Gasoleo A": huge})
    assert found == {}
    assert warnings == [warning("Gasoleo A", huge, "formato no válido")]
