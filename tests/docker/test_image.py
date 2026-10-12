"""Requisitos «Imagen con Python 3.12 sin archivos de desarrollo» y «Ejecución
con un usuario sin privilegios» (sin Compose), y escenario «Configuración
local fuera de la imagen».

Todo se lanza con `--entrypoint` y sin red: nunca se ejecuta la ingesta.
"""

from tests.docker.helpers import docker


def in_image(image, entrypoint, *args):
    return docker("run", "--rm", "--network", "none", "--entrypoint", entrypoint, image, *args,
                  timeout=300)


def test_python_version(image):
    result = in_image(image, "python", "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("Python 3.12.")


def test_pytest_is_not_installed(image):
    result = in_image(image, "python", "-c", "import pytest")
    assert result.returncode != 0
    assert "No module named 'pytest'" in result.stderr


def test_no_database_or_env_anywhere(image):
    result = in_image(image, "find", "/", "-xdev",
                      "(", "-name", "prices.db", "-o", "-name", ".env", ")", "-print")
    assert result.stdout.strip() == ""
    result = in_image(image, "find", "/app", "-name", "*.db")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_app_folder_only_has_code(image):
    result = in_image(image, "ls", "-A", "/app")
    assert result.returncode == 0, result.stderr
    assert sorted(result.stdout.split()) == ["container", "src"]


def test_default_user_is_not_root(image):
    uid = in_image(image, "id", "-u")
    gid = in_image(image, "id", "-g")
    assert uid.returncode == 0 and gid.returncode == 0
    assert int(uid.stdout) != 0
    assert int(gid.stdout) != 0
