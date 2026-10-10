"""Descarga de la API del Ministerio: una sola petición, sin reintentos y con plazo total."""

import http.client
import json
import queue
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import DownloadError, DownloadTimeout, InvalidResponseError

API_URL = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/"
)
DOWNLOAD_DEADLINE_S = 120.0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_prices(
    url: str = API_URL,
    deadline_s: float = DOWNLOAD_DEADLINE_S,
    now: Callable[[], datetime] = utc_now,
) -> tuple[object, datetime]:
    """Descarga y decodifica la respuesta. Devuelve (JSON, instante de descarga).

    Toda la descarga (DNS, conexión, redirecciones y cuerpo) corre en un hilo
    *daemon*: si no termina dentro del plazo, se abandona y el proceso puede
    salir sin esperarlo. No se usa ThreadPoolExecutor porque sus hilos no son
    daemon y el intérprete los esperaría al salir.
    """
    results: queue.Queue = queue.Queue(maxsize=1)

    def worker():
        try:
            results.put(("ok", _download(url, deadline_s)))
        except BaseException as exc:  # se relanza en el hilo principal
            results.put(("error", exc))

    thread = threading.Thread(target=worker, name="price-download", daemon=True)
    thread.start()
    thread.join(timeout=deadline_s)
    if thread.is_alive():
        raise DownloadTimeout(_timeout_message(deadline_s))
    kind, value = results.get_nowait()
    if kind == "error":
        raise value
    downloaded_at = now()
    return _decode(value), downloaded_at


def _download(url: str, deadline_s: float) -> bytes:
    # El orden importa: HTTPError hereda de URLError, y URLError y
    # TimeoutError heredan de OSError.
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=deadline_s) as response:
            if response.status != 200:
                raise DownloadError(f"la descarga ha fallado con HTTP {response.status}")
            return response.read()
    except HTTPError as exc:
        exc.close()  # libera la conexión de la respuesta de error
        raise DownloadError(f"la descarga ha fallado con HTTP {exc.code}") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise DownloadTimeout(_timeout_message(deadline_s)) from exc
        raise DownloadError(f"no se ha podido conectar con la API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise DownloadTimeout(_timeout_message(deadline_s)) from exc
    except http.client.InvalidURL as exc:  # subclase de HTTPException
        raise DownloadError(f"URL no válida: {url!r}") from exc
    except http.client.HTTPException as exc:
        raise DownloadError(f"la respuesta de la API está incompleta o mal formada: {exc!r}") from exc
    except OSError as exc:
        raise DownloadError(f"error de red durante la descarga: {exc}") from exc
    except ValueError as exc:  # URL mal formada (p. ej. sin esquema)
        raise DownloadError(f"URL no válida: {url!r}") from exc


def _decode(body: bytes) -> object:
    if not body:
        raise InvalidResponseError("la respuesta de la API está vacía")
    try:
        # Se pasan bytes: json detecta UTF-8 con o sin BOM.
        return json.loads(body)
    # ValueError incluye JSONDecodeError, UnicodeDecodeError y los enteros
    # demasiado largos; RecursionError, un anidamiento excesivo.
    except (ValueError, RecursionError) as exc:
        raise InvalidResponseError(f"la respuesta de la API no es JSON válido: {exc}") from exc


def _timeout_message(deadline_s: float) -> str:
    return f"se agotó el tiempo de descarga ({deadline_s:g} s)"
