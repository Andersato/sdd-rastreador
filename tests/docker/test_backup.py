"""Copias en Docker (`database-backup`): carpeta `./backups`, servicio `backup`
(copia a mano) y copias del programador.

Las copias no piden nada a la API. La comprobación de arranque se lanza
contra el servidor local, como en `test_scheduler.py`.
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.docker.helpers import (
    CLOSED_PORT_URL,
    TEST_IMAGE,
    container_exists,
    container_url,
    dir_state,
    docker,
    make_project,
    unique_name,
)
from tests.docker.test_scheduler import seed, slow_fixture, snapshots, wait_logs, wait_until


def today_name():
    return f"prices-{datetime.now(ZoneInfo('Europe/Madrid')).date().isoformat()}.db.gz"


def all_services(project):
    """Servicios con contenedor creado (en marcha o no)."""
    result = project.compose("ps", "-a", "--format", "{{.Service}}", timeout=60)
    return sorted(set(result.stdout.split()))


# --- Carpeta ./backups montada aparte -----------------------------------------

def test_missing_backups_folder_fails_without_creating_it(tmp_path, image, http_server):
    """Escenario: ./backups inexistente."""
    project = make_project(tmp_path, backups=False)
    try:
        http_server.add_fixture("/api", "valid_two_stations.json")
        result = project.start_scheduler(container_url(http_server, "/api"))
        assert result.returncode != 0
        assert not project.backups.exists()
        assert http_server.requests == {}
    finally:
        project.down()


def test_manual_ingestion_does_not_need_backups(tmp_path, image, http_server):
    """Escenario: La ingesta manual no necesita ./backups."""
    project = make_project(tmp_path, backups=False)
    try:
        http_server.add_fixture("/api", "valid_two_stations.json")
        result = project.run_ingest(url=container_url(http_server, "/api"))
        assert result.returncode == 0, result.stderr
        assert snapshots(project) == 1
        assert not project.backups.exists()
    finally:
        project.down()


def test_manual_ingestion_does_not_see_the_copies(project):
    """Escenario: La ingesta manual no ve las copias."""
    result = project.run_entrypoint("sh", "-c", "test -e /app/backups && echo montada || echo no")
    assert result.stdout.strip() == "no", result.stdout + result.stderr


def test_activation_creates_neither_ingest_nor_backup(project, http_server):
    """Escenario: Activación (sin contenedores de `ingest` ni de la copia a mano)."""
    http_server.add_fixture("/api", "valid_two_stations.json")
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, "captura guardada")
    # Programador y API (add-prices-api), sin `ingest` ni la copia a mano.
    assert all_services(project) == ["api", "scheduler"]


def test_manual_copy_uses_the_same_image(project):
    """Escenario: Copia a mano con la misma imagen."""
    result = project.compose("--profile", "manual", "config", "--images", timeout=60)
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.split()) == {TEST_IMAGE}


def test_copy_files_belong_to_the_host_user(project):
    """Escenario: Archivos a nombre del usuario del host (en el Mac se comprueba el
    número; los permisos por número solo se ven en Linux: verificación manual)."""
    seed(project, hours_ago=1)
    assert project.run_backup().returncode == 0
    import os

    st = (project.backups / today_name()).stat()
    assert (st.st_uid, st.st_gid) == (os.getuid(), os.getgid())


# --- Copia a mano ---------------------------------------------------------------

def test_copy_before_an_update_with_scheduler_running(project, http_server):
    """Escenario: Copia antes de una actualización (programador en marcha, la misma
    línea que la copia diaria)."""
    seed(project, hours_ago=1)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "no toca capturar")
    project.wait_startup()
    result = project.run_backup()
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"· copia guardada: {today_name()} (" in result.stdout
    assert "1 capturas, integridad correcta)" in result.stdout
    assert (project.backups / today_name()).exists()
    assert sorted(dir_state(project.data)) == ["prices.db"]


def test_manual_copy_with_the_scheduler_stopped(project, http_server):
    """Escenario: Copia a mano con el programador parado."""
    seed(project, hours_ago=1)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "no toca capturar")
    assert project.compose("stop", timeout=120).returncode == 0
    result = project.run_backup()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project.backups / today_name()).exists()
    state = project.compose("ps", "-a", "--format", "{{.Service}} {{.State}}", timeout=60)
    assert "scheduler exited" in state.stdout


def test_manual_copy_waits_for_an_ingestion_in_another_container(project, http_server):
    """Escenario: Ingesta en curso que termina pronto: el bloqueo vale entre
    contenedores y la copia lleva la captura nueva."""
    seed(project, hours_ago=1)
    url = slow_fixture(http_server, "/api", 3)
    proc = project.start_ingest(url=container_url(http_server, "/api"),
                                container_name=unique_name())
    assert wait_until(lambda: http_server.requests.get("/api"), timeout=60)
    result = project.run_backup()
    proc.communicate(timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 capturas" in result.stdout


def test_manual_copy_with_an_ingestion_that_does_not_end(project, http_server):
    """Escenario: Copia a mano con una ingesta en curso (plazo reducido con
    `--wait`, solo para pruebas)."""
    seed(project, hours_ago=1)
    slow_fixture(http_server, "/api", 60)
    name = unique_name()
    proc = project.start_ingest(url=container_url(http_server, "/api"), container_name=name)
    try:
        assert wait_until(lambda: http_server.requests.get("/api"), timeout=60)
        result = project.run_backup("--wait", "2")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "ya hay otra ingesta o copia en curso" in result.stdout
        assert dir_state(project.backups) == {}
    finally:
        docker("stop", "-t", "2", name, timeout=60)
        proc.communicate(timeout=60)


def test_manual_copy_without_backups_folder(tmp_path, image):
    """Escenario: Copia a mano sin ./backups."""
    project = make_project(tmp_path, backups=False)
    try:
        result = project.run_backup()
        assert result.returncode != 0
        assert not project.backups.exists()
    finally:
        project.down()


def test_manual_copy_on_the_mac(project):
    """Escenario: Copia a mano en el Mac (sin COLLECTION_ENABLED)."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=1)
    result = project.run_backup()
    assert result.returncode == 2
    assert "copias desactivadas en esta máquina" in result.stdout
    assert dir_state(project.backups) == {}


