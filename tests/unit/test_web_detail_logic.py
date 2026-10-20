"""Unitarios de la ficha completa (add-station-detail): la lógica pura de
`web/js/logic.js` (design.md D2 a D5) y el cargador de `web/js/detail.js` (D6).

Se cargan desde una página vacía, como `test_web_logic.py`. Corren en
Chromium; los de fechas, también en WebKit.
"""

import pytest

from tests.unit.test_web_logic import HARNESS, Module, serve_blank
from tests.web_helpers import UA_IPADOS, UA_LINUX_CHROME, UA_MAC_SAFARI

pytestmark = pytest.mark.browser

ENGINES = pytest.mark.parametrize("device", ["desktop", "iphone"], ids=["chromium", "webkit"])


@pytest.fixture
def logic_in(open_page):
    def make(timezone_id="Europe/Madrid", device="desktop"):
        web = open_page(HARNESS, device=device, before_goto=serve_blank, clock=False,
                        timezone_id=timezone_id)
        return Module(web, "/js/logic.js")
    return make


@pytest.fixture
def logic(logic_in):
    return logic_in()


def price(slug, name, value, unit="€/l"):
    return {"slug": slug, "name": name, "unit": unit, "kind": "combustible", "price": value}


def body(data, capture=None):
    result = {"attribution": "x", "data": data}
    if capture is not None:
        result["capture"] = capture
    return result


def station(prices, sid="4375", schedule="L-D: 24H", **extra):
    return {"id": sid, "brand": "REPSOL", "schedule": schedule, "prices": prices, **extra}


# --- 2.1 Horario tal como lo publica el Ministerio ----------------------------

@pytest.mark.parametrize(("schedule", "lines"), [
    ("L-J: 06:00-22:30; V: 06:00-23:00; S: 06:45-23:00; D: 07:45-22:30",
     ["L-J: 06:00-22:30", "V: 06:00-23:00", "S: 06:45-23:00", "D: 07:45-22:30"]),
    ("L-D: 24H", ["L-D: 24H"]),
    ("L-V: 09:00-13:30 y 16:00-18:30; S: 09:00-13:30",
     ["L-V: 09:00-13:30 y 16:00-18:30", "S: 09:00-13:30"]),
    ("L: 24H", ["L: 24H"]),
    ("L-V: 07:00-22:00;;  S: 08:00-14:00 ; ", ["L-V: 07:00-22:00", "S: 08:00-14:00"]),
    ("L: 06:30-22:30; M-D: 06:30-14:29 y 14:30-22:30 (festivos cerrado)",
     ["L: 06:30-22:30", "M-D: 06:30-14:29 y 14:30-22:30 (festivos cerrado)"]),
    ("\tL-D: 24H ", ["L-D: 24H"]),
    (None, []), (";", []), (24, []), ("", []), ("  ", []),
], ids=["varios", "uno", "dos-franjas", "L-24H", "vacios", "raro", "tab-nbsp", "null", "punto-coma",
        "numero", "vacio", "espacios"])
def test_schedule_lines(logic, schedule, lines):
    """Escenarios de «Horario tal como lo publica el Ministerio»."""
    assert logic.scheduleLines(schedule) == lines


# --- 2.2 Respuesta del detalle y orden de los precios ---------------------------

ADBLUE = price("adblue", "Adblue", 0.899)
GASOLEO = price("gasoleo-a", "Gasoleo A", 1.459)
E5 = price("gasolina-95-e5", "Gasolina 95 E5", 1.529)


def slugs(result):
    return [(p["slug"], p["searched"]) for p in result["prices"]]


def test_searched_first(logic):
    """Escenario: Buscado el primero."""
    result = logic.parseDetail(body(station([ADBLUE, GASOLEO, E5])), "4375", "gasolina-95-e5")
    assert result["ok"] is True
    assert slugs(result) == [("gasolina-95-e5", True), ("adblue", False), ("gasoleo-a", False)]


