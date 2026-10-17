"""`COLLECTION_ENABLED` en el programador real (`scheduled-collection`):
"Recogida habilitada explícitamente en una sola máquina", "Cambio de la
variable de recogida" y "Comprobación al arrancar y cada hora".

Como en `test_scheduler.py`, la comprobación horaria se simula con
`docker compose exec scheduler python /app/container/check.py`. Compose
recorta los espacios de `.env`, así que las formas con espacios se prueban
también pasando la variable directamente (archivo de Compose adicional y
`exec -e`, D8).
"""

import pytest

from tests.docker.helpers import container_url, dir_state, docker
from tests.docker.test_scheduler import (
    container_id,
    running_services,
    seed,
    snapshots,
    wait_logs,
)

DISABLED = "recogida desactivada en esta máquina; se activa con COLLECTION_ENABLED=true en .env"
STARTUP_DISABLED = "recogida desactivada (se activa con COLLECTION_ENABLED=true en .env)"


def checks(project, count, *env):
    """`count` comprobaciones horarias simuladas; devuelve su salida junta."""
    flags = [arg for pair in env for arg in ("-e", pair)]
    outputs = []
    project.wait_startup()
    for _ in range(count):
        result = project.compose("exec", "-T", *flags, "scheduler", "python",
                                 "/app/container/check.py", timeout=120)
        outputs.append(result.stdout + result.stderr)
    return "".join(outputs)


def test_enabled_startup_line_and_capture(project, http_server):
    """Escenario: Habilitada."""
    http_server.add_fixture("/api", "valid_two_stations.json")
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, "captura guardada (no hay capturas)")
    assert "; recogida activada" in project.scheduler_logs()
    assert http_server.requests == {"/api": 1}
    assert snapshots(project) == 1


def test_without_variable_mac_by_habit(project, http_server):
    """Escenario: Sin la variable (el Mac por costumbre): la última captura es de
    hace 7 h, pero no se pide nada en el arranque ni en 2 comprobaciones."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=7)
    before = dir_state(project.data)
    http_server.add_fixture("/api", "valid_two_stations.json")
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, DISABLED)
    outputs = project.scheduler_logs() + checks(project, 2)
    assert outputs.count(DISABLED) == 3  # al arrancar y en cada comprobación
    assert STARTUP_DISABLED in project.scheduler_logs()
    assert running_services(project) == [("scheduler", "running")]
    restarts = docker("inspect", "-f", "{{.RestartCount}}", container_id(project), timeout=60)
    assert restarts.stdout.strip() == "0"
    assert http_server.requests == {}
    assert dir_state(project.data) == before


@pytest.mark.parametrize("value", ["", "false"])
def test_empty_or_false_does_nothing(project, http_server, value):
    """Escenario: Variable vacía o false (sin capturas)."""
    project.write_env(COLLECTION_ENABLED=value)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, DISABLED)
    assert http_server.requests == {}
    assert dir_state(project.data) == {}


def test_invalid_value_keeps_running(project, http_server):
    """Escenario: Valor no válido."""
    project.write_env(COLLECTION_ENABLED="yes")
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "configuración no válida: COLLECTION_ENABLED no válido: 'yes'; "
                       "solo 'true' activa la recogida")
    assert running_services(project) == [("scheduler", "running")]
    assert http_server.requests == {}
    assert dir_state(project.data) == {}


def test_hourly_checks_while_disabled(project, http_server):
    """Escenario: Comprobaciones con la recogida desactivada."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, DISABLED)
    assert checks(project, 2).count(DISABLED) == 2
    assert http_server.requests == {}


def test_enable_later(project, http_server):
    """Escenario: Activarla después (vuelve a lanzarse `docker compose up -d`)."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    http_server.add_fixture("/api", "valid_two_stations.json")
    url = container_url(http_server, "/api")
    project.start_scheduler(url)
    wait_logs(project, DISABLED)
    project.write_env()
    assert project.start_scheduler(url).returncode == 0
    wait_logs(project, "captura guardada (no hay capturas)")
    assert http_server.requests == {"/api": 1}


def test_disable_later(project, http_server):
    """Escenario: Desactivarla después. La comprobación forzada con intervalo
    de 1 h tocaría (la última captura tiene 2 h), pero ya no captura."""
    seed(project, hours_ago=2)
    http_server.add_fixture("/api", "valid_two_stations.json")
    url = container_url(http_server, "/api")
    project.start_scheduler(url)
    wait_logs(project, "no toca capturar")
    project.write_env(COLLECTION_ENABLED="false")
    assert project.start_scheduler(url).returncode == 0
    wait_logs(project, DISABLED)
    assert DISABLED in checks(project, 1, "CAPTURE_INTERVAL_HOURS=1")
    assert http_server.requests == {}


def test_change_without_relaunch_keeps_running_value(project, http_server):
    """Escenario: Cambio sin volver a lanzar."""
    seed(project, hours_ago=2)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "no toca capturar")
    project.write_env(drop=("COLLECTION_ENABLED",))
    output = checks(project, 1, "CAPTURE_INTERVAL_HOURS=1")
    assert "captura guardada" in output and DISABLED not in output
    assert http_server.requests == {"/api": 1}


def test_manual_ingestion_does_not_depend_on_variable(project, http_server):
    """Escenario: La ingesta manual no depende de la variable."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    http_server.add_fixture("/api", "valid_two_stations.json")
    result = project.run_ingest(url=container_url(http_server, "/api"))
    assert result.returncode == 0, result.stderr
    assert snapshots(project) == 1


def test_spaces_and_case_passed_directly(project, http_server):
    """Escenario: Formas admitidas, sin pasar por el recorte de `.env` (D8):
    a `scheduler.py` (línea de arranque) y a `check.py` (`exec -e`)."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=2)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"),
                            environment={"COLLECTION_ENABLED": " TRUE "})
    wait_logs(project, "no toca capturar")
    assert "; recogida activada" in project.scheduler_logs()
    output = checks(project, 1, "COLLECTION_ENABLED= True ")
    assert "no toca capturar" in output and DISABLED not in output
    assert http_server.requests == {}
