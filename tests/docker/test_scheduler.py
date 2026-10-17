"""Servicio programador (`docker compose up -d`): escenarios de `scheduled-collection`
y de `ingestion-container` que se pueden comprobar en el Mac.

El programador siempre se arranca con `Project.start_scheduler(url)`, contra el
servidor local. La comprobación horaria (minuto 17) no se espera: se simula
con `docker compose exec scheduler python /app/container/check.py`, el mismo
comando que lanza supercronic.
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from tests.builders import response, station
from tests.docker.helpers import (
    CLOSED_PORT_URL,
    TEST_IMAGE,
    container_url,
    dir_state,
    docker,
    make_project,
    unique_name,
)
from tests.http_server import FIXTURES, HANG, SLOW
from tests.storage_helpers import ingest, query

EXIT_BUSY = 3


def wait_until(predicate, timeout=60, interval=0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def wait_logs(project, text, count=1, timeout=60):
    assert wait_until(lambda: project.scheduler_logs().count(text) >= count, timeout), (
        f"no aparece {text!r} en los logs:\n{project.scheduler_logs()}"
    )


def seed(project, hours_ago, stations=2):
    """`./data/prices.db` con 1 captura de hace `hours_ago` horas."""
    instant = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    data = response(*(station(f"S{i}", **{"Precio Gasoleo A": "1,459"}) for i in range(stations)))
    ingest(project.db, data, instant=instant)


def snapshots(project):
    return query(project.db, "SELECT COUNT(*) FROM snapshots")[0][0]


def running_services(project):
    result = project.compose("ps", "--format", "json", timeout=60)
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return sorted((row["Service"], row["State"]) for row in rows)


def container_id(project):
    return project.compose("ps", "-q", "scheduler", timeout=60).stdout.strip()


def slow_fixture(server, path, seconds):
    size = (FIXTURES / "valid_two_stations.json").stat().st_size
    return server.add_fixture(path, "valid_two_stations.json", mode=SLOW, delay=seconds / size)


# --- Servicio programador que se arranca una vez ------------------------------

def test_activation_only_scheduler_with_host_user_and_startup_capture(project, http_server):
    """Escenarios: Activación y Programador contra un servidor local."""
    http_server.add_fixture("/api", "valid_two_stations.json")
    result = project.start_scheduler(container_url(http_server, "/api"))
    assert result.returncode == 0, result.stderr
    # Exactamente dos contenedores: el programador y la API de prices-api.
    assert running_services(project) == [("api", "running"), ("scheduler", "running")]
    for service in ("scheduler", "api"):
        uid = project.compose("exec", "-T", service, "id", "-u", timeout=60).stdout.strip()
        gid = project.compose("exec", "-T", service, "id", "-g", timeout=60).stdout.strip()
        assert (int(uid), int(gid)) == (os.getuid(), os.getgid())
    wait_logs(project, "captura guardada (no hay capturas)")
    assert "programador en marcha" in project.scheduler_logs()
    assert http_server.requests == {"/api": 1}
    assert snapshots(project) == 1
    assert sorted(dir_state(project.data)) == ["prices.db"]


def test_scheduled_ingestions_use_the_fixed_database(project, http_server):
    """Escenario: Base de datos de las ingestas programadas (`ingestion-container`):
    la captura de arranque va a ./data/prices.db
    y no se crea ninguna otra base de datos, ni en ./data ni dentro del contenedor.

    Las ingestas que se comprueban son la de arranque (la lanza scheduler.py) y
    una comprobación horaria simulada con `exec` de check.py, el mismo comando
    del crontab. Ninguna la dispara supercronic: esperar al minuto 17 no es
    viable en un test."""
    seed(project, hours_ago=7)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "captura guardada")
    project.wait_startup()
    result = project.compose("exec", "-T", "-e", "CAPTURE_INTERVAL_HOURS=1", "scheduler",
                             "python", "/app/container/check.py", timeout=120)
    assert "no toca capturar" in result.stdout, result.stdout + result.stderr
    assert snapshots(project) == 2
    assert sorted(dir_state(project.data)) == ["prices.db"]
    # Archivos *.db* creados después de arrancar (el crontab se escribe al arrancar),
    # fuera de ./data (-xdev no entra en el montaje de /app/data).
    found = project.compose("exec", "-T", "scheduler", "find", "/", "-xdev",
                            "-name", "*.db*", "-newer", "/tmp/crontab", timeout=60)
    assert found.stdout.split() == [], found.stdout + found.stderr
    assert http_server.requests == {"/api": 1}


def test_simulated_hourly_check_after_capture(project, http_server):
    """Comprobación horaria simulada: tras la captura de arranque, no toca."""
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "captura guardada")
    result = project.exec_check()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no toca capturar: última captura hace 0 h 0 min (intervalo 6 h)" in result.stdout
    assert http_server.requests == {"/api": 1}


# --- Configuración no válida --------------------------------------------------

@pytest.mark.parametrize(("uid", "gid", "reason"), [
    (0, None, "no se permite ejecutar la ingesta como root"),
    (None, 0, "no se permite ejecutar la ingesta con el grupo root"),
], ids=["usuario-root", "grupo-root"])
def test_root_keeps_running_without_requests(project, http_server, uid, gid, reason):
    """Escenarios: Usuario root y Grupo root (sigue en marcha, motivo repetido), y
    Programador configurado como root de `ingestion-container` (HOST_UID=0)."""
    project.write_env(uid=uid, gid=gid)
    http_server.add_fixture("/api", "valid_two_stations.json")
    before = dir_state(project.data)
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, reason)
    outputs = project.scheduler_logs() + "".join(project.exec_check().stdout for _ in range(2))
    assert outputs.count(reason) == 3  # al arrancar y en 2 comprobaciones
    # Diferencia intencionada (prices-api): la API, con root, no arranca y Docker
    # la reintenta (entre intento e intento puede verse «running» un instante);
    # el programador sigue en marcha.
    assert dict(running_services(project))["scheduler"] == "running"
    assert wait_until(lambda: "no se permite ejecutar la API" in project.api_logs(), 60)
    restarts = docker("inspect", "-f", "{{.RestartCount}}", container_id(project), timeout=60)
    assert restarts.stdout.strip() == "0"
    assert http_server.requests == {}
    assert dir_state(project.data) == before


def test_invalid_interval_keeps_running_without_requests(project, http_server):
    """Escenario: Intervalo no válido."""
    project.write_env(CAPTURE_INTERVAL_HOURS="seis")
    http_server.add_fixture("/api", "valid_two_stations.json")
    assert project.start_scheduler(container_url(http_server, "/api")).returncode == 0
    wait_logs(project, "configuración no válida: CAPTURE_INTERVAL_HOURS no válido: 'seis'; "
                       "se admiten horas enteras de 1 a 24")
    assert running_services(project) == [("api", "running"), ("scheduler", "running")]
    assert http_server.requests == {}
    assert dir_state(project.data) == {}


def test_missing_host_uid(project):
    """Escenario: Falta HOST_UID."""
    project.write_env(drop=("HOST_UID",))
    result = project.start_scheduler(CLOSED_PORT_URL)
    assert result.returncode != 0
    assert "falta HOST_UID" in result.stderr
    assert running_services(project) == []
    assert dir_state(project.data) == {}


def test_missing_data_folder(tmp_path, image):
    """Escenario: Carpeta ./data inexistente."""
    project = make_project(tmp_path, data=False)
    try:
        result = project.start_scheduler(CLOSED_PORT_URL)
        assert result.returncode != 0
        assert not project.data.exists()
    finally:
        project.down()


# --- Ingesta manual con el programador en marcha ------------------------------

def test_manual_capture_without_ingestion_in_progress(project, http_server):
    """Escenario: Captura manual sin ingesta en curso."""
    seed(project, hours_ago=1)
    http_server.add_fixture("/sched", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/sched"))
    wait_logs(project, "no toca capturar")
    http_server.add_fixture("/manual", "valid_two_stations.json")
    result = project.run_ingest(url=container_url(http_server, "/manual"))
    assert result.returncode == 0, result.stderr
    assert snapshots(project) == 2
    assert http_server.requests == {"/manual": 1}


def test_manual_capture_while_scheduler_captures(project, http_server):
    """Escenario: Captura manual mientras el programador captura (bloqueo entre contenedores)."""
    slow_fixture(http_server, "/sched", 8)
    project.start_scheduler(container_url(http_server, "/sched"))
    assert wait_until(lambda: http_server.count("/sched") == 1, timeout=60)
    http_server.add_fixture("/manual", "valid_two_stations.json")
    result = project.run_ingest(url=container_url(http_server, "/manual"))
    assert result.returncode == EXIT_BUSY, result.stderr
    assert "ya hay otra ingesta o copia en curso" in result.stderr
    assert http_server.count("/manual") == 0
    wait_logs(project, "captura guardada", timeout=60)
    assert snapshots(project) == 1
    assert sorted(dir_state(project.data)) == ["prices.db"]


def test_startup_check_still_running_at_minute_17(project, http_server):
    """Escenario: Arranque justo antes del minuto 17 (una sola ingesta)."""
    slow_fixture(http_server, "/sched", 8)
    project.start_scheduler(container_url(http_server, "/sched"))
    assert wait_until(lambda: http_server.count("/sched") == 1, timeout=60)
    result = project.exec_check(wait_startup=False)  # la comprobación de las :17
    assert "otra ingesta o copia en curso; no se captura" in result.stdout
    wait_logs(project, "captura guardada", timeout=60)
    assert http_server.requests == {"/sched": 1}
    assert snapshots(project) == 1


# --- Parada del programador ---------------------------------------------------

def test_down_without_ingestion_in_progress(project, http_server):
    """Escenario: Parada sin ingesta en curso."""
    seed(project, hours_ago=1)
    before = dir_state(project.data)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    wait_logs(project, "no toca capturar")
    result = project.compose("down", timeout=120)
    assert result.returncode == 0, result.stderr
    assert running_services(project) == []
    assert http_server.requests == {}
    assert dir_state(project.data) == before


@pytest.mark.parametrize("launcher", ["arranque", "horaria"])
def test_stop_does_not_wait_for_ingestion(project, http_server, launcher):
    """Escenario: La parada no espera a la ingesta (< 5 s, sin captura nueva)."""
    seed(project, hours_ago=1 if launcher == "horaria" else 7)
    before = dir_state(project.data)
    http_server.add("/api", mode=HANG)  # la ingesta se queda esperando
    project.start_scheduler(container_url(http_server, "/api"))
    if launcher == "horaria":
        wait_logs(project, "no toca capturar")
        project.wait_startup()
        project.compose("exec", "-d", "-T", "-e", "CAPTURE_INTERVAL_HOURS=1", "scheduler",
                        "python", "/app/container/check.py", timeout=60)
    assert wait_until(lambda: http_server.count("/api") == 1, timeout=60)
    start = time.monotonic()
    result = project.compose("stop", timeout=60)
    elapsed = time.monotonic() - start
    assert result.returncode == 0, result.stderr
    assert elapsed < 5, f"la parada ha tardado {elapsed:.1f} s"
    assert dir_state(project.data) == before
    assert http_server.requests == {"/api": 1}


def test_stop_during_save_keeps_complete_captures(project, http_server):
    """Escenario: Parada durante una ingesta (3 o 4 capturas completas, sin diario ni temporal)."""
    for hours in (30, 20, 10):
        seed(project, hours_ago=hours)
    big = response(*(station(f"B{i}", **{"Precio Gasoleo A": "1,459", "Precio Gasoleo B": "1,299"})
                     for i in range(20_000)))
    http_server.add("/api", body=json.dumps(big))
    journal = project.data / "prices.db-journal"
    project.start_scheduler(container_url(http_server, "/api"))
    assert wait_until(journal.exists, timeout=60, interval=0.002), "la ingesta no llegó a guardar"
    project.compose("stop", timeout=60)
    assert sorted(dir_state(project.data)) == ["prices.db"]
    count = snapshots(project)
    assert count in (3, 4)
    if count == 4:
        assert query(project.db, "SELECT COUNT(*) FROM prices WHERE snapshot_id = 4") == [(40_000,)]


# --- Tamaño de los logs, imagen y zona horaria -------------------------------

def test_log_rotation_configuration(project, http_server):
    """Escenario: Rotación (10 MB × 3)."""
    seed(project, hours_ago=1)
    http_server.add_fixture("/api", "valid_two_stations.json")
    project.start_scheduler(container_url(http_server, "/api"))
    result = docker("inspect", "-f", "{{json .HostConfig.LogConfig}}", container_id(project),
                    timeout=60)
    config = json.loads(result.stdout)
    assert config == {"Type": "json-file", "Config": {"max-file": "3", "max-size": "10m"}}


def test_madrid_time_inside_container(image):
    """Escenario: Hora de Madrid dentro del contenedor."""
    code = ("from datetime import datetime, timezone; "
            "print(datetime(2026, 7, 15, 12, 17, tzinfo=timezone.utc).astimezone().isoformat())")
    result = docker("run", "--rm", "--network", "none", "-e", "TZ=Europe/Madrid",
                    "--entrypoint", "python", image, "-c", code, timeout=120)
    assert result.stdout.strip() == "2026-07-15T14:17:00+02:00"


def test_scheduler_without_compose_is_not_root(image):
    """Escenario: Programador lanzado sin Compose."""
    name = unique_name()
    started = docker("run", "--rm", "-d", "--name", name, "-e", f"INGEST_API_URL={CLOSED_PORT_URL}",
                     "--entrypoint", "python", image, "/app/container/scheduler.py", timeout=120)
    assert started.returncode == 0, started.stderr
    try:
        statuses = docker("exec", name, "sh", "-c",
                          "cat /proc/[0-9]*/status | grep -E '^(Uid|Gid):'", timeout=60)
        ids = {line.split()[1] for line in statuses.stdout.splitlines()}
        assert ids and "0" not in ids, statuses.stdout
    finally:
        docker("rm", "-f", name, timeout=60)


def test_supercronic_pinned_version_and_valid_crontab(image):
    """Escenario: Construcción en el Mac (versión fijada) y crontab válido."""
    version = docker("run", "--rm", "--network", "none", "--entrypoint", "supercronic", image,
                     "-version", timeout=120)
    assert version.stdout.strip() == "v0.2.49"
    script = ("python -c 'import sys; sys.path.insert(0, \"/app/container\"); import scheduler; "
              "open(\"/tmp/c\", \"w\").write(scheduler.crontab())' && supercronic -test /tmp/c")
    result = docker("run", "--rm", "--network", "none", "--entrypoint", "sh", image, "-c", script,
                    timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "crontab is valid" in result.stdout + result.stderr


def test_compose_build_single_image_for_both_services(project):
    """Escenarios: Construcción (una sola imagen para el programador, la API y la
    ingesta a mano) y Copia a mano con la misma imagen."""
    default = project.compose("config", "--services", timeout=60).stdout.split()
    assert sorted(default) == ["api", "scheduler"]
    config = json.loads(project.compose("--profile", "manual", "config", "--format", "json",
                                        timeout=60).stdout)
    images = {name: svc["image"] for name, svc in config["services"].items()}
    assert images == {"ingest": TEST_IMAGE, "scheduler": TEST_IMAGE, "backup": TEST_IMAGE,
                      "api": TEST_IMAGE}
    assert project.run_entrypoint("python", "-c", "print('ok')").stdout.strip() == "ok"


@pytest.fixture
def build_project(tmp_path):
    return make_project(tmp_path, build=True)


def test_build_for_amd64(build_project):
    """Escenario: Construcción para amd64."""
    tag = unique_name("pgtest-amd64")
    built = docker("build", "-q", "--platform", "linux/amd64", "-t", tag, ".",
                   cwd=build_project.root, timeout=900)
    assert built.returncode == 0, built.stderr
    try:
        result = docker("run", "--rm", "--platform", "linux/amd64", "--network", "none",
                        "--entrypoint", "sh", tag, "-c", "uname -m; supercronic -version",
                        timeout=300)
        assert result.stdout.split() == ["x86_64", "v0.2.49"]
    finally:
        docker("rmi", "-f", tag, timeout=120)


def test_build_fails_with_wrong_checksum(build_project):
    """Escenario: Suma de comprobación que no coincide."""
    tag = unique_name("pgtest-badsum")
    wrong = "0" * 64
    result = docker("build", "--progress", "plain", "--build-arg", f"SUPERCRONIC_SHA256_ARM64={wrong}",
                    "--build-arg", f"SUPERCRONIC_SHA256_AMD64={wrong}", "-t", tag, ".",
                    cwd=build_project.root, timeout=900)
    assert result.returncode != 0
    assert "no coincide" in result.stderr
    assert docker("image", "inspect", tag, timeout=60).returncode != 0
