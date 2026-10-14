"""Utilidades de los tests con Docker.

Cada test trabaja en un proyecto temporal con su propio `docker-compose.yml`,
`.env` y `data/`: nunca se monta el `data/` real ni se escribe el `.env` del
repo. La ingesta solo se lanza con `--url` hacia el servidor local (o hacia
destinos que no pueden llegar a la API real), porque el bloqueo de red de
`tests/conftest.py` no alcanza al contenedor.
"""

import os
import secrets
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from tests.helpers import REPO_ROOT

IMAGE = "precios-gasolineras-ingest"  # la del proyecto real: los tests no la tocan
TEST_IMAGE = "precios-gasolineras-ingest-test"
# Nombre del proyecto de Compose real (el de la carpeta del repo).
REAL_PROJECT = REPO_ROOT.name.lower()
REAL_COMPOSE_FILE = str(REPO_ROOT / "docker-compose.yml")
REAL_DATA = (REPO_ROOT / "data").resolve()
TEST_PREFIX = "pgtest"
SERVICE = "ingest"
SCHEDULER = "scheduler"
OVERRIDE = "test-scheduler.yml"
CONTAINER_DB = "/app/data/prices.db"
HOST_ALIAS = "host.docker.internal"
# Destinos sin servidor: puerto cerrado del propio contenedor y nombre que
# nunca se resuelve (RFC 2606).
CLOSED_PORT_URL = "http://127.0.0.1:9/api"
UNRESOLVABLE_URL = "http://api.precios.invalid/api"
NO_PROXY_VALUE = f"{HOST_ALIAS},127.0.0.1,localhost"
BUILD_FILES = ("Dockerfile", ".dockerignore", "src", "container")


def docker_env(extra=None) -> dict[str, str]:
    """Entorno mínimo para `docker`: sin `HOST_UID`/`HOST_GID` ni proxies heredados."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME") or k.startswith("DOCKER_")}
    env.update(extra or {})
    return env


def guard_docker_args(args) -> None:
    """Barrera: ningún test puede tocar el proyecto real de Compose.

    Con el programador real en marcha, un test no debe pararlo, reconstruirlo
    ni reiniciarlo. Se rechaza: `compose` sin `-p pgtest-…`, el
    `docker-compose.yml` del repo, la imagen o los contenedores del proyecto
    real y montar el `data/` real.
    """
    args = [str(arg) for arg in args]
    if args and args[0] == "compose":
        if "-p" not in args or not args[args.index("-p") + 1].startswith(TEST_PREFIX):
            raise ValueError(f"compose en los tests solo con -p {TEST_PREFIX}-…: {args}")
    for arg in args:
        if arg == REAL_COMPOSE_FILE:
            raise ValueError("los tests no pueden usar el docker-compose.yml del proyecto real")
        if arg.startswith(f"{REAL_PROJECT}-") or arg.startswith(f"{REAL_PROJECT}_"):
            raise ValueError(f"los tests no pueden tocar los contenedores del proyecto real: {arg}")
        if arg in (IMAGE, f"{IMAGE}:latest"):
            raise ValueError(f"los tests no pueden usar ni sustituir la imagen real {IMAGE}")
        if str(REAL_DATA) in arg:
            raise ValueError("los tests no pueden usar la carpeta data/ real")


def docker(*args, env=None, cwd=None, timeout=300, input=None) -> subprocess.CompletedProcess:
    guard_docker_args(args)
    return subprocess.run(
        ["docker", *args],
        env=docker_env(env),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input,
    )


def docker_available() -> bool:
    try:
        return docker("info", timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def container_url(server, path: str) -> str:
    """URL del servidor local vista desde el contenedor."""
    return f"http://{HOST_ALIAS}:{server.port}{path}"


def check_url(url) -> None:
    """Impide lanzar la ingesta contra algo que no sea un destino de prueba."""
    if url is None:
        raise ValueError("la ingesta en Docker solo se lanza con --url (nunca contra la API real)")
    if url in (CLOSED_PORT_URL, UNRESOLVABLE_URL):
        return
    host = urlparse(url).hostname or ""
    if host != HOST_ALIAS:
        raise ValueError(f"URL no permitida en los tests con Docker: {url!r}")


def check_args(args) -> None:
    """Impide colar otro `--url` en los argumentos (argparse usaría el último)."""
    if any(arg == "--url" or arg.startswith("--url=") for arg in args):
        raise ValueError("la URL se pasa con el parámetro url=, no en los argumentos")


def recover(db_path) -> None:
    """Abre la base en lectura y escritura y la lee, para que SQLite deshaga
    un diario pendiente como haría la siguiente ingesta (`db_dump` abre en
    solo lectura y no puede hacerlo)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    finally:
        conn.close()


def dir_state(path) -> dict[str, bytes] | None:
    """Nombres y contenido de los archivos de una carpeta, o None si no existe."""
    path = Path(path)
    if not path.exists():
        return None
    return {
        str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()
    }


def unique_name(prefix=TEST_PREFIX) -> str:
    return f"{prefix}-{secrets.token_hex(4)}"


