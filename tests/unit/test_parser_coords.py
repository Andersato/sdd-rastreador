"""Requisito "Coordenadas inválidas" para estaciones nuevas, y Canarias (parser)."""

import pytest

from src.ingestion.parser import parse_response
from tests.builders import response, station

LAT, LON = "Latitud", "Longitud (WGS84)"


def parse(drop=(), **fields):
    result = parse_response(
        response(station("4375", drop=drop, **{"Precio Gasoleo A": "1,459"}, **fields))
    )
    st = result.stations[0]
    return (st.latitude, st.longitude), [(w.station_id, w.field, w.value) for w in result.warnings], result


@pytest.mark.parametrize(
    "fields, drop, expected_warnings",
    [
        ({LAT: "abc", LON: "-3,703790"}, (), [("4375", LAT, "abc")]),
        ({LAT: "123,000000", LON: "-3,703790"}, (), [("4375", LAT, "123,000000")]),
        ({LAT: "40,416775", LON: "-3,70x790"}, (), [("4375", LON, "-3,70x790")]),
        ({LAT: "40,416775", LON: "-190,000000"}, (), [("4375", LON, "-190,000000")]),
        ({LAT: "", LON: "-3,703790"}, (), [("4375", LAT, "")]),
        ({LAT: "40,416775"}, (LON,), [("4375", LON, "(ausente)")]),
        ({LAT: None, LON: "-3,703790"}, (), [("4375", LAT, "null")]),
        ({LAT: 40.416775, LON: "-3,703790"}, (), [("4375", LAT, "40.416775")]),
    ],
    ids=["lat-formato", "lat-rango", "lon-formato", "lon-rango", "vacia", "ausente", "null", "numero"],
)
def test_invalid_coordinate_on_new_station(fields, drop, expected_warnings):
    coords, warnings, result = parse(drop=drop, **fields)
    assert coords == (None, None)
    assert warnings == expected_warnings
    assert [p.fuel for p in result.prices] == ["Gasoleo A"]


def test_both_coordinates_invalid_give_two_warnings():
    coords, warnings, _ = parse(drop=(LON,), **{LAT: "abc"})
    assert coords == (None, None)
    assert warnings == [("4375", LAT, "abc"), ("4375", LON, "(ausente)")]


def test_range_limits_are_valid():
    coords, warnings, _ = parse(**{LAT: "-90,000000", LON: "180,000000"})
    assert coords == (-90.0, 180.0)
    assert warnings == []
    coords, warnings, _ = parse(**{LAT: "90", LON: "-180,0"})
    assert coords == (90.0, -180.0)
    assert warnings == []


def test_canary_islands():
    coords, warnings, _ = parse(**{LAT: "28,123546", LON: "-15,436257"})
    assert coords == (28.123546, -15.436257)
    assert warnings == []


def test_warning_records_whether_value_was_text():
    _, _, result = parse(drop=(LON,), **{LAT: None})
    _, _, text_result = parse(**{LAT: "abc"})
    assert [(w.field, w.value_is_text) for w in result.warnings] == [(LAT, False), (LON, False)]
    assert [(w.field, w.value_is_text) for w in text_result.warnings] == [(LAT, True)]
