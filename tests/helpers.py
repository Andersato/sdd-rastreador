"""Utilidades compartidas por los tests."""

import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
REAL_DATA = (REPO_ROOT / "data").resolve()
PROXY_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


def check_not_real_data(db) -> None:
    """Barrera: ningún test escribe en el `data/` real del proyecto."""
    if db is not None and Path(db).resolve().is_relative_to(REAL_DATA):
        raise ValueError(f"los tests no pueden usar la carpeta data/ real: {db}")


def free_port() -> int:
    """Un puerto local libre en este momento."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def closed_port_url(path: str = "/api") -> str:
    """URL local a un puerto sin nadie escuchando: la conexión se rechaza."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}{path}"


def db_dump(path) -> object:
    """Contenido completo de la base (tablas y `user_version`), o "no existe"."""
    path = Path(path)
    if not path.exists():
        return "no existe"
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        dump = {"user_version": conn.execute("PRAGMA user_version").fetchone()[0]}
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        for table in tables:
            dump[table] = sorted(conn.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr)
        return dump
    finally:
        conn.close()


def run_cli(url, db, *extra_args, deadline=None, env=None, cwd=None, timeout=30, project_root=None):
    """Lanza `python -m src.ingestion` como subproceso, siempre contra el servidor local.

    Es la única forma de lanzar la CLI en los tests: impide que un test olvide
    `--url` y acabe llamando a la API real.

    `db=None` lanza la CLI sin `--db` (ruta por defecto). Solo se permite con
    `project_root` apuntando a una copia del proyecto, nunca al repo real, para
    que ningún test escriba en el `data/` real.
    """
    host = urlparse(url).hostname
    if host not in LOCAL_HOSTS:
        raise ValueError(f"run_cli solo acepta URLs locales, no {url!r}")
    check_not_real_data(db)
    root = Path(project_root) if project_root is not None else REPO_ROOT
    if db is None and root.resolve() == REPO_ROOT.resolve():
        raise ValueError("run_cli sin --db solo se permite con una copia del proyecto (project_root)")
    args = [sys.executable, "-m", "src.ingestion", "--url", url]
    if db is not None:
        args += ["--db", str(db)]
    args += list(extra_args)
    if deadline is not None:
        args += ["--deadline", str(deadline)]
    full_env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
    full_env["no_proxy"] = full_env["NO_PROXY"] = "127.0.0.1,localhost"
    full_env["PYTHONPATH"] = str(root)
    full_env.update(env or {})
    return subprocess.run(
        args,
        cwd=cwd or root,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def start_cli(url, db, *extra_args, deadline=None):
    """Como `run_cli`, pero sin esperar: devuelve el `Popen` (salidas en tuberías)."""
    host = urlparse(url).hostname
    if host not in LOCAL_HOSTS:
        raise ValueError(f"start_cli solo acepta URLs locales, no {url!r}")
    check_not_real_data(db)
    args = [sys.executable, "-m", "src.ingestion", "--url", url, "--db", str(db), *extra_args]
    if deadline is not None:
        args += ["--deadline", str(deadline)]
    env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.Popen(args, cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def run_check(url, db, now, *extra_args, deadline=None, timeout=60):
    """Lanza una comprobación programada (`python -m src.ingestion.scheduled`) con reloj fijo.

    Como `run_cli`, solo contra el servidor local o un puerto cerrado local.
    """
    host = urlparse(url).hostname
    if host not in LOCAL_HOSTS:
        raise ValueError(f"run_check solo acepta URLs locales, no {url!r}")
    check_not_real_data(db)
    args = [sys.executable, "-m", "src.ingestion.scheduled", "--url", url, "--db", str(db),
            "--now", now, *extra_args]
    if deadline is not None:
        args += ["--deadline", str(deadline)]
    env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(args, cwd=REPO_ROOT, env=env, capture_output=True, text=True,
                          timeout=timeout)