@dataclass
class Project:
    """Copia temporal del proyecto para lanzar `docker compose`."""

    root: Path
    name: str

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def db(self) -> Path:
        return self.data / "prices.db"

    @property
    def compose_file(self) -> Path:
        return self.root / "docker-compose.yml"

    def write_env(self, uid=None, gid=None, drop=(), **extra) -> None:
        values = {"HOST_UID": uid if uid is not None else os.getuid(),
                  "HOST_GID": gid if gid is not None else os.getgid(), **extra}
        lines = [f"{k}={v}\n" for k, v in values.items() if k not in drop]
        (self.root / ".env").write_text("".join(lines))

    def remove_env(self) -> None:
        (self.root / ".env").unlink(missing_ok=True)

    def compose_files(self) -> list[str]:
        files = ["-f", str(self.compose_file)]
        override = self.root / OVERRIDE
        if override.exists():
            files += ["-f", str(override)]
        return files

    def compose(self, *args, env=None, cwd=None, timeout=300) -> subprocess.CompletedProcess:
        return docker("compose", "-p", self.name, *self.compose_files(), *args,
                      env=env, cwd=cwd or self.root, timeout=timeout)

    def start_scheduler(self, url, timeout=300) -> subprocess.CompletedProcess:
        """`docker compose up -d` con el programador apuntando a `url` (obligatoria).

        Es la única forma de arrancar el programador en los tests: la URL va
        en un archivo de Compose adicional, junto con NO_PROXY, para que
        nunca llame a la API real.
        """
        check_url(url)
        (self.root / OVERRIDE).write_text(
            "services:\n"
            f"  {SCHEDULER}:\n"
            "    environment:\n"
            f"      INGEST_API_URL: \"{url}\"\n"
            f"      NO_PROXY: \"{NO_PROXY_VALUE}\"\n"
            f"      no_proxy: \"{NO_PROXY_VALUE}\"\n"
        )
        return self.compose("up", "-d", timeout=timeout)

    def scheduler_logs(self) -> str:
        result = self.compose("logs", "--no-log-prefix", SCHEDULER, timeout=60)
        return result.stdout + result.stderr

    def exec_check(self, timeout=120) -> subprocess.CompletedProcess:
        """Comprobación horaria simulada: el mismo comando que lanza supercronic."""
        return self.compose("exec", "-T", SCHEDULER, "python", "/app/container/check.py",
                            timeout=timeout)

    def _run_args(self, container_name, entrypoint, args) -> list[str]:
        run = ["compose", "-p", self.name, "-f", str(self.compose_file), "run", "--rm", "-T",
               "--name", container_name,
               "-e", f"NO_PROXY={NO_PROXY_VALUE}", "-e", f"no_proxy={NO_PROXY_VALUE}"]
        if entrypoint is not None:
            run += ["--entrypoint", entrypoint]
        return run + [SERVICE, *args]

    def run_ingest(self, *args, url, container_name=None, cwd=None, timeout=300):
        """Lanza la ingesta con `docker compose run`; `url` es obligatoria."""
        check_url(url)
        check_args(args)
        container_name = container_name or unique_name()
        result = docker(*self._run_args(container_name, None, ["--url", url, *args]),
                        cwd=cwd or self.root, timeout=timeout)
        result.container_name = container_name
        return result

    def start_ingest(self, *args, url, container_name) -> subprocess.Popen:
        """Como `run_ingest`, pero en segundo plano (para interrumpirla)."""
        check_url(url)
        check_args(args)
        run_args = self._run_args(container_name, None, ["--url", url, *args])
        guard_docker_args(run_args)
        return subprocess.Popen(
            ["docker", *run_args],
            env=docker_env(), cwd=self.root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def run_entrypoint(self, entrypoint, *args, timeout=120) -> subprocess.CompletedProcess:
        """Lanza el servicio con otro programa de arranque (p. ej. `id`): no ejecuta la ingesta."""
        return docker(*self._run_args(unique_name(), entrypoint, list(args)),
                      cwd=self.root, timeout=timeout)

    def down(self) -> None:
        """Borra la red que deja `run --rm`. Las variables solo sirven para que
        Compose pueda leer el archivo aunque el test haya quitado `.env`."""
        result = self.compose("down", "--remove-orphans", timeout=120,
                              env={"HOST_UID": "1", "HOST_GID": "1"})
        assert result.returncode == 0, result.stderr


def make_project(tmp_path, *, uid=None, gid=None, env=True, data=True, build=False,
                 image=None) -> Project:
    """Proyecto temporal con `docker-compose.yml`, `.env` y `data/`.

    `build=True` copia también lo necesario para construir la imagen ahí.
    La imagen de los servicios es siempre una de test (`TEST_IMAGE` o la que
    se indique en `image`), nunca la del proyecto real.
    """
    image = image or TEST_IMAGE
    root = Path(tmp_path) / unique_name("proyecto")
    root.mkdir(parents=True)
    compose = (REPO_ROOT / "docker-compose.yml").read_text()
    old = f"image: {IMAGE}\n"
    if compose.count(old) != 1:
        raise AssertionError("docker-compose.yml no tiene la línea de imagen esperada")
    compose = compose.replace(old, f"image: {image}\n")
    (root / "docker-compose.yml").write_text(compose)
    if build:
        for name in BUILD_FILES:
            src = REPO_ROOT / name
            if src.is_dir():
                shutil.copytree(src, root / name, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, root / name)
    project = Project(root=root, name=unique_name())
    if env:
        project.write_env(uid, gid)
    if data:
        project.data.mkdir()
    return project


def container_exists(name: str) -> bool:
    result = docker("ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}", timeout=60)
    return name in result.stdout.split()
