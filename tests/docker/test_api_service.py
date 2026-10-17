"""Servicio `api` en Docker (prices-api): «Servicio api que se arranca con el
programador», «API sin usuario root», «Carpeta ./data montada en solo
lectura» y «Base ocupada por una recogida» entre dos contenedores.

La API de cada proyecto temporal se publica en un puerto libre
(`project.api_port`), nunca en el 8000 real (design.md, D14).
"""

import os
import subprocess
import time

import pytest

from tests.api_helpers import ATTRIBUTION
from tests.docker.helpers import API, docker_env, guard_docker_args, unique_name
from tests.docker.test_scheduler import running_services, seed, wait_logs, wait_until


def test_start_like_the_vps(project, http_server):
    """Escenario: Arranque en el VPS (programador y API con el usuario de .env)."""
    seed(project, hours_ago=1)
    project.start_services(http_server)
    assert running_services(project) == [("api", "running"), ("scheduler", "running")]
    uid = project.compose("exec", "-T", API, "id", "-u", timeout=60).stdout.strip()
    gid = project.compose("exec", "-T", API, "id", "-g", timeout=60).stdout.strip()
    assert (int(uid), int(gid)) == (os.getuid(), os.getgid())
    project.wait_api()
    status, body = project.api_get("/api/health")
    assert (status, body["status"], body["attribution"]) == (200, "ok", ATTRIBUTION)
    assert http_server.requests == {}  # la última captura es de hace 1 h: no toca


def test_start_on_the_mac_without_collection(project, http_server):
    """Escenario: Arranque en el Mac sin recogida."""
    project.write_env(drop=("COLLECTION_ENABLED",))
    seed(project, hours_ago=7)
    project.start_services(http_server)
    wait_logs(project, "recogida desactivada")
    project.wait_api()
    status, body = project.api_get("/api/fuels")
    assert status == 200
    assert next(f for f in body["data"] if f["slug"] == "gasoleo-a")["stations"] == 2
    assert http_server.requests == {}


def test_stop_is_quick_and_leaves_data_unchanged(project, http_server):
    """Escenario: Parada."""
    seed(project, hours_ago=1)
    project.start_services(http_server)
    project.wait_api()
    project.api_get("/api/fuels")
    before = {p.name: p.read_bytes() for p in project.data.iterdir()}
    started = time.monotonic()
    result = project.compose("stop", API, timeout=60)
    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 10
    assert {p.name: p.read_bytes() for p in project.data.iterdir()} == before


@pytest.mark.parametrize(("uid", "gid", "message"), [
    (0, None, "no se permite ejecutar la API como root (usuario 0); revisa HOST_UID en .env"),
    (None, 0, "no se permite ejecutar la API con el grupo root (grupo 0); revisa HOST_GID en .env"),
], ids=["usuario-root", "grupo-root"])
def test_root_does_not_serve(project, http_server, uid, gid, message):
    """Escenarios: Usuario root y Grupo root."""
    project.write_env(uid=uid, gid=gid)
    seed(project, hours_ago=1)
    before = {p.name: p.read_bytes() for p in project.data.iterdir()}
    project.start_services(http_server)
    assert wait_until(lambda: message in project.api_logs(), 60), project.api_logs()
    # Docker la reintenta: el motivo se repite y el puerto nunca responde (entre
    # intento e intento el contenedor puede verse «running» un instante).
    assert wait_until(lambda: project.api_logs().count(message) >= 2, 60), project.api_logs()
    for _ in range(10):
        assert not project.api_answers()
        time.sleep(0.3)
    assert {p.name: p.read_bytes() for p in project.data.iterdir()} == before


def test_writing_is_impossible(project, http_server):
    """Escenario: Escritura imposible."""
    seed(project, hours_ago=1)
    project.start_services(http_server)
    project.wait_api()
    result = project.compose("exec", "-T", API, "python", "-c",
                             "open('/app/data/x', 'w')", timeout=60)
    assert result.returncode != 0
    assert "Read-only file system" in result.stderr
    assert not (project.data / "x").exists()


HOLD = """
import sqlite3, sys, time
conn = sqlite3.connect("/app/data/prices.db", isolation_level=None)
conn.execute("BEGIN EXCLUSIVE")
print("ready", flush=True)
time.sleep(4)
conn.execute("ROLLBACK")
"""


def test_lock_between_two_containers(project, http_server):
    """Escenario: Entre dos contenedores (Docker)."""
    seed(project, hours_ago=1)
    project.start_services(http_server)
    project.wait_api()
    assert project.api_get("/api/fuels")[0] == 200
    args = project._run_args(unique_name(), "python", ["-c", HOLD])
    guard_docker_args(args)
    holder = subprocess.Popen(["docker", *args], env=docker_env(), cwd=project.root,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready", holder.stderr.read()
        started = time.monotonic()
        status, body = project.api_get("/api/fuels")
        elapsed = time.monotonic() - started
    finally:
        holder.wait(timeout=60)
    assert (status, body["error"]["code"]) == (503, "base_ocupada")
    assert 1.5 <= elapsed <= 3.5
    assert project.api_get("/api/fuels")[0] == 200
