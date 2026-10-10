"""Requisito "Datos fijos de la estación separados de los precios" (parser)."""

from src.ingestion.models import Station
from src.ingestion.parser import parse_response
from tests.builders import response, station


def parse_one(**fields):
    result = parse_response(response(station(**fields)))
    assert len(result.stations) == 1
    return result


def test_new_station():
    result = parse_one()
    assert result.stations[0] == Station(
        id="4375",
        brand="REPSOL",
        address="CALLE MAYOR, 1",
        municipality="Madrid",
        province="MADRID",
        schedule="L-D: 24H",
        latitude=40.416775,
        longitude=-3.70379,
    )
    assert result.warnings == []


def test_empty_null_or_missing_text_fields():
    result = parse_response(
        response(
            station(
                "5120",
                drop=["Horario"],
                **{"Rótulo": "", "Dirección": None, "Precio Gasoleo A": "1,459"},
            )
        )
    )
    st = result.stations[0]
    assert (st.brand, st.address, st.schedule) == ("", "", "")
    assert len(result.prices) == 1
    assert result.warnings == []


def test_text_field_as_number():
    result = parse_one(**{"Rótulo": 123})
    assert result.stations[0].brand == "123"
    assert result.warnings == []


def test_text_with_spaces_kept_as_is():
    assert parse_one(**{"Rótulo": " GALP "}).stations[0].brand == " GALP "


def test_ideess_spaces_are_stripped():
    result = parse_response(response(station(" 4375 "), station("\t5120\n")))
    assert [s.id for s in result.stations] == ["4375", "5120"]
