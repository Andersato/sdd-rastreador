"""Requisitos «Imagen con Python 3.12 sin archivos de desarrollo» y «Ejecución
con un usuario sin privilegios» (sin Compose), y escenario «Configuración
local fuera de la imagen». Incluye las dependencias de la API (add-prices-api).

Todo se lanza con `--entrypoint` y sin red: nunca se ejecuta la ingesta.
"""

from tests.docker.helpers import docker
from tests.helpers import REPO_ROOT


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


def test_httpx_is_not_installed(image):
    result = in_image(image, "python", "-c", "import httpx")
    assert result.returncode != 0
    assert "No module named 'httpx'" in result.stderr


def pinned_requirements() -> set[str]:
    lines = (REPO_ROOT / "requirements.txt").read_text().splitlines()
    return {line.strip().lower().replace("_", "-") for line in lines
            if line.strip() and not line.startswith("#")}


def test_installed_packages_match_requirements(image):
    """Paquetes instalados = `requirements.txt` (aparte de `pip`, de la imagen base)."""
    result = in_image(image, "python", "-m", "pip", "list", "--format=freeze",
                      "--disable-pip-version-check")
    assert result.returncode == 0, result.stderr
    installed = {line.strip().lower().replace("_", "-") for line in result.stdout.splitlines()
                 if line.strip() and not line.lower().startswith("pip==")}
    assert installed == pinned_requirements()
    names = {line.split("==")[0] for line in installed}
    assert {"fastapi", "uvicorn", "starlette", "pydantic", "pydantic-core", "anyio",
            "h11", "click"} <= names


def test_fastapi_without_standard_extra(image):
    """Sin `[standard]`: ni `fastapi-cli` ni `uvicorn[standard]` (uvloop, httptools…)."""
    result = in_image(image, "python", "-c",
                      "import importlib.util as u;"
                      "print([m for m in ('fastapi_cli','uvloop','httptools','watchfiles',"
                      "'email_validator','jinja2','multipart') if u.find_spec(m)])")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


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
    assert sorted(result.stdout.split()) == ["container", "src", "web"]


def test_default_user_is_not_root(image):
    uid = in_image(image, "id", "-u")
    gid = in_image(image, "id", "-g")
    assert uid.returncode == 0 and gid.returncode == 0
    assert int(uid.stdout) != 0
    assert int(gid.stdout) != 0
