"""Requisito «Contexto de construcción sin archivos ajenos a la ingesta».

Se construye desde una carpeta temporal con archivos falsos que nunca deben
llegar a Docker. Las imágenes usan etiquetas `:test-*` y se borran al final.
"""

import shutil

import pytest

from tests.docker.helpers import BUILD_FILES, IMAGE, docker, unique_name
from tests.helpers import REPO_ROOT

FAKE_FILES = {
    "data/prices.db": b"x" * (4 * 1024 * 1024),
    ".env": b"HOST_UID=501\nHOST_GID=20\n",
    ".venv/bin/python": b"falso",
    "tests/test_x.py": b"def test_x(): pass\n",
    "openspec/specs/x/spec.md": b"# falso\n",
    "src/x.db": b"falso",
}


@pytest.fixture
def context(tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    for name in BUILD_FILES:
        src = REPO_ROOT / name
        if src.is_dir():
            shutil.copytree(src, ctx / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, ctx / name)
    for rel, content in FAKE_FILES.items():
        path = ctx / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return ctx


@pytest.fixture
def tags():
    created = []

    def new():
        tag = f"{IMAGE}:test-{unique_name('ctx')}"
        created.append(tag)
        return tag

    yield new
    for tag in created:
        docker("image", "rm", "-f", tag, timeout=120)


def build(ctx, tag, dockerfile=None):
    args = ["build", "-q", "-t", tag]
    if dockerfile is not None:
        args += ["-f", str(dockerfile)]
    result = docker(*args, str(ctx), timeout=900)
    assert result.returncode == 0, result.stderr


def app_files(tag):
    result = docker("run", "--rm", "--network", "none", "--entrypoint", "sh", tag, "-c",
                    "cd /app && find . -type f -exec sha256sum {} + | sort -k2", timeout=300)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_context_excludes_local_files(image, context, tags, tmp_path):
    aux = tmp_path / "Dockerfile.ctx"
    aux.write_text("FROM python:3.12-slim-bookworm\nCOPY . /ctx\n")
    tag = tags()
    build(context, tag, dockerfile=aux)
    result = docker("run", "--rm", "--network", "none", "--entrypoint", "find", tag,
                    "/ctx", "-print", timeout=300)
    assert result.returncode == 0, result.stderr
    sent = {line.removeprefix("/ctx/") for line in result.stdout.split()}
    for rel in FAKE_FILES:
        assert rel not in sent
    for folder in ("data", ".venv", "tests", "openspec"):
        assert folder not in sent
    assert "src/ingestion/__main__.py" in sent


def test_changing_only_tests_gives_same_app_files(image, context, tags):
    first, second = tags(), tags()
    build(context, first)
    (context / "tests" / "test_x.py").write_text("def test_x(): assert True\n")
    (context / "tests" / "test_y.py").write_text("def test_y(): pass\n")
    build(context, second)
    files = app_files(first)
    assert "./src/ingestion/__main__.py" in files
    assert files == app_files(second)


def in_image(tag, *args):
    return docker("run", "--rm", "--network", "none", "--entrypoint", args[0], tag, *args[1:],
                  timeout=300)


def test_image_built_with_local_files_excludes_them(image, context, tags):
    """Escenarios «Base de datos grande en ./data», «Configuración local fuera de
    la imagen» y «Sin tests, entorno, datos ni OpenSpec»: la carpeta tiene
    `data/prices.db` (4 MB), `.env`, `.venv/`, `tests/`, `openspec/` y otra `.db`,
    y se construye con el Dockerfile real."""
    tag = tags()
    build(context, tag)
    found = in_image(tag, "find", "/", "-xdev",
                     "(", "-name", "prices.db", "-o", "-name", ".env", ")", "-print")
    assert found.stdout.strip() == ""
    dbs = in_image(tag, "find", "/app", "-name", "*.db")
    assert dbs.returncode == 0, dbs.stderr
    assert dbs.stdout.strip() == ""
    listing = in_image(tag, "ls", "-A", "/app")
    assert listing.returncode == 0, listing.stderr
    assert sorted(listing.stdout.split()) == ["container", "src"]
