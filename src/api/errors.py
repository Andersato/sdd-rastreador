"""Errores de la API con su código estable y su mensaje en español."""


class ApiError(Exception):
    """Error que se responde con el formato común: `{"error": {code, message}}`."""

    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}


def unavailable(code: str, message: str, headers: dict | None = None) -> ApiError:
    return ApiError(503, code, message, headers)


def invalid_parameter(message: str) -> ApiError:
    return ApiError(422, "parametro_no_valido", message)


def unknown_fuel(value: str) -> ApiError:
    return ApiError(422, "combustible_desconocido",
                    f"combustible desconocido: {value!r}; los identificadores válidos "
                    "están en /api/fuels")
