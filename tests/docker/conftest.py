"""Configuración de los tests con Docker.

Todos los tests de esta carpeta llevan la marca `docker` y se saltan si
`docker info` falla. La imagen se construye una vez por sesión.
"""

import os
from pathlib import Path

import pytest

from tests.docker.helpers import IMAGE, docker, docker_available, make_project
from tests.helpers import REPO_ROOT

HERE = Path(__file__).parent
_available = None


def _docker_ok() -> bool:
    global _available
    if _available is None:
        _available = docker_available()
    return _available


def pytest_collection_modifyitems(config, items):
    for item in items:
        if HERE not in Path(item.path).parents:
            continue
        item.add_marker(pytest.mark.docker)
        if not _docker_ok():
            item.add_marker(pytest.mark.skip(reason="Docker no está disponible (docker info falla)"))


@pytest.fixture(scope="session")
def image():
    """Construye la imagen `precios-gasolineras-ingest` desde el repo.

    Sustituye la imagen local del usuario por la del código actual: es la
    misma que daría `docker compose build`. El UID/GID se pasa como variable
    del subproceso para no crear ni pisar el `.env` del repo.
    """
    result = docker(
        "compose", "-f", str(REPO_ROOT / "docker-compose.yml"), "build", "-q",
        env={"HOST_UID": str(os.getuid()), "HOST_GID": str(os.getgid())},
        cwd=REPO_ROOT, timeout=900,
    )
    assert result.returncode == 0, result.stderr
    return IMAGE


@pytest.fixture
def project(tmp_path, image):
    """Proyecto temporal con `.env` del usuario actual y `data/` vacía."""
    proj = make_project(tmp_path)
    yield proj
    proj.down()
