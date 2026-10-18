"""Fixtures de los tests de la web en Chromium (add-map-view, design.md D11).

- `web_server`: la app real (`create_app`) en un hilo de uvicorn, en
  `127.0.0.1` y en un puerto libre, sobre una base de prueba en `tmp_path`
  (o sin base). Nunca `./data` ni el puerto 8000.
- `web_context`: contexto de Chromium con la guarda de red. Solo deja pasar
  el origen del servidor de prueba; las teselas de OpenStreetMap se
  responden con `tests/fixtures/web/tile.png` y cualquier otra petición se
  aborta, se anota y hace fallar el test al terminar.
- `open_page`: abre la web con la ubicación simulada, el reloj de
  Playwright instalado y, si se piden, respuestas fijas de
  `tests/fixtures/web/` para rutas concretas de la API.

Chromium se lanza con `--host-resolver-rules`, así que no puede resolver
ningún nombre fuera de `127.0.0.1` (ni para el prefetch de DNS). Los tests
`browser` se saltan con aviso si su motor (WebKit o Chromium) no está
instalado. Por defecto se abren en el iPhone 13 con WebKit (design.md D11).
"""

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.helpers import check_not_real_data, free_port

FIXTURES = Path(__file__).parent / "fixtures" / "web"
TILE_URL = re.compile(r"^https://tile\.openstreetmap\.org/(\d+)/(\d+)/(\d+)\.png$")
HOST_RULES = "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"

# Ubicación simulada: sustituye `navigator.geolocation` por un objeto que
# el test controla con `window.__geo` (conceder, denegar o no responder).
GEO_SCRIPT = """
(mode) => {
  const pending = [];
  const geo = {
    calls: 0,
    grant(lat, lon) {
      while (pending.length) pending.shift().ok({coords: {latitude: lat, longitude: lon, accuracy: 20}, timestamp: Date.now()});
    },
    deny() {
      while (pending.length) pending.shift().fail({code: 1, message: 'denied', PERMISSION_DENIED: 1});
    },
  };
  window.__geo = geo;
  if (mode.kind === 'none') {
    Object.defineProperty(navigator, 'geolocation', {value: undefined, configurable: true});
    return;
  }
  const fake = {
    getCurrentPosition(ok, fail) {
      geo.calls += 1;
      pending.push({ok, fail: fail || (() => {})});
      if (mode.kind === 'grant') geo.grant(mode.lat, mode.lon);
      if (mode.kind === 'deny') geo.deny();
    },
    watchPosition() { return 0; },
    clearWatch() {},
  };
  Object.defineProperty(navigator, 'geolocation', {value: fake, configurable: true});
}
"""


