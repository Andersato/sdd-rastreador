"""Copias y configuración no válida con el programador real en Docker
(`database-backup` y `scheduled-collection`), escenarios que faltaban.

Como en `test_scheduler.py`: el programador se arranca con
`Project.start_scheduler(url)` contra el servidor local y las tareas del
crontab se simulan con `docker compose exec scheduler …`, el mismo comando
que lanza supercronic.
"""

import gzip
import os
import shutil
import time
from datetime import datetime, timedelta

import pytest

from tests.docker.helpers import container_url, dir_state, docker
from tests.docker.test_backup import today_name
from tests.docker.test_scheduler import (
    container_id,
    running_services,
    seed,
    wait_logs,
    wait_until,
)
from tests.http_server import HANG
from tests.storage_helpers import query

ROOT_REASON = "no se permite ejecutar la ingesta como root"


def copy_snapshots(gz, work):
    out = work / f"copia-{time.monotonic_ns()}.db"
    with gzip.open(gz) as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return query(out, "SELECT COUNT(*) FROM snapshots")[0][0]


def old_copy(project, hours_ago):
    """Copia de ayer con fecha de modificación de hace `hours_ago` horas."""
    yesterday = (datetime.now() - timedelta(days=1)).date()
    path = project.backups / f"prices-{yesterday.isoformat()}.db.gz"
    path.write_bytes(b"anterior")
    instant = time.time() - hours_ago * 3600
    os.utime(path, (instant, instant))
    return path


def restarts(project):
    return docker("inspect", "-f", "{{.RestartCount}}", container_id(project),
                  timeout=60).stdout.strip()


# --- Copia al arrancar si la última es antigua ---------------------------------

def test_startup_with_capture_due_ingests_then_copies(project, http_server, tmp_path):
    """Escenario: Arranque con captura pendiente: la última captura es de hace 7 h
    y la última copia tiene 30 h; primero la ingesta y después la copia, que
    incluye la captura nueva."""
    seed(project, hours_ago=7)
    old_copy(project, hours_ago=30)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, f"copia guardada: {today_name()}")
    logs = project.scheduler_logs()
    assert logs.index("captura guardada") < logs.index(f"copia guardada: {today_name()}")
    assert "2 capturas, integridad correcta" in logs
    assert copy_snapshots(project.backups / today_name(), tmp_path) == 2
    assert http_server.requests == {"/api": 1}


def test_recent_copy_is_not_repeated_at_startup(project, http_server):
    """Escenario: Apagado solo a la hora de la copia (la última copia tiene 24 h
    17 min): al arrancar no se hace ninguna copia."""
    seed(project, hours_ago=1)
    old = old_copy(project, hours_ago=24.3)
    before = dir_state(project.backups)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "no toca capturar")
    project.wait_startup()
    assert "copia" not in project.scheduler_logs()
    assert dir_state(project.backups) == before and old.exists()


# --- Copia diaria a hora fija ---------------------------------------------------

