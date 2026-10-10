"""Requisito "Respuestas inválidas no guardan nada" a nivel de parser."""

import pytest

from src.ingestion.errors import InvalidResponseError
from src.ingestion.parser import parse_response
from tests.builders import response, station


def invalid(data, match=None):
    with pytest.raises(InvalidResponseError, match=match):
        parse_response(data)


@pytest.mark.parametrize("data", [[], "OK", None, 3])
def test_root_not_object(data):
    invalid(data)


def test_resultado_not_ok():
    data = response(station())
    data["ResultadoConsulta"] = "ERROR"
    invalid(data, "ERROR")


def test_resultado_missing():
    invalid(response(station(), drop=["ResultadoConsulta"]), "ResultadoConsulta")


def test_lista_missing():
    invalid(response(station(), drop=["ListaEESSPrecio"]), "ListaEESSPrecio")


def test_lista_empty():
    invalid(response(), "vacía")


@pytest.mark.parametrize("value", [{"IDEESS": "4375"}, "sin datos"])
def test_lista_not_a_list(value):
    data = response()
    data["ListaEESSPrecio"] = value
    invalid(data, "no es una lista")


def test_station_not_object():
    invalid(response(station(), "4375"), "no es un objeto")


@pytest.mark.parametrize("value", ["", "   ", 4375, None])
def test_ideess_invalid(value):
    invalid(response(station("1"), station(value)), "IDEESS")


def test_ideess_missing():
    invalid(response(station("1"), station(drop=["IDEESS"])), "IDEESS")


def test_ideess_duplicate():
    invalid(response(station("4375"), station("4375")), "IDEESS duplicado: 4375")


def test_ideess_duplicate_with_spaces():
    invalid(response(station(" 4375 "), station("4375")), "IDEESS duplicado: 4375$")
