"""Programa de arranque de la API (`container/api.py`), sin Docker.

Requisito «API sin usuario root»: con usuario o grupo 0 no se lanza ni se
carga FastAPI o uvicorn.
"""

import importlib.util
import subprocess
import sys

import pytest

from tests.helpers import REPO_ROOT

PATH = REPO_ROOT / "container" / "api.py"


def load_api():
    spec = importlib.util.spec_from_file_location("container_api", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api = load_api()


@pytest.mark.parametrize(("uid", "gid", "message"), [
    (0, 20, "no se permite ejecutar la API como root (usuario 0); revisa HOST_UID en .env"),
    (0, 0, "no se permite ejecutar la API como root (usuario 0); revisa HOST_UID en .env"),
    (1000, 0, "no se permite ejecutar la API con el grupo root (grupo 0); revisa HOST_GID en .env"),
])
def test_refuses_root(capsys, uid, gid, message):
    calls = []
    code = api.main(uid, gid, {}, serve=calls.append)
    assert code == 2
    assert calls == []
    assert capsys.readouterr().err.strip() == f"Error: {message}"


def test_serves_with_a_normal_user():
    calls = []
    env = {"CAPTURE_INTERVAL_HOURS": "12"}
    assert api.main(1000, 1000, env, serve=calls.append) == 0
    assert calls == [env]


def test_root_does_not_load_fastapi_or_uvicorn():
    """Con root, el proceso termina sin haber importado FastAPI ni uvicorn."""
    script = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('a', {str(PATH)!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "code = m.main(0, 0, {})\n"
        "loaded = [n for n in sys.modules if n.split('.')[0] in ('fastapi', 'uvicorn', 'starlette')]\n"
        "print(code, loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            cwd=REPO_ROOT, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2 []"