def test_daily_copy_disabled_leaves_data_and_backups_untouched(project, http_server):
    """Escenario: Recogida desactivada (04:43): ni ./backups ni ./data cambian."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=1)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "recogida desactivada")
    project.wait_startup()
    before = dir_state(project.data)
    result = project.compose("exec", "-T", "scheduler", "python", "/app/container/backup.py",
                             "--daily", timeout=120)
    assert result.returncode == 0  # desactivada no es un error (revisión, punto 3)
    assert "copias desactivadas en esta máquina" in result.stdout
    assert dir_state(project.backups) == {}
    assert dir_state(project.data) == before


def test_failed_daily_copy_does_not_stop_the_scheduler(project, http_server):
    """Escenario: Una copia fallida no para el programador: ./backups sin permiso de
    escritura para el usuario del programador; la copia falla y la comprobación
    siguiente se hace con normalidad."""
    seed(project, hours_ago=1)
    old_copy(project, hours_ago=1)  # para que no haya copia de arranque
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "no toca capturar")
    project.wait_startup()
    project.backups.chmod(0o555)
    try:
        probe = project.compose("exec", "-T", "scheduler", "sh", "-c",
                                "touch /app/backups/.prueba && rm /app/backups/.prueba",
                                timeout=60)
        if probe.returncode == 0:
            pytest.skip("este entorno de Docker no aplica los permisos de la carpeta montada")
        before = dir_state(project.backups)
        result = project.compose("exec", "-T", "scheduler", "python", "/app/container/backup.py",
                                 "--daily", timeout=120)
        assert result.returncode != 0
        assert "error en la copia" in result.stdout, result.stdout + result.stderr
        assert dir_state(project.backups) == before
    finally:
        project.backups.chmod(0o755)
    assert running_services(project) == [("scheduler", "running")]
    assert restarts(project) == "0"
    check = project.exec_check()
    assert "no toca capturar" in check.stdout, check.stdout + check.stderr


# --- Copia interrumpida ------------------------------------------------------------

def test_compose_stop_during_a_copy(project, http_server):
    """Escenario: Copia interrumpida: `docker compose stop` mientras la copia diaria
    del programador está en curso (esperando el bloqueo de ./data, que tiene la
    ingesta de arranque): termina en menos de 15 s, sin archivos nuevos ni
    temporales en ./backups y con ./data igual que antes."""
    seed(project, hours_ago=7)
    old_copy(project, hours_ago=1)
    before_backups = dir_state(project.backups)
    before_data = dir_state(project.data)
    http_server.add("/api", mode=HANG)
    project.start_scheduler(container_url(http_server, "/api"))
    assert wait_until(lambda: http_server.count("/api") == 1, timeout=60)
    project.compose("exec", "-d", "-T", "scheduler", "python", "/app/container/backup.py",
                    "--daily", timeout=60)
    time.sleep(2)
    start = time.monotonic()
    result = project.compose("stop", timeout=60)
    elapsed = time.monotonic() - start
    assert result.returncode == 0, result.stderr
    assert elapsed < 15, f"la parada ha tardado {elapsed:.1f} s"
    assert dir_state(project.backups) == before_backups
    assert dir_state(project.data) == before_data


# --- Configuración no válida antes que recogida desactivada ------------------------

def test_root_without_variable_shows_root_not_disabled(project, http_server):
    """Escenario: Root sin la variable: al arrancar y en cada comprobación el log
    dice que no se permite root, no dice "recogida desactivada" y no hay
    peticiones."""
    project.write_env(uid=0, drop=("COLLECTION_ENABLED",))
    http_server.add_fixture("/api", "valid_two_stations.json")
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, ROOT_REASON)
    outputs = project.scheduler_logs() + "".join(project.exec_check().stdout for _ in range(2))
    assert outputs.count(ROOT_REASON) == 3
    assert http_server.requests == {}
    assert "recogida desactivada" not in outputs, outputs


def test_invalid_interval_with_collection_disabled(project, http_server):
    """Escenario: Intervalo no válido con la recogida desactivada."""
    project.write_env(CAPTURE_INTERVAL_HOURS="seis", COLLECTION_ENABLED="false")
    http_server.add_fixture("/api", "valid_two_stations.json")
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, "configuración no válida: CAPTURE_INTERVAL_HOURS no válido: 'seis'")
    check = project.exec_check()
    assert "CAPTURE_INTERVAL_HOURS no válido" in check.stdout
    assert "recogida desactivada en esta máquina" not in project.scheduler_logs() + check.stdout
    assert http_server.requests == {}


def test_invalid_value_with_root_shows_root_first(project, http_server):
    """Escenario: Valor no válido de la variable con root."""
    project.write_env(uid=0, COLLECTION_ENABLED="yes")
    http_server.add_fixture("/api", "valid_two_stations.json")
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, f"configuración no válida: {ROOT_REASON}")
    check = project.exec_check()
    assert f"configuración no válida: {ROOT_REASON}" in check.stdout
    assert http_server.requests == {}