def test_manual_copy_spaces_and_case_passed_directly(project):
    """D8: normalización con `backup.py` pasando la variable directamente."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=1)
    result = project.run_backup(env={"COLLECTION_ENABLED": " TRUE "})
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project.backups / today_name()).exists()


def test_interrupted_copy_stops_quickly_and_leaves_nothing(project, http_server):
    """Escenario: Copia interrumpida: la copia espera a una ingesta y se para con
    `docker stop`; termina en menos de 15 s sin dejar nada en ./backups."""
    seed(project, hours_ago=1)
    slow_fixture(http_server, "/api", 60)
    ingest_name, backup_name = unique_name(), unique_name()
    ingest = project.start_ingest(url=container_url(http_server, "/api"),
                                  container_name=ingest_name)
    try:
        assert wait_until(lambda: http_server.requests.get("/api"), timeout=60)
        before = dir_state(project.data)
        backup = project.start_backup(backup_name)
        assert wait_until(lambda: container_exists(backup_name), timeout=60)
        time.sleep(1)
        start = time.monotonic()
        docker("stop", backup_name, timeout=60)
        backup.communicate(timeout=60)
        assert time.monotonic() - start < 15
        assert dir_state(project.backups) == {}
    finally:
        docker("stop", "-t", "2", ingest_name, timeout=60)
        ingest.communicate(timeout=60)
    assert dir_state(project.data) == before


# --- Copias del programador ---------------------------------------------------

def test_startup_copy_without_previous_copies(project, http_server):
    """Escenario: Sin copias: la comprobación de arranque hace una copia."""
    seed(project, hours_ago=1)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, f"copia guardada: {today_name()}")
    assert http_server.requests == {}


def test_startup_copy_disabled(project, http_server):
    """Escenario: Copia al arrancar con la recogida desactivada."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=1)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "recogida desactivada en esta máquina")
    time.sleep(2)
    assert dir_state(project.backups) == {}


def test_daily_copy_disabled_creates_nothing(project, http_server):
    """Escenario: Recogida desactivada a las 04:43 (el comando del crontab)."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=1)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "recogida desactivada")
    project.wait_startup()
    result = project.compose("exec", "-T", "scheduler", "python", "/app/container/backup.py",
                             "--daily", timeout=120)
    assert result.returncode == 0  # no es un error: supercronic no lo registra como tal
    assert "copias desactivadas en esta máquina" in result.stdout
    assert dir_state(project.backups) == {}


def test_crontab_has_the_daily_copy(project, http_server):
    """Escenario: Copia de madrugada (la línea del crontab del contenedor)."""
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "programador en marcha")
    crontab = project.compose("exec", "-T", "scheduler", "cat", "/tmp/crontab", timeout=60)
    assert "43 4 * * * python /app/container/backup.py --daily" in crontab.stdout
