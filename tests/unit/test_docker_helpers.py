"""Helpers de los tests con Docker, comprobados sin Docker."""

import signal
import sqlite3
import subprocess
import sys

import pytest

from tests.docker import helpers
from tests.docker.helpers import (
    CLOSED_PORT_URL,
    UNRESOLVABLE_URL,
    Project,
    check_url,
    docker_env,
    recover,
)
from tests.helpers import db_dump


@pytest.fixture
def no_subprocess(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no se debía llamar a Docker")

    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/",
        "http://127.0.0.1:8080/api",
        "http://example.com/api",
    ],
)
def test_run_ingest_rejects_non_test_urls_before_calling_docker(tmp_path, no_subprocess, url):
    project = Project(root=tmp_path, name="pgtest-x")
    with pytest.raises(ValueError):
        project.run_ingest(url=url)
    with pytest.raises(ValueError):
        project.start_ingest(url=url, container_name="pgtest-x")


@pytest.mark.parametrize("args", [("--url", "http://example.com/api"), ("--url=http://example.com/api",)])
def test_run_ingest_rejects_a_second_url(tmp_path, no_subprocess, args):
    project = Project(root=tmp_path, name="pgtest-x")
    with pytest.raises(ValueError):
        project.run_ingest(*args, url=CLOSED_PORT_URL)
    with pytest.raises(ValueError):
        project.start_ingest(*args, url=CLOSED_PORT_URL, container_name="pgtest-x")


@pytest.mark.parametrize(
    "url", [CLOSED_PORT_URL, UNRESOLVABLE_URL, "http://host.docker.internal:5123/api"]
)
def test_check_url_accepts_test_destinations(url):
    check_url(url)


def test_docker_env_does_not_inherit_user_or_proxy_variables(monkeypatch):
    for name in ("HOST_UID", "HOST_GID", "http_proxy", "HTTPS_PROXY", "no_proxy", "COMPOSE_FILE"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("DOCKER_CONTEXT", "orbstack")
    env = docker_env()
    assert set(env) <= {"PATH", "HOME"} | {k for k in env if k.startswith("DOCKER_")}
    assert env["DOCKER_CONTEXT"] == "orbstack"
    assert "HOST_UID" not in env and "HOST_GID" not in env
    assert docker_env({"HOST_UID": "1001"})["HOST_UID"] == "1001"


CRASH_WRITER = """
import os, signal, sqlite3, sys
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("PRAGMA cache_size = 1")
conn.execute("BEGIN IMMEDIATE")
conn.executemany("INSERT INTO t VALUES (?)", ((i,) for i in range(2, 20000)))
conn.execute("UPDATE t SET x = 99 WHERE x = 1")
os.kill(os.getpid(), signal.SIGKILL)
"""


def test_recover_rolls_back_a_hot_journal(tmp_path):
    db = tmp_path / "prices.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    # Un proceso que muere con SIGKILL en mitad de la transacción, sin
    # ROLLBACK: lo mismo que `docker stop` durante el guardado.
    killed = subprocess.run([sys.executable, "-c", CRASH_WRITER, str(db)])
    assert killed.returncode == -signal.SIGKILL
    assert (tmp_path / "prices.db-journal").exists()

    recover(db)

    assert not (tmp_path / "prices.db-journal").exists()
    assert db_dump(db)["t"] == [(1,)]


def test_recover_ignores_missing_database(tmp_path):
    recover(tmp_path / "no-existe.db")
    assert not (tmp_path / "no-existe.db").exists()


def test_make_project_never_touches_repo_env(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "REPO_ROOT", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "docker-compose.yml").write_text(f"image: {helpers.IMAGE}\n")
    project = helpers.make_project(tmp_path / "tmp", uid=1001, gid=1001)
    assert (project.root / ".env").read_text() == (
        "HOST_UID=1001\nHOST_GID=1001\nCOLLECTION_ENABLED=true\n")
    assert not (tmp_path / "repo" / ".env").exists()
    assert project.data.is_dir()
    assert project.backups.is_dir()


# --- Barrera: los tests no tocan el proyecto real -----------------------------

@pytest.mark.parametrize("args", [
    ("compose", "up", "-d"),
    ("compose", "-p", "sdd-rastreador", "stop"),
    ("compose", "-p", "pgtest-x", "-f", helpers.REAL_COMPOSE_FILE, "build"),
    ("stop", f"{helpers.REAL_PROJECT}-scheduler-1"),
    ("restart", f"{helpers.REAL_PROJECT}-scheduler-1"),
    ("build", "-t", helpers.IMAGE, "."),
    ("rmi", f"{helpers.IMAGE}:latest"),
    ("run", "-v", f"{helpers.REAL_DATA}:/app/data", helpers.TEST_IMAGE),
    ("run", "-v", f"{helpers.REAL_BACKUPS}:/app/backups", helpers.TEST_IMAGE),
])
def test_guard_rejects_real_project(args, no_subprocess):
    with pytest.raises(ValueError):
        helpers.docker(*args)


def test_guard_allows_test_projects():
    helpers.guard_docker_args(["compose", "-p", "pgtest-abcd", "-f", "/tmp/x/docker-compose.yml",
                               "up", "-d"])
    helpers.guard_docker_args(["stop", "pgtest-1234"])
    helpers.guard_docker_args(["run", "--rm", helpers.TEST_IMAGE])


def test_real_data_is_rejected_by_cli_helpers():
    from tests.helpers import REAL_DATA, run_check, run_cli, start_cli
    from tests.storage_helpers import ingest

    db = REAL_DATA / "prices.db"
    for call in (lambda: run_cli("http://127.0.0.1:9/api", db),
                 lambda: start_cli("http://127.0.0.1:9/api", db),
                 lambda: run_check("http://127.0.0.1:9/api", db, "2026-10-12T12:17:00Z"),
                 lambda: ingest(db, {})):
        with pytest.raises(ValueError, match="data/ real"):
            call()


def test_run_backup_goes_through_the_guard(tmp_path, monkeypatch):
    """2.7: `run_backup` usa un proyecto `pgtest-…` y pasa por la barrera."""
    seen = []
    monkeypatch.setattr(helpers, "guard_docker_args", lambda args: seen.append(list(args)))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    project = Project(root=tmp_path, name="pgtest-abcd")
    project.run_backup(env={"COLLECTION_ENABLED": " TRUE "})
    args = seen[0]
    assert args[:3] == ["compose", "-p", "pgtest-abcd"]
    assert args[-1] == "backup"
    assert "COLLECTION_ENABLED= TRUE " in args


def test_run_backup_rejects_real_project(tmp_path, no_subprocess):
    project = Project(root=tmp_path, name="sdd-rastreador")
    with pytest.raises(ValueError):
        project.run_backup()
