"""Bloqueo de la carpeta de la base: una sola ingesta a la vez (D1)."""

import os
import signal
import subprocess
import sys
import time

import pytest

from src.ingestion.errors import IngestionBusy, StorageError
from src.ingestion.lock import data_dir_lock
from tests.helpers import REPO_ROOT

HOLDER = """
import sys, time
from pathlib import Path
from src.ingestion.lock import data_dir_lock
with data_dir_lock(Path(sys.argv[1])):
    print("locked", flush=True)
    time.sleep(60)
"""


def hold_lock(folder):
    """Proceso aparte que coge el bloqueo de `folder` y lo mantiene."""
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(folder)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout.readline().strip() == "locked"
    return proc


@pytest.fixture
def holder():
    procs = []

    def start(folder):
        proc = hold_lock(folder)
        procs.append(proc)
        return proc

    yield start
    for proc in procs:
        proc.kill()
        proc.wait()


def test_second_process_is_rejected_without_waiting(tmp_path, holder):
    holder(tmp_path)
    start = time.monotonic()
    with pytest.raises(IngestionBusy, match="ya hay otra ingesta en curso"):
        with data_dir_lock(tmp_path):
            pass
    assert time.monotonic() - start < 2


def test_different_folders_do_not_conflict(tmp_path, holder):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    holder(a)
    with data_dir_lock(b):
        pass


def test_lock_is_released_after_kill_9(tmp_path, holder):
    proc = holder(tmp_path)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait()
    with data_dir_lock(tmp_path):
        pass


def test_lock_is_released_on_exit(tmp_path):
    with data_dir_lock(tmp_path):
        pass
    with data_dir_lock(tmp_path):
        pass


def test_lock_leaves_no_files(tmp_path):
    db = tmp_path / "prices.db"
    db.write_bytes(b"contenido")
    with data_dir_lock(tmp_path):
        pass
    assert [p.name for p in tmp_path.iterdir()] == ["prices.db"]
    assert db.read_bytes() == b"contenido"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora los permisos de la carpeta")
def test_unreadable_folder_is_a_controlled_error(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    folder.chmod(0o300)
    try:
        with pytest.raises(StorageError, match="no se ha podido crear o escribir la base de datos"):
            with data_dir_lock(folder):
                pass
    finally:
        folder.chmod(0o700)
