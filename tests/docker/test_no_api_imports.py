"""Requisito «Ingesta, programador y copias sin depender de la API» (add-prices-api).

Con `PYTHONPROFILEIMPORTTIME=1` cada proceso de Python escribe en stderr una
línea por módulo importado. A diferencia de `-X importtime`, la variable la
heredan el `os.execv` de `entrypoint.py` y los procesos que lanza supercronic
(design.md, D14), así que se ve lo que importa el proceso que de verdad
trabaja.
"""

import json

from tests.docker.helpers import NO_PROXY_VALUE, SERVICE, container_url, docker, unique_name
from tests.docker.test_scheduler import wait_logs
from tests.http_server import FIXTURES
from tests.storage_helpers import ingest, query

PROFILE = {"PYTHONPROFILEIMPORTTIME": "1"}


def assert_no_api_modules(output: str) -> None:
    imports = [line for line in output.splitlines() if line.startswith("import time:")]
    assert imports, "no se ha registrado ninguna importación: la variable no ha llegado"
    modules = {line.rsplit("|", 1)[-1].strip().split(".")[0] for line in imports}
    assert "fastapi" not in modules
    assert "uvicorn" not in modules
    assert "starlette" not in modules


def test_manual_ingestion_does_not_import_the_api(project, http_server):
    http_server.add_fixture("/api", "valid_two_stations.json")
    run = ["compose", "-p", project.name, "-f", str(project.compose_file), "run", "--rm", "-T",
           "--name", unique_name(), "-e", f"NO_PROXY={NO_PROXY_VALUE}",
           "-e", f"no_proxy={NO_PROXY_VALUE}", "-e", "PYTHONPROFILEIMPORTTIME=1",
           SERVICE, "--url", container_url(http_server, "/api")]
    result = docker(*run, cwd=project.root, timeout=300)
    assert result.returncode == 0, result.stderr
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(1,)]
    # El proceso que guarda es el que `entrypoint.py` lanza con execv.
    assert "src.ingestion.storage" in result.stderr
    assert_no_api_modules(result.stderr)


def test_scheduler_check_does_not_import_the_api(project, http_server):
    project.write_env(drop=("COLLECTION_ENABLED",))
    result = project.start_scheduler(container_url(http_server, "/api"), environment=PROFILE)
    assert result.returncode == 0, result.stderr
    # Una línea al arrancar (scheduler.py) y otra de la comprobación de
    # arranque (check.py, lanzado aparte): las dos con el perfil activo.
    wait_logs(project, "recogida desactivada", count=2)
    project.wait_startup()
    logs = project.scheduler_logs()
    # Solo check.py importa src.backup.scheduled: se ve su proceso, no solo el
    # de scheduler.py.
    assert "src.backup.scheduled" in logs
    assert_no_api_modules(logs)
    assert http_server.total_requests() == 0


def test_manual_copy_does_not_import_the_api(project):
    ingest(project.db, json.loads((FIXTURES / "valid_two_stations.json").read_text()))
    result = project.run_backup(env=PROFILE)
    assert result.returncode == 0, result.stderr
    assert list(project.backups.glob("prices-*.db.gz"))
    assert "src.backup" in result.stderr
    assert_no_api_modules(result.stderr)
