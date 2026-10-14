"""Errores controlados de la ingesta. La CLI los convierte en mensaje y código
de salida: 3 para `IngestionBusy`, 4 para `ShortResponseError` y 1 para el resto."""

from .formatting import percentage, thousands


class IngestionError(Exception):
    """Base de todos los errores controlados de la ingesta."""


class DownloadError(IngestionError):
    """La descarga ha fallado (red, HTTP o lectura de la respuesta)."""


class DownloadTimeout(DownloadError):
    """La descarga no ha terminado dentro del plazo total."""


class InvalidResponseError(IngestionError):
    """La respuesta, en su conjunto, no tiene el formato esperado."""


class StorageError(IngestionError):
    """Fallo al guardar en la base de datos; no se ha guardado nada."""


class IngestionBusy(IngestionError):
    """Otra ingesta tiene cogido el bloqueo de la carpeta de la base."""


class ShortResponseError(IngestionError):
    """Respuesta con menos del 80 % de las estaciones de la última captura."""

    def __init__(self, stations: int, reference: int):
        self.stations = stations
        self.reference = reference
        super().__init__(
            f"respuesta sospechosamente corta: {short_response_figures(stations, reference)}; "
            "no se ha guardado. Si es correcta, guárdala con --accept-short-response"
        )


def short_response_figures(stations: int, reference: int) -> str:
    """'9.000 estaciones con precio frente a 12.000 de la última captura (75,0 %)'."""
    return (
        f"{thousands(stations)} estaciones con precio frente a {thousands(reference)} "
        f"de la última captura ({percentage(stations, reference)})"
    )


class InterruptedIngestion(IngestionError):
    """La base tiene un diario pendiente: una ingesta anterior quedó a medias."""
