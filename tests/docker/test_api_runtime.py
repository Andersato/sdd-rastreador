"""Servicio `api` en marcha en Docker: escenarios de prices-api
que faltaban por comprobar con el contenedor real.

- «Log de la API limitado y sin ubicaciones exactas»: el log de verdad del
  contenedor (`docker compose logs api`), no solo la línea que genera la app.
- «Servicio api que se arranca con el programador», escenario Parada, con
  `docker compose stop` de todo el proyecto.

Proyectos temporales con la API en un puerto libre (nunca el 8000 real) y el
programador contra el servidor local.
"""

import json
import time

from tests.api_helpers import folder_state
from tests.docker.helpers import API
from tests.docker.test_scheduler import seed, wait_until

NEARBY = "/api/stations/nearby?lat=40.416775&lon=-3.703790&fuel=gasoleo-a"
BAD_NEARBY = "/api/stations/nearby?lat=40,416775&lon=-3.703790&fuel=gasoleo-a"


def all_containers(project):
    """(servicio, estado) de todos los contenedores del proyecto, también parados."""
    result = project.compose("ps", "-a", "--format", "json", timeout=60)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return sorted((row["Service"], row["State"]) for row in rows)


def test_search_in_the_container_log(project, http_server):
    """Escenarios: Búsqueda en el log y Coordenadas no válidas en el log (log real
    del contenedor: coordenadas redondeadas y nunca las exactas)."""
    seed(project, hours_ago=1)
    project.start_services(http_server)
    project.wait_api()
    status, _ = project.api_get(NEARBY)
    assert status == 200
    status, _ = project.api_get(BAD_NEARBY)
    assert status == 422

    def lines():
        return [line for line in project.api_logs().splitlines()
                if "GET /api/stations/nearby" in line]

    assert wait_until(lambda: len(lines()) >= 2, 30), project.api_logs()
    ok_line = next(line for line in lines() if "→ 200" in line)
    assert "lat=40.42" in ok_line and "lon=-3.70" in ok_line and "fuel=gasoleo-a" in ok_line
    bad_line = next(line for line in lines() if "→ 422" in line)
    assert "40,416775" not in bad_line and "-3.703790" not in bad_line
    log = project.api_logs()
    for exact in ("40.416775", "-3.703790", "40,416775", "-3.70379"):
        assert exact not in log, exact


def test_compose_stop_stops_the_api_quickly(project, http_server):
    """Escenario: Parada (`docker compose stop`: la API se para en menos de 10 s y
    ./data queda exactamente igual)."""
    seed(project, hours_ago=1)
    project.start_services(http_server)
    project.wait_api()
    project.wait_startup()
    assert project.api_get("/api/fuels")[0] == 200
    before = folder_state(project.data)
    started = time.monotonic()
    result = project.compose("stop", timeout=60)
    elapsed = time.monotonic() - started
    assert result.returncode == 0, result.stderr
    assert elapsed < 10
    assert dict(all_containers(project))[API] == "exited"
    assert folder_state(project.data) == before
