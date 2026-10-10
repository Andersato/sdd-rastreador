"""Errores controlados de la ingesta. La CLI los convierte en mensaje y código 1."""


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
