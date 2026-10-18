"""Utilidades de los tests de la web: la guarda de red bloquea lo que sale del
equipo y deja llegar al servidor de prueba (add-map-view, tarea 1.3)."""

import pytest

from tests.web_fixtures import FIXTURES

pytestmark = pytest.mark.browser

HARNESS = "/__harness__.html"


@pytest.fixture
def blank(open_page):
    def serve(web):
        web.page.route(web.base + HARNESS, lambda route: route.fulfill(
            status=200, body="<!doctype html><title>t</title>", content_type="text/html"))
    return open_page(HARNESS, before_goto=serve, clock=False)


def test_outside_request_is_blocked_and_fails(blank):
    blank.page.evaluate("() => fetch('https://example.org/').catch(() => 'bloqueada')")
    assert blank.guard.blocked == ["https://example.org/"]
    with pytest.raises(AssertionError, match="example.org"):
        blank.guard.check()
    blank.guard.blocked.clear()  # ya comprobado: que no falle al cerrar


def test_api_request_reaches_test_server(blank):
    status = blank.page.evaluate("() => fetch('/api/health').then(r => r.status)")
    assert status == 503  # base de prueba sin crear: sin_base
    assert blank.guard.api_calls("/api/health")


def test_tiles_are_served_locally(blank):
    size = blank.page.evaluate(
        "() => fetch('https://tile.openstreetmap.org/5/15/12.png').then(r => r.blob()).then(b => b.size)")
    assert size == (FIXTURES / "tile.png").stat().st_size
    assert blank.guard.tiles[0]["url"] == "https://tile.openstreetmap.org/5/15/12.png"
    assert not blank.guard.blocked
