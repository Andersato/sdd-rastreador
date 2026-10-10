"""Datos normalizados que produce el parser y consume el guardado."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IngestionWarning:
    """Dato descartado que no impide guardar la captura.

    `station_id` es None para avisos de la respuesta (p. ej. `Fecha`).
    `value` es el valor tal como llegó, ya formateado para mostrarlo: el texto
    tal cual, otro tipo en JSON (`null`, `40.416775`) o `(ausente)`.
    `value_is_text` indica si el valor original era texto (para mostrarlo
    entre comillas); no cuenta al comparar avisos.
    """

    station_id: str | None
    field: str
    value: str
    reason: str
    value_is_text: bool = field(default=True, compare=False)


@dataclass(frozen=True)
class Station:
    """Datos fijos de una estación. Las coordenadas van las dos o ninguna."""

    id: str
    brand: str
    address: str
    municipality: str
    province: str
    schedule: str
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class PriceRecord:
    station_id: str
    fuel: str
    price: float


@dataclass(frozen=True)
class ParsedSnapshot:
    """Resultado del parser: todo lo que se guardará en una captura."""

    source_date: str | None
    stations: list[Station] = field(default_factory=list)
    prices: list[PriceRecord] = field(default_factory=list)
    warnings: list[IngestionWarning] = field(default_factory=list)
