"""Constructores de respuestas pequeñas con el formato de la API, para los tests."""

BASE_STATION = {
    "Rótulo": "REPSOL",
    "Dirección": "CALLE MAYOR, 1",
    "Municipio": "Madrid",
    "Provincia": "MADRID",
    "Horario": "L-D: 24H",
    "Latitud": "40,416775",
    "Longitud (WGS84)": "-3,703790",
}


def station(ideess="4375", drop=(), **fields):
    """Estación con datos válidos; `fields` sobrescribe y `drop` quita claves.

    Los precios se pasan con su clave completa, p. ej.
    `**{"Precio Gasoleo A": "1,459"}`.
    """
    data = {"IDEESS": ideess, **BASE_STATION, **fields}
    for key in drop:
        data.pop(key, None)
    return data


def response(*stations, fecha="10/10/2026 19:05:23", drop=()):
    data = {
        "Fecha": fecha,
        "ListaEESSPrecio": list(stations),
        "Nota": "",
        "ResultadoConsulta": "OK",
    }
    for key in drop:
        data.pop(key, None)
    return data
