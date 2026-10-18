"""«Cómo abrir la web en el README» (map-view): se lee la sección de la web y
la de los tests. Solo se comprueba lo que se puede comprobar con texto."""

import re

import pytest

from tests.helpers import REPO_ROOT

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def section(title):
    assert title in README, title
    body = README.split(title, 1)[1]
    body = re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]
    return re.sub(r"\s+", " ", body)  # sin saltos de línea del Markdown


@pytest.fixture(scope="module")
def web():
    return section("## Web del mapa")


def test_reading_the_readme(web):
    """Escenario: Lectura del README."""
    assert "http://127.0.0.1:8000/" in web
    assert "ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>" in web
    assert "-L 8001:127.0.0.1:8000" in web and "http://127.0.0.1:8001/" in web
    assert "necesita conexión" in web and "internet" in web.lower() and "OpenStreetMap" in web
    assert "solo se envían a la" in web and "unos 100 m" in web and "no se guardan" in web
    assert "teselas de la zona que se ve" in web


def test_test_browsers():
    """Escenario: Navegadores de los tests."""
    tests = section("## Tests")
    assert ".venv/bin/playwright install chromium" in tests
    assert ".venv/bin/playwright install webkit" in tests


def test_ios_simulator(web):
    """Escenario: Simulador de iOS."""
    assert "Simulador de iOS" in web and "opcional" in web
    assert "http://127.0.0.1:8000/" in web and "Features → Location" in web
    assert "vertical y en horizontal" in web and "muesca" in web and "barra" in web