def test_other_unit(logic):
    """Escenario: Otra unidad (los datos pasan tal cual)."""
    hydrogen = price("hidrogeno", "Hidrogeno", 12.95, "€/kg")
    result = logic.parseDetail(body(station([GASOLEO, hydrogen])), "4375", "gasoleo-a")
    assert [(p["name"], p["price"], p["unit"]) for p in result["prices"]] == [
        ("Gasoleo A", 1.459, "€/l"), ("Hidrogeno", 12.95, "€/kg")]


def test_no_prices(logic):
    """Escenario: Sin precios (lista vacía válida)."""
    result = logic.parseDetail(body(station([])), "4375", "gasoleo-a")
    assert result == {"ok": True, "lines": ["L-D: 24H"], "prices": [], "capture": None}


def test_searched_fuel_missing(logic):
    """Escenario: El buscado ya no aparece."""
    result = logic.parseDetail(body(station([E5])), "4375", "gasoleo-a")
    assert slugs(result) == [("gasolina-95-e5", False)]


def test_invalid_items_are_ignored(logic):
    """Escenario: Elementos no válidos."""
    items = [GASOLEO, {**E5, "name": None}, {**E5, "price": None}, {**E5, "price": "1,5"},
             {**E5, "price": 0}, {**E5, "slug": "  "}, {**E5, "unit": 3}, None, "x",
             {**E5, "price": -1}]
    result = logic.parseDetail(body(station(items)), "4375", "gasoleo-a")
    assert slugs(result) == [("gasoleo-a", True)]


def test_no_valid_price_is_unexpected(logic):
    """Escenario: Ningún precio válido."""
    items = [{**GASOLEO, "name": None}, {**E5, "price": None}]
    assert logic.parseDetail(body(station(items)), "4375", "gasoleo-a") == {"ok": False}


@pytest.mark.parametrize("prices", [None, {"gasoleo-a": 1.459}, "x"], ids=["null", "objeto", "texto"])
def test_prices_that_are_not_a_list(logic, prices):
    """Escenario: Precios no es una lista."""
    assert logic.parseDetail(body(station(prices)), "4375", "gasoleo-a") == {"ok": False}


def test_prices_missing(logic):
    """Escenario: Precios no es una lista (`data` sin `prices`)."""
    data = station([])
    del data["prices"]
    assert logic.parseDetail(body(data), "4375", "gasoleo-a") == {"ok": False}


@pytest.mark.parametrize("data", [None, "x", [1, 2], 3], ids=["null", "texto", "lista", "numero"])
def test_data_that_is_not_an_object(logic, data):
    """Escenario: Respuesta que no es JSON (200 con `data` que no es un objeto)."""
    assert logic.parseDetail(body(data), "4375", "gasoleo-a") == {"ok": False}


@pytest.mark.parametrize("sid", ["1002", 1001, None], ids=["otro", "numero", "sin-id"])
def test_other_identifier(logic, sid):
    """Escenario: Respuesta con otro identificador."""
    data = station([GASOLEO], sid=sid)
    if sid is None:
        del data["id"]
    assert logic.parseDetail(body(data), "1001", "gasoleo-a") == {"ok": False}


def test_repeated_searched_slug(logic):
    """Si el `slug` buscado se repite, solo el primero va arriba y marcado."""
    second = {**GASOLEO, "price": 1.469}
    result = logic.parseDetail(body(station([E5, GASOLEO, second])), "4375", "gasoleo-a")
    assert [(p["slug"], p["price"], p["searched"]) for p in result["prices"]] == [
        ("gasoleo-a", 1.459, True), ("gasolina-95-e5", 1.529, False),
        ("gasoleo-a", 1.469, False)]


