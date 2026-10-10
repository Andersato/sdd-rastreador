"""Genera las respuestas escritas a mano de tests/fixtures/.

Imitan el formato de la API del Ministerio (textos con coma decimal).
Se vuelven a generar con: .venv/bin/python tests/fixtures/make_fixtures.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
FUELS = [
    "Biodiesel", "Bioetanol", "Gas Natural Comprimido", "Gas Natural Licuado",
    "Gases licuados del petróleo", "Gasoleo A", "Gasoleo B", "Gasoleo Premium",
    "Gasolina 95 E10", "Gasolina 95 E5", "Gasolina 95 E5 Premium",
    "Gasolina 98 E10", "Gasolina 98 E5", "Hidrogeno",
]


def station(ideess, brand="REPSOL", lat="40,416775", lon="-3,703790", **prices):
    data = {
        "C.P.": "28013",
        "Dirección": "CALLE MAYOR, 1",
        "Horario": "L-D: 24H",
        "Latitud": lat,
        "Localidad": "MADRID",
        "Longitud (WGS84)": lon,
        "Margen": "D",
        "Municipio": "Madrid",
        "Provincia": "MADRID",
        "Remisión": "dm",
        "Rótulo": brand,
        "Tipo Venta": "P",
        "IDEESS": ideess,
        "IDMunicipio": "4354",
        "IDProvincia": "28",
        "IDCCAA": "13",
    }
    for fuel in FUELS:
        data[f"Precio {fuel}"] = prices.get(fuel, "")
    return data


def response(stations, fecha="10/10/2026 19:05:23", resultado="OK"):
    data = {"Fecha": fecha, "ListaEESSPrecio": stations, "Nota": "Archivo de prueba"}
    if resultado is not None:
        data["ResultadoConsulta"] = resultado
    return data


def p(**kwargs):
    """Atajo para precios con nombres de combustible con espacios."""
    names = {
        "a": "Gasoleo A", "e5": "Gasolina 95 E5", "e98": "Gasolina 98 E5",
        "glp": "Gases licuados del petróleo", "gnc": "Gas Natural Comprimido",
    }
    return {names[k]: v for k, v in kwargs.items()}


S1 = station("4375", **p(a="1,459", e5="1,529"))
S2 = station("5120", brand="CEPSA", lat="41,387400", lon="2,168600", **p(a="1,479"))

FIXTURES = {
    "valid_two_stations.json": response([S1, S2]),
    "valid_three_stations.json": response([
        station("4375", **p(a="1,459", e5="1,529")),
        station("5120", brand="CEPSA"),
        station("6200", brand="GALP", **p(a="1,449", e5="1,519", e98="1,689", glp="0,899")),
    ]),
    "with_warnings.json": response([
        station("4375", **p(a="1,4a9", e5="1,529")),
        station("5120", brand="CEPSA", lat="abc", lon="2,168600", **p(a="1,479")),
    ]),
    "fecha_invalid.json": response([S1, S2], fecha="2026-10-10 19:05"),
    "root_list.json": [],
    "root_string.json": "OK",
    "resultado_error.json": response([S1], resultado="ERROR"),
    "resultado_missing.json": response([S1], resultado=None),
    "lista_missing.json": {"Fecha": "10/10/2026 19:05:23", "Nota": "", "ResultadoConsulta": "OK"},
    "lista_empty.json": response([]),
    "lista_object.json": {**response([]), "ListaEESSPrecio": {"IDEESS": "4375"}},
    "lista_string.json": {**response([]), "ListaEESSPrecio": "sin datos"},
    "station_not_object.json": response([S1, "4375"]),
    "ideess_missing.json": response([S1, {k: v for k, v in S2.items() if k != "IDEESS"}]),
    "ideess_empty.json": response([S1, {**S2, "IDEESS": ""}]),
    "ideess_spaces.json": response([S1, {**S2, "IDEESS": "   "}]),
    "ideess_number.json": response([S1, {**S2, "IDEESS": 5120}]),
    "ideess_null.json": response([S1, {**S2, "IDEESS": None}]),
    "ideess_duplicate.json": response([S1, {**S2, "IDEESS": "4375"}]),
    "ideess_duplicate_spaces.json": response([{**S1, "IDEESS": " 4375 "}, {**S2, "IDEESS": "4375"}]),
}

TEXT_FIXTURES = {
    "not_json.xml": (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<PreciosEESSTerrestres><Fecha>10/10/2026 19:05:23</Fecha></PreciosEESSTerrestres>\n"
    ),
    "not_json.html": "<!DOCTYPE html>\n<html><body><h1>Servicio no disponible</h1></body></html>\n",
    "empty.json": "",
}


def main():
    for name, data in FIXTURES.items():
        (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, text in TEXT_FIXTURES.items():
        (HERE / name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
