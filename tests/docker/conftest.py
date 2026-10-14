"""Configuración de los tests con Docker.

Todos los tests de esta carpeta llevan la marca `docker` y se saltan si
`docker info` falla. La imagen se construye una vez por sesión.
"""

from pathlib import Path

import pytest

from tests.docker.helpers import TEST_IMAGE, docker, docker_available, make_project

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
def image(tmp_path_factory):
    """Construye la imagen de test `precios-gasolineras-ingest-test` con el código actual.

    Se construye desde una copia temporal del proyecto y con su propio nombre
    de proyecto de Compose: nunca se toca el proyecto real (su imagen ni su
    programador, que puede estar en marcha).
    """
    builder = make_project(tmp_path_factory.mktemp("imagen"), build=True)
    result = builder.compose("build", "-q", timeout=900)
    assert result.returncode == 0, result.stderr
    return TEST_IMAGE


@pytest.fixture
def project(tmp_path, image):
    """Proyecto temporal con `.env` del usuario actual y `data/` vacía."""
    proj = make_project(tmp_path)
    yield proj
    proj.down()