def test_capture_and_schedule_are_returned(logic):
    capture = {"downloaded_at": "2026-10-16T07:26:37Z"}
    result = logic.parseDetail(body(station([GASOLEO], schedule=None), capture), "4375", "x")
    assert result["lines"] == [] and result["capture"] == capture


# --- 2.3 Captura del detalle más nueva -----------------------------------------

OLD = {"downloaded_at": "2026-10-16T07:26:37Z"}
NEW = {"downloaded_at": "2026-10-16T08:26:40Z"}


@ENGINES
def test_newer_capture(logic_in, device):
    """Escenario: Captura nueva entre la búsqueda y la ficha (navegador en UTC)."""
    logic = logic_in("UTC", device)
    assert logic.newerCaptureText(OLD, NEW) == (
        "Horario y precios de una captura más reciente: del 16/10/2026 a las 10:26 "
        "(hora de Madrid)")


@pytest.mark.parametrize(("search", "detail"), [
    (OLD, OLD),
    (OLD, None), (OLD, {}), (OLD, {"downloaded_at": "ayer"}),
    (NEW, OLD),
    (None, NEW), ({"downloaded_at": "ayer"}, NEW),
], ids=["misma", "detalle-sin-captura", "detalle-vacia", "detalle-ayer", "anterior",
        "busqueda-sin-fecha", "busqueda-ayer"])
@ENGINES
def test_no_newer_capture_notice(logic_in, device, search, detail):
    """Escenarios: Misma captura, desconocida, anterior y búsqueda sin fecha."""
    assert logic_in("UTC", device).newerCaptureText(search, detail) is None


# --- 2.4 Aplicación de mapas y enlace -------------------------------------------

@pytest.fixture
def device_agents(playwright):
    return {"iphone": playwright.devices["iPhone 13"]["user_agent"],
            "pixel": playwright.devices["Pixel 7"]["user_agent"]}


def test_maps_provider(logic, device_agents):
    """Escenarios de «Enlace «Cómo llegar» según el dispositivo»."""
    assert logic.mapsProvider(device_agents["iphone"]) == "apple"
    assert logic.mapsProvider(device_agents["pixel"]) == "google"
    assert logic.mapsProvider(UA_MAC_SAFARI) == "apple"
    assert logic.mapsProvider(UA_IPADOS) == "apple"
    assert logic.mapsProvider(UA_LINUX_CHROME) == "osm"
    assert logic.mapsProvider("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)") == "apple"
    assert logic.mapsProvider("Mozilla/5.0 (iPod touch; CPU iPhone OS 15_0)") == "apple"
    assert logic.mapsProvider("") == "osm"
    assert logic.mapsProvider(None) == "osm"


def test_maps_provider_ignores_case(logic, device_agents):
    assert logic.mapsProvider(device_agents["iphone"].upper()) == "apple"
    assert logic.mapsProvider(device_agents["pixel"].upper()) == "google"
    assert logic.mapsProvider("Mozilla/5.0 (MACINTOSH; Intel Mac OS X)") == "apple"
    assert logic.mapsProvider("mozilla/5.0 (linux; android 14; pixel 7)") == "google"


def test_android_wins_over_other_words(logic):
    assert logic.mapsProvider("Mozilla/5.0 (Linux; Android 14) like iPhone Macintosh") == "google"


@pytest.mark.parametrize(("provider", "lat", "lon", "href", "name"), [
    ("apple", 40.44, -3.73, "https://maps.apple.com/?daddr=40.44,-3.73", "Apple Maps"),
    ("google", 40.44, -3.73,
     "https://www.google.com/maps/dir/?api=1&destination=40.44,-3.73", "Google Maps"),
    ("osm", 40.44, -3.73,
     "https://www.openstreetmap.org/directions?route=%3B40.44%2C-3.73", "OpenStreetMap"),
    ("apple", 40.416775, -3.70379, "https://maps.apple.com/?daddr=40.416775,-3.70379",
     "Apple Maps"),
])
def test_directions_link(logic, provider, lat, lon, href, name):
    """Escenarios: URLs exactas, muchos decimales y nombres accesibles."""
    assert logic.directionsLink(provider, lat, lon) == {
        "href": href, "label": f"Cómo llegar con {name} (se abre en otra pestaña)"}


