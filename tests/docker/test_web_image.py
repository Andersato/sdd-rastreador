"""«Web incluida en la imagen» (map-view): la imagen lleva `web/` con Leaflet y
su licencia, y el servicio `api` sirve la página en `/` sin publicar ningún
puerto nuevo.

La API va en un puerto libre (nunca el 8000 real); que el puerto publicado
sea exactamente `127.0.0.1:8000` lo comprueba `test_api_compose.py` con el
`docker-compose.yml` real.
"""

import json
import urllib.request

from tests.docker.helpers import API
from tests.docker.test_image import in_image


def test_page_from_the_container(project, http_server):
    """Escenario: Página desde el contenedor (`./data` vacía)."""
    project.start_services(http_server)
    project.wait_api()
    with urllib.request.urlopen(project.api_url + "/", timeout=5) as response:
        assert response.status == 200
        assert response.headers["Content-Type"] == "text/html; charset=utf-8"
        assert "<title>Gasolineras baratas cerca</title>" in response.read().decode()
    assert project.api_get("/api/fuels")[0] == 503  # sin base: sigue igual
    assert list(project.data.iterdir()) == []


def test_no_new_published_port(project):
    result = project.compose("config", "--format", "json", timeout=60)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    published = [(name, port) for name, service in services.items()
                 for port in service.get("ports", [])]
    assert len(published) == 1
    name, port = published[0]
    assert name == API and port["host_ip"] == "127.0.0.1"


def test_image_contains_the_web_and_leaflet_license(image):
    for path in ("/app/web/index.html", "/app/web/vendor/leaflet/LICENSE",
                 "/app/web/vendor/leaflet/VERSION", "/app/web/vendor/leaflet/leaflet.js"):
        result = in_image(image, "test", "-f", path)
        assert result.returncode == 0, path


def test_playwright_is_not_in_the_image(image):
    result = in_image(image, "python", "-c", "import playwright")
    assert result.returncode != 0
    assert "No module named 'playwright'" in result.stderr
