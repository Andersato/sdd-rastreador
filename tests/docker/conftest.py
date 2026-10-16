"""Configuración de los tests con Docker.

Todos los tests de esta carpeta llevan la marca `docker` y se saltan si
`docker info` falla. La imagen se construye una vez por sesión.

Las carpetas temporales de esta carpeta de tests se crean bajo `$HOME`
(`~/.cache/precios-gasolineras-tests/`), no en la temporal del sistema: en
macOS esa está en `/private/var/folders/…`, que Colima no comparte con su
máquina virtual. Bajo `$HOME` funciona igual en OrbStack, Colima y Linux.
"""

import shutil
import tempfile
import warnings
from pathlib import Path

import pytest

from tests.docker.helpers import TEST_IMAGE, docker, docker_available, make_project

HERE = Path(__file__).parent
SHARED_TMP_ROOT = Path.home() / ".cache" / "precios-gasolineras-tests"
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
def shared_tmp():
    """Carpeta de esta ejecución, con nombre único, que se borra al terminar."""
    SHARED_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=SHARED_TMP_ROOT))
    yield run
    shutil.rmtree(run, ignore_errors=True)
    if run.exists():  # p. ej. en Linux, archivos de un contenedor con otro UID
        warnings.warn(f"no se ha podido borrar del todo la carpeta temporal {run}")


@pytest.fixture
def tmp_path(shared_tmp):
    """Sustituye al `tmp_path` de pytest: carpeta propia del test dentro de `shared_tmp`."""
    return Path(tempfile.mkdtemp(prefix="test-", dir=shared_tmp))


@pytest.fixture(scope="session")
def image(shared_tmp):
    """Construye la imagen de test `precios-gasolineras-ingest-test` con el código actual.

    Se construye desde una copia temporal del proyecto y con su propio nombre
    de proyecto de Compose: nunca se toca el proyecto real (su imagen ni su
    programador, que puede estar en marcha).
    """
    builder = make_project(Path(tempfile.mkdtemp(prefix="imagen-", dir=shared_tmp)), build=True)
    result = builder.compose("build", "-q", timeout=900)
    assert result.returncode == 0, result.stderr
    return TEST_IMAGE


@pytest.fixture
def project(tmp_path, image):
    """Proyecto temporal con `.env` del usuario actual y `data/` vacía."""
    proj = make_project(tmp_path)
    yield proj
    proj.down()
