"""«Página servida en la raíz» (map-view) y el delta de prices-api con la web
montada: la página y sus archivos en `/`, y `/api/*` igual que antes."""

import json
import time

import pytest

from src.api.web import CONTENT_SECURITY_POLICY
from tests.api_helpers import ATTRIBUTION, assert_error, basic_db, hold_lock, make_client

WEB_HEADERS = ("Cache-Control", "X-Content-Type-Options", "Referrer-Policy",
               "Content-Security-Policy")


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


@pytest.fixture
def client(db):
    basic_db(db)
    return make_client(db)


@pytest.fixture
def no_web(db):
    """La misma API sin la web montada: lo que había antes de este cambio."""
    basic_db(db)
    return make_client(db, web_dir=None)


# --- Página servida en la raíz ----------------------------------------------

def test_open_the_page(client):
    """Escenario: Abrir la página."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert '<html lang="es">' in response.text
    assert "<title>Gasolineras baratas cerca</title>" in response.text


def test_head_of_the_page(client):
    """Escenario: HEAD de la página."""
    response = client.head("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == client.get("/").headers["content-type"]
    assert response.content == b""


def test_favicon(client):
    """Escenario: Favicon."""
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_page_without_database(tmp_path):
    """Escenario: Página sin base."""
    folder = tmp_path / "data"
    folder.mkdir()
    client = make_client(folder / "prices.db")
    assert client.get("/").status_code == 200
    assert_error(client.get("/api/fuels"), 503, "sin_base")
    assert list(folder.iterdir()) == []


def test_page_with_busy_database(db, client):
    """Escenario: Página con la base ocupada."""
    with hold_lock(db, 4):
        started = time.monotonic()
        response = client.get("/")
        elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed < 0.5


def test_trailing_slash_in_api_route(client, no_web):
    """Escenario: Barra final en una ruta de la API."""
    response = client.get("/api/fuels/", follow_redirects=False)
    before = no_web.get("/api/fuels/", follow_redirects=False)
    assert (response.status_code, before.status_code) == (307, 307)
    assert response.headers["location"] == before.headers["location"] == "http://testserver/api/fuels"


def test_trailing_slash_keeps_the_query(client, no_web):
    response = client.get("/api/fuels/?fuel=x", follow_redirects=False)
    before = no_web.get("/api/fuels/?fuel=x", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == before.headers["location"]
    assert response.headers["location"].endswith("/api/fuels?fuel=x")


def test_missing_file(client):
    """Escenario: Archivo inexistente."""
    assert_error(client.get("/no-existe.js"), 404, "no_encontrado")


def test_folder(client):
    """Escenario: Carpeta."""
    response = client.get("/vendor/leaflet/")
    assert_error(response, 404, "no_encontrado")
    assert "leaflet.js" not in response.text


@pytest.mark.parametrize("path", ["/..%2Fsrc%2Fapi%2Fapp.py", "/%2e%2e/requirements.txt",
                                  "/../src/api/app.py"])
def test_cannot_leave_web_folder(client, path):
    """Escenario: Intento de salir de web/."""
    response = client.get(path)
    assert_error(response, 404, "no_encontrado")
    assert "create_app" not in response.text
    assert "fastapi==" not in response.text


def test_other_method_on_the_page(client):
    """Escenario: Otro método en la página."""
    response = client.post("/")
    body = assert_error(response, 405, "metodo_no_permitido")
    assert response.headers["allow"] == "GET, HEAD"
    assert body["error"]["message"] == "solo se admiten GET y HEAD"


def test_post_to_missing_file(client):
    """design.md D3: el método se mira antes que el archivo."""
    response = client.post("/no-existe.js")
    body = assert_error(response, 405, "metodo_no_permitido")
    assert response.headers["allow"] == "GET, HEAD"
    assert body["error"]["message"] == "solo se admiten GET y HEAD"


def test_head_of_missing_file(client):
    """design.md D3: 404, comprobado por estado y cabeceras."""
    response = client.head("/no-existe.js")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"


def test_head_in_the_api(client, no_web):
    """Escenarios: HEAD en la API (map-view y prices-api)."""
    for c in (client, no_web):
        response = c.head("/api/fuels")
        assert response.status_code == 405
        assert response.headers["allow"] == "GET"


@pytest.mark.parametrize(("method", "path"), [("POST", "/api/fuels"),
                                              ("DELETE", "/api/stations/4375")])
def test_api_method_not_allowed_unchanged(client, no_web, method, path):
    """«Método no permitido» de prices-api, igual con la web montada."""
    with_web = client.request(method, path)
    before = no_web.request(method, path)
    assert with_web.status_code == before.status_code == 405
    assert with_web.headers["allow"] == before.headers["allow"] == "GET"
    assert with_web.json() == before.json()


@pytest.mark.parametrize("path", ["/api/precios", "/api/stations/4375/precios", "/api/"])
def test_api_unknown_route_unchanged(client, no_web, path):
    with_web = client.get(path, follow_redirects=False)
    before = no_web.get(path, follow_redirects=False)
    assert (with_web.status_code, with_web.content) == (before.status_code, before.content)


def test_the_api_stays_the_same(client, no_web):
    """Escenario: La API sigue igual."""
    for path in ("/api/fuels", "/api/health", "/api/stations/4375",
                 "/api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=gasoleo-a",
                 "/api/provinces/prices?fuel=gasoleo-a"):
        with_web, before = client.get(path), no_web.get(path)
        assert (with_web.status_code, with_web.json()) == (before.status_code, before.json()), path
    assert set(client.get("/api/openapi.json").json()["paths"]) == {
        "/api/health", "/api/fuels", "/api/stations/nearby", "/api/stations/{station_id}",
        "/api/provinces/prices"}


# --- delta de prices-api ------------------------------------------------------

def test_unknown_route_outside_api(client):
    """Escenario: Ruta inexistente (`GET /precios`)."""
    body = assert_error(client.get("/precios"), 404, "no_encontrado")
    assert body["attribution"] == ATTRIBUTION


def test_the_page_is_not_json(client):
    """Escenario: La página no es JSON."""
    response = client.get("/")
    assert response.headers["content-type"].startswith("text/html")
    try:
        body = json.loads(response.text)
    except ValueError:
        body = None
    assert not isinstance(body, dict)  # ni attribution, ni capture, ni data en JSON


def test_the_page_is_not_in_the_documentation(client):
    """Escenario: La página no está en la documentación."""
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/" not in paths
    assert not any("favicon" in p or p.endswith(".js") for p in paths)


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_no_documentation_at_the_root_with_web(client, path):
    """Escenario: Sin documentación en la raíz, con la web montada."""
    assert_error(client.get(path), 404, "no_encontrado")


# --- cabeceras (design.md D3 y D4) ---------------------------------------------

@pytest.mark.parametrize("path", ["/", "/favicon.ico"])
def test_web_headers(client, path):
    headers = client.get(path).headers
    assert headers["cache-control"] == "no-cache"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "etag" in headers


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/api/docs"), ("GET", "/api/fuels"), ("GET", "/api/precios"),
    ("HEAD", "/api/fuels"), ("GET", "/api/fuels/")])
def test_api_responses_have_no_web_headers(client, method, path):
    headers = client.request(method, path, follow_redirects=False).headers
    for name in WEB_HEADERS:
        assert name.lower() not in headers, (path, name)


def test_without_web_folder(db):
    """design.md D3: con `web_dir=None` o una carpeta que no existe, no se monta nada."""
    basic_db(db)
    for web_dir in (None, db.parent / "no-existe"):
        client = make_client(db, web_dir=web_dir)
        assert_error(client.get("/"), 404, "no_encontrado")
        assert client.get("/api/fuels").status_code == 200
