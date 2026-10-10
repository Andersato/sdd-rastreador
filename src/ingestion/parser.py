"""Normalización de la respuesta de la API (función pura, sin E/S).

Recibe el JSON ya decodificado y devuelve un `ParsedSnapshot`. Los errores de
estructura lanzan `InvalidResponseError` (no se guarda nada); los datos
inválidos de una estación o de `Fecha` se descartan con un aviso.
"""

import json
from datetime import datetime

from .errors import InvalidResponseError
from .models import IngestionWarning, ParsedSnapshot, PriceRecord, Station
from .number_parsing import parse_decimal

PRICE_PREFIX = "Precio "
LATITUDE = "Latitud"
LONGITUDE = "Longitud (WGS84)"
COORDINATE_RANGES = {LATITUDE: (-90.0, 90.0), LONGITUDE: (-180.0, 180.0)}
TEXT_FIELDS = {
    "brand": "Rótulo",
    "address": "Dirección",
    "municipality": "Municipio",
    "province": "Provincia",
    "schedule": "Horario",
}
SOURCE_DATE_FORMAT = "%d/%m/%Y %H:%M:%S"
ABSENT = "(ausente)"
_MISSING = object()


def parse_response(data: object) -> ParsedSnapshot:
    stations_data = _validate_structure(data)
    warnings: list[IngestionWarning] = []
    source_date = _parse_source_date(data.get("Fecha", _MISSING), warnings)

    stations: list[Station] = []
    prices: list[PriceRecord] = []
    seen_ids: set[str] = set()
    for position, raw in enumerate(stations_data, start=1):
        station_id = _parse_station_id(raw, position)
        if station_id in seen_ids:
            raise InvalidResponseError(f"IDEESS duplicado: {station_id}")
        seen_ids.add(station_id)
        stations.append(_parse_station(station_id, raw, warnings))
        prices.extend(_parse_prices(station_id, raw, warnings))

    return ParsedSnapshot(
        source_date=source_date, stations=stations, prices=prices, warnings=warnings
    )


def _validate_structure(data: object) -> list[dict]:
    if not isinstance(data, dict):
        raise InvalidResponseError("la respuesta no es un objeto JSON")
    if "ResultadoConsulta" not in data:
        raise InvalidResponseError("la respuesta no trae ResultadoConsulta")
    if data["ResultadoConsulta"] != "OK":
        raise InvalidResponseError(
            f"ResultadoConsulta no es OK: {_display(data['ResultadoConsulta'])}"
        )
    if "ListaEESSPrecio" not in data:
        raise InvalidResponseError("la respuesta no trae ListaEESSPrecio")
    stations = data["ListaEESSPrecio"]
    if not isinstance(stations, list):
        raise InvalidResponseError("ListaEESSPrecio no es una lista")
    if not stations:
        raise InvalidResponseError("ListaEESSPrecio está vacía")
    for position, raw in enumerate(stations, start=1):
        if not isinstance(raw, dict):
            raise InvalidResponseError(f"la estación n.º {position} no es un objeto")
    return stations


def _parse_station_id(raw: dict, position: int) -> str:
    value = raw.get("IDEESS")
    if not isinstance(value, str) or not value.strip():
        raise InvalidResponseError(
            f"la estación n.º {position} no tiene un IDEESS válido: "
            f"{_display(raw.get('IDEESS', _MISSING))}"
        )
    return value.strip()


def _parse_station(station_id: str, raw: dict, warnings: list) -> Station:
    texts = {attr: _text(raw.get(key)) for attr, key in TEXT_FIELDS.items()}
    latitude, longitude = _parse_coordinates(station_id, raw, warnings)
    return Station(id=station_id, latitude=latitude, longitude=longitude, **texts)


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    # null, ausente u otro tipo (pendiente menor en design.md): vacío.
    return ""


def _parse_coordinates(
    station_id: str, raw: dict, warnings: list
) -> tuple[float | None, float | None]:
    values = {}
    problems = []
    for key, (low, high) in COORDINATE_RANGES.items():
        value = raw.get(key, _MISSING)
        number = parse_decimal(value)
        if number is None:
            reason = "vacía" if isinstance(value, str) and not value.strip() else "formato no válido"
            if value is _MISSING:
                reason = "ausente"
            problems.append(_warning(station_id, key, value, reason))
        elif not low <= number <= high:
            problems.append(_warning(station_id, key, value, "fuera de rango"))
        else:
            values[key] = number
    if problems:
        warnings.extend(problems)
        return None, None
    return values[LATITUDE], values[LONGITUDE]


def _parse_prices(station_id: str, raw: dict, warnings: list) -> list[PriceRecord]:
    prices = []
    for key, value in raw.items():
        if not key.startswith(PRICE_PREFIX):
            continue
        fuel = key[len(PRICE_PREFIX):]
        if value is None or (isinstance(value, str) and not value.strip()):
            continue  # no vende ese combustible
        number = parse_decimal(value)
        if number is None:
            warnings.append(_warning(station_id, fuel, value, "formato no válido"))
        elif number <= 0:
            warnings.append(_warning(station_id, fuel, value, "precio cero o negativo"))
        else:
            prices.append(PriceRecord(station_id, fuel, number))
    return prices


def _parse_source_date(value: object, warnings: list) -> str | None:
    if isinstance(value, str):
        try:
            return datetime.strptime(value, SOURCE_DATE_FORMAT).isoformat()
        except ValueError:
            pass
    reason = "ausente" if value is _MISSING else "formato no válido"
    warnings.append(_warning(None, "Fecha", value, reason))
    return None


def _warning(station_id: str | None, field: str, value: object, reason: str) -> IngestionWarning:
    return IngestionWarning(
        station_id, field, _display(value), reason, value_is_text=isinstance(value, str)
    )


def _display(value: object) -> str:
    """Valor recibido, tal cual si es texto; en JSON si no lo es (`null`, `40.4`)."""
    if value is _MISSING:
        return ABSENT
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
