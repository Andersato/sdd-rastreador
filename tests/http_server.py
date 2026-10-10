"""Servidor HTTP local para los tests: sustituye a la API del Ministerio.

Cada ruta se configura con `add(path, ...)` y el servidor cuenta las
peticiones recibidas por ruta, para comprobar que no hay reintentos.
"""

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

# Modos de respuesta
NORMAL = "normal"                    # estado + cuerpo completos
TRUNCATED_LENGTH = "truncated_length"  # Content-Length mayor que el cuerpo
TRUNCATED_CLOSE = "truncated_close"    # sin Content-Length, corta a mitad
HANG = "hang"                        # acepta la petición y nunca responde
SLOW = "slow"                        # cabeceras y luego un byte cada `delay` s


@dataclass
class Route:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    mode: str = NORMAL
    delay: float = 0.3


class LocalServer:
    def __init__(self):
        self.routes: dict[str, Route] = {}
        self.requests: dict[str, int] = {}
        self.received_headers: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def add(self, path, status=200, body=b"", headers=None, mode=NORMAL, delay=0.3):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.routes[path] = Route(status, body, dict(headers or {}), mode, delay)
        return self.url(path)

    def add_fixture(self, path, fixture_name, **kwargs):
        return self.add(path, body=(FIXTURES / fixture_name).read_bytes(), **kwargs)

    def count(self, path: str) -> int:
        return self.requests.get(path, 0)

    def total_requests(self) -> int:
        return sum(self.requests.values())

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._httpd.shutdown()
        self._httpd.server_close()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                with server._lock:
                    server.requests[self.path] = server.requests.get(self.path, 0) + 1
                    server.received_headers[self.path] = dict(self.headers)
                route = server.routes.get(self.path)
                if route is None:
                    self.send_error(404)
                    return
                if route.mode == HANG:
                    server._stop.wait(timeout=30)
                    self.close_connection = True
                    return
                self.send_response(route.status)
                for name, value in route.headers.items():
                    self.send_header(name, value)
                if route.mode == TRUNCATED_CLOSE:
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(route.body[: len(route.body) // 2])
                    self.close_connection = True
                    return
                declared = len(route.body)
                if route.mode == TRUNCATED_LENGTH:
                    declared += 100
                self.send_header("Content-Length", str(declared))
                self.end_headers()
                if route.mode == SLOW:
                    for byte in route.body:
                        if server._stop.is_set():
                            break
                        try:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                        except OSError:
                            break
                        time.sleep(route.delay)
                    self.close_connection = True
                    return
                self.wfile.write(route.body)
                if route.mode == TRUNCATED_LENGTH:
                    self.close_connection = True

        return Handler