def test_directions_shortest_numbers(logic):
    """40.4400 → 40.44 (escritura más corta del número)."""
    assert logic.directionsLink("apple", 40.4400, -3.7000)["href"] == (
        "https://maps.apple.com/?daddr=40.44,-3.7")


def test_is_text_is_exported(logic):
    assert logic.isText("4375") is True
    assert [logic.isText(x) for x in ["", "  ", 4375, None]] == [False, False, False, False]


# --- 3.1 Cargador de detalles (detail.js) y texto de los errores -----------------

# `fetchOne` falso: cada petición queda pendiente hasta `answer(i, result)`;
# `t.now` es el reloj. Todo vive en `window.t` de la página vacía.
LOADER = """async () => {
  const {createDetailLoader} = await import('/js/detail.js');
  const t = {calls: [], pending: [], changes: [], now: 1000};
  t.loader = createDetailLoader({
    fetchOne: (path, signal) => new Promise((resolve) => {
      t.calls.push(path);
      t.pending.push({resolve, signal});
    }),
    now: () => t.now,
    onChange: (id) => t.changes.push(id),
  });
  t.answer = async (i, result) => { t.pending[i].resolve(result); await new Promise(r => setTimeout(r, 0)); };
  window.t = t;
}"""


def ok_body(sid="4375", prices=None):
    return {"kind": "ok", "body": body(station([GASOLEO, E5] if prices is None else prices,
                                                sid=sid))}


@pytest.fixture
def loader(open_page):
    web = open_page(HARNESS, device="desktop", before_goto=serve_blank, clock=False)
    web.page.evaluate(LOADER)
    web.page.evaluate("() => window.t.loader.reset('gasoleo-a')")
    return web.page


def js(page, code, arg=None):
    return page.evaluate(f"async (arg) => {{ const t = window.t; {code} }}", arg)


def test_one_request_per_station(loader):
    """Una sola petición por `id`, también al reabrir mientras carga."""
    first = js(loader, "return t.loader.open({id: '4375'}).status;")
    again = js(loader, "return t.loader.open({id: '4375'}).status;")
    assert (first, again) == ("loading", "loading")
    js(loader, "await t.answer(0, arg);", ok_body())
    entry = js(loader, "return t.loader.open({id: '4375'});")
    assert entry["status"] == "ok"
    assert [p["slug"] for p in entry["result"]["prices"]] == ["gasoleo-a", "gasolina-95-e5"]
    assert entry["result"]["prices"][0]["searched"] is True  # combustible guardado en reset
    assert js(loader, "return t.calls;") == ["/api/stations/4375"]
    assert js(loader, "return t.changes;") == ["4375"]


def test_reopen_after_error_does_not_request(loader):
    """Reabrir una ficha con error no pide nada."""
    js(loader, "t.loader.open({id: '4375'}); await t.answer(0, {kind: 'unreachable'});")
    entry = js(loader, "return t.loader.open({id: '4375'});")
    assert entry["status"] == "error" and entry["result"] == {"kind": "unreachable"}
    assert js(loader, "return t.calls.length;") == 1


def test_reset_aborts_and_discards_old_generation(loader):
    """`reset` aborta lo que está en camino y una respuesta vieja no cambia nada."""
    js(loader, "t.loader.open({id: '4375'});")
    aborted = js(loader, "t.loader.reset('gasoleo-a'); return t.pending[0].signal.aborted;")
    assert aborted is True
    js(loader, "t.loader.open({id: '4375'});")  # búsqueda nueva: petición nueva
    js(loader, "await t.answer(0, arg);", ok_body(prices=[E5]))  # la vieja llega después
    assert js(loader, "return t.loader.get('4375').status;") == "loading"
    assert js(loader, "return t.changes;") == []
    js(loader, "await t.answer(1, arg);", ok_body())
    assert js(loader, "return t.loader.get('4375').status;") == "ok"
    assert js(loader, "return t.calls;") == ["/api/stations/4375", "/api/stations/4375"]