def fixture_response(name: str) -> dict:
    """Respuesta fija `{"status", "headers", "body" | "body_text"}`."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def fulfill_args(spec: dict) -> dict:
    """Argumentos de `route.fulfill` para una respuesta fija."""
    headers = dict(spec.get("headers", {}))
    if "body_text" in spec:
        headers.setdefault("Content-Type", "text/html; charset=utf-8")
        body = spec["body_text"]
    else:
        headers.setdefault("Content-Type", "application/json")
        body = json.dumps(spec["body"], ensure_ascii=False)
    return {"status": spec["status"], "headers": headers, "body": body}


# --- servidor de prueba ------------------------------------------------------

class WebServer:
    """La app real en un hilo de uvicorn."""

    def __init__(self, db_path: Path, *, web_dir="default", now=None):
        import uvicorn

        from src.api.app import create_app
        from tests.api_helpers import NOW

        check_not_real_data(db_path)
        kwargs = {} if web_dir == "default" else {"web_dir": web_dir}
        clock_now = now or NOW
        app = create_app(Path(db_path), clock=lambda: clock_now,
                         log_line=lambda line: None, **kwargs)
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning",
                                access_log=False, lifespan="off")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("el servidor de prueba no arrancó")
            time.sleep(0.02)
        return self

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def web_db(tmp_path):
    """Ruta de la base de prueba (sin crear): `tmp_path/data/prices.db`."""
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


@pytest.fixture
def web_server(web_db):
    server = WebServer(web_db).start()
    yield server
    server.stop()


# --- navegador ---------------------------------------------------------------

# Dispositivos de los tests (design.md D11): (motor, opciones del contexto).
# Los descriptores de Playwright se usan tal cual, con su ventana (el área que
# deja el navegador, no la pantalla entera).
DEVICES = {
    "iphone": ("webkit", "iPhone 13"),
    "iphone_landscape": ("webkit", "iPhone 13 landscape"),
    "pixel": ("chromium", "Pixel 7"),
    "small": ("chromium", {"viewport": {"width": 320, "height": 568}, "is_mobile": True,
                           "has_touch": True, "device_scale_factor": 2}),
    "desktop": ("chromium", {"viewport": {"width": 1280, "height": 800}}),
}
TOUCH_DEVICES = ("iphone", "iphone_landscape", "pixel", "small")

# WebKit informa de una violación `style-src-attr` de la CSP que causa su propio
# <select> (también en una página que solo tiene un select). No es nuestra.
WEBKIT_SELECT_CSP = "Refused to apply a stylesheet because its hash, its nonce, or 'unsafe-inline'"


def context_options(playwright, device: str) -> dict:
    engine, spec = DEVICES[device]
    options = dict(playwright.devices[spec]) if isinstance(spec, str) else dict(spec)
    options.pop("default_browser_type", None)
    return options


_INSTALLED = {}
USED_DEVICES: set = set()


def pytest_terminal_summary(terminalreporter):
    """Escenario «Dispositivos de los tests»: qué dispositivos y motores se usaron."""
    if USED_DEVICES:
        used = ", ".join(f"{device} ({engine})" for device, engine in sorted(USED_DEVICES))
        terminalreporter.write_line(f"Dispositivos de los tests de la web: {used}")


def engine_installed(playwright, engine: str) -> bool:
    if engine not in _INSTALLED:
        try:
            _INSTALLED[engine] = Path(getattr(playwright, engine).executable_path).exists()
        except Exception:
            _INSTALLED[engine] = False
    return _INSTALLED[engine]


@pytest.fixture(scope="session")
def engines(playwright):
    """Navegadores lanzados una vez por sesión: WebKit y Chromium (este con la
    regla de resolución que impide salir del equipo)."""
    launched = {}

    def get(engine):
        if not engine_installed(playwright, engine):
            pytest.skip(f"{engine} de Playwright no instalado (.venv/bin/playwright install {engine})")
        if engine not in launched:
            args = [HOST_RULES] if engine == "chromium" else []
            launched[engine] = getattr(playwright, engine).launch(args=args)
        return launched[engine]

    yield get
    for browser in launched.values():
        browser.close()


@dataclass
class NetworkGuard:
    """Peticiones del navegador: las que llegan al servidor y las bloqueadas."""

    base: str
    requests: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    tiles: list = field(default_factory=list)

    def api_calls(self, path: str) -> list:
        """URLs pedidas a `path` del servidor (sin contar las respuestas fijas)."""
        return [r["url"] for r in self.requests
                if urlsplit(r["url"]).path == path and r["url"].startswith(self.base)]

    def check(self):
        if self.blocked:
            raise AssertionError(f"peticiones fuera del equipo bloqueadas: {self.blocked}")


@pytest.fixture
def guard_factory(engines, playwright):
    """Crea contextos del dispositivo pedido con la guarda de red sobre `base`."""
    made = []

    def make(base: str, device: str = "iphone", **context_args):
        engine, _ = DEVICES[device]
        USED_DEVICES.add((device, engine))
        options = {**context_options(playwright, device), **context_args}
        context = engines(engine).new_context(**options)
        guard = NetworkGuard(base)
        tile = (FIXTURES / "tile.png").read_bytes()

        def on_request(request):
            guard.requests.append({"url": request.url, "method": request.method,
                                   "headers": request.headers})

        def handle(route):
            url = route.request.url
            if url.startswith(base + "/"):
                route.fallback()
            elif TILE_URL.match(url):
                guard.tiles.append({"url": url, "headers": route.request.headers})
                route.fulfill(status=200, body=tile, headers={"Content-Type": "image/png"})
            else:
                guard.blocked.append(url)
                route.abort("blockedbyclient")

        context.on("request", on_request)
        context.route("**/*", handle)
        made.append((context, guard))
        return context, guard

    yield make
    for context, guard in made:
        context.close()
    for _, guard in made:
        guard.check()


class WebPage:
    """Página de la web abierta en un test, con sus utilidades."""

    def __init__(self, page, guard, base, device="iphone"):
        self.page = page
        self.guard = guard
        self.base = base
        self.device = device
        self.touch = device in TOUCH_DEVICES
        self.console_errors = []
        page.on("pageerror", lambda exc: self.console_errors.append(str(exc)))
        page.on("console", self._on_console)

    def _on_console(self, msg):
        if msg.type != "error":
            return
        if DEVICES[self.device][0] == "webkit" and msg.text.startswith(WEBKIT_SELECT_CSP):
            return
        if msg.text.startswith("Failed to load resource"):
            return  # registro del navegador de una respuesta de error, no un error de la página
        self.console_errors.append(msg.text)

    def press(self, selector):
        """Toque en los dispositivos táctiles; clic en escritorio."""
        if self.touch:
            self.page.tap(selector)
        else:
            self.page.click(selector)

    def mock(self, path: str, *specs, hold: bool = False):
        """Responde `path` de la API con respuestas fijas, en orden; la última se
        repite. Cada `spec` es el nombre de un archivo de fixtures, un dict,
        `"network_error"` (conexión rechazada) o `None` (no contesta nunca).
        Con `hold=True` las peticiones esperan hasta `mock.release()`.
        """
        return ApiMock(self, path, specs, hold)

    @property
    def geo(self):
        return GeoControl(self.page)


class ApiMock:
    """Respuestas fijas para una ruta de la API (ver `WebPage.mock`)."""

    def __init__(self, web, path, specs, hold):
        self.queue = [fixture_response(s) if isinstance(s, str) and s != "network_error" else s
                      for s in specs]
        self.calls = []
        self.held = []
        self.hold = hold
        web.page.route(re.compile(re.escape(web.base + path) + r"(\?.*)?$"), self._handle)

    def _next(self):
        return self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]

    def _answer(self, route, spec):
        if spec is None:
            return  # sin respuesta: la petición se queda colgada
        if spec == "network_error":
            route.abort("connectionrefused")
        else:
            route.fulfill(**fulfill_args(spec))

    def _handle(self, route):
        self.calls.append(route.request.url)
        spec = self._next()
        if self.hold:
            self.held.append((route, spec))
        else:
            self._answer(route, spec)

    def release(self):
        """Contesta las peticiones retenidas, en orden de llegada."""
        held, self.held = self.held, []
        for route, spec in held:
            self._answer(route, spec)


class GeoControl:
    def __init__(self, page):
        self.page = page

    def grant(self, lat, lon):
        self.page.evaluate("([a, b]) => window.__geo.grant(a, b)", [lat, lon])

    def deny(self):
        self.page.evaluate("() => window.__geo.deny()")

    @property
    def calls(self) -> int:
        return self.page.evaluate("() => window.__geo.calls")


@pytest.fixture
def open_page(guard_factory, web_server):
    """Abre la web en `device` (ver DEVICES; por defecto, el iPhone en WebKit).
    `geo`: {"kind": "pending" | "grant" | "deny" | "none", ...}.
    `before_goto(web_page)` permite registrar respuestas fijas antes de cargar."""

    def open_(path="/", *, device="iphone", geo=None, viewport=None, timezone_id="Europe/Madrid",
              clock=True, before_goto=None, init_scripts=(), server=None, goto=True):
        srv = server or web_server
        extra = {"viewport": viewport} if viewport else {}
        context, guard = guard_factory(srv.base, device, timezone_id=timezone_id, locale="es-ES",
                                       **extra)
        page = context.new_page()
        page.add_init_script(script=f"({GEO_SCRIPT})({json.dumps(geo or {'kind': 'pending'})})")
        for script in init_scripts:
            page.add_init_script(script=script)
        web = WebPage(page, guard, srv.base, device)
        if clock:
            page.clock.install()
        if before_goto:
            before_goto(web)
        if goto:
            page.goto(srv.base + path)
        return web

    return open_