def test_aborted_result_is_ignored(loader):
    js(loader, "t.loader.open({id: '4375'}); await t.answer(0, {kind: 'aborted'});")
    assert js(loader, "return t.loader.get('4375').status;") == "loading"


def test_retry_respects_retry_after_and_double_tap(loader):
    """`retry` no hace nada antes de `retryAt` ni con dos toques seguidos."""
    js(loader, "t.loader.open({id: '4375'}); await t.answer(0, {kind: 'busy', seconds: 5});")
    entry = js(loader, "return t.loader.get('4375');")
    assert entry["status"] == "error" and entry["retryAt"] == 6000
    js(loader, "t.now = 5999; t.loader.retry('4375');")
    assert js(loader, "return t.calls.length;") == 1
    statuses = js(loader, "t.now = 6000; const a = t.loader.retry('4375').status;"
                          " const b = t.loader.retry('4375').status; return [a, b];")
    assert statuses == ["loading", "loading"]
    assert js(loader, "return t.calls.length;") == 2


def test_retry_after_rejected_ok_response(loader):
    """Un 200 que `parseDetail` rechaza queda en error reintentable."""
    js(loader, "t.loader.open({id: '1001'}); await t.answer(0, arg);", ok_body(sid="1002"))
    entry = js(loader, "return t.loader.get('1001');")
    assert entry["status"] == "error" and entry["result"] == {"kind": "unexpected"}
    assert entry["retryable"] is True
    js(loader, "t.loader.retry('1001');")
    assert js(loader, "return t.calls.length;") == 2


@pytest.mark.parametrize("sid", ["", "  ", 4375], ids=["vacio", "espacios", "numero"])
def test_invalid_identifier_does_not_request(loader, sid):
    """Escenario: Gasolinera de la búsqueda sin identificador válido."""
    entry = js(loader, "return t.loader.open({id: arg});", sid)
    assert entry == {"status": "error", "result": {"kind": "unexpected"}, "retryAt": 0,
                     "retryable": False}
    assert js(loader, "return t.calls;") == []


def test_path_is_encoded(loader):
    """Escenario: Identificador con caracteres especiales."""
    js(loader, "t.loader.open({id: '12/3?x'});")
    assert js(loader, "return t.calls;") == ["/api/stations/12%2F3%3Fx"]


@pytest.mark.parametrize(("result", "text"), [
    ({"kind": "busy", "seconds": 5}, "El servidor está ocupado; inténtalo en unos segundos"),
    ({"kind": "no_data", "message": "todavía no hay capturas guardadas"},
     "No hay datos disponibles. Detalle: todavía no hay capturas guardadas"),
    ({"kind": "no_data", "message": None}, "No hay datos disponibles."),
    ({"kind": "unreachable"}, "No se puede conectar con el servidor. Comprueba que está en "
                              "marcha y que el túnel está abierto."),
    ({"kind": "server_error"}, "El servidor ha dado un error. Inténtalo más tarde."),
    ({"kind": "unknown_fuel"}, "El servidor ha dado un error. Inténtalo más tarde."),
    ({"kind": "outside_spain"}, "El servidor ha dado un error. Inténtalo más tarde."),
    ({"kind": "unexpected"}, "El servidor ha dado una respuesta inesperada"),
])
def test_error_text(open_page, result, text):
    web = open_page(HARNESS, device="desktop", before_goto=serve_blank, clock=False)
    got = web.page.evaluate(
        "async (r) => (await import('/js/view.js')).errorText(r)", result)
    assert got == text
