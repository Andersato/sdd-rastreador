"""Carpetas temporales de los tests de Docker (`tests/docker/conftest.py`).

Colima solo comparte `$HOME` con su máquina virtual: las carpetas que se montan
en los contenedores tienen que estar bajo `~/.cache/precios-gasolineras-tests/`.
"""

from pathlib import Path

import pytest

from tests.docker.conftest import SHARED_TMP_ROOT


def test_shared_root_is_under_home():
    assert SHARED_TMP_ROOT == Path.home() / ".cache" / "precios-gasolineras-tests"


def test_tmp_path_is_inside_this_run_folder(tmp_path, shared_tmp):
    assert shared_tmp.parent == SHARED_TMP_ROOT
    assert shared_tmp.name.startswith("run-")
    assert tmp_path.parent == shared_tmp
    assert tmp_path.name.startswith("test-")
    assert tmp_path.is_dir() and list(tmp_path.iterdir()) == []


_seen = []


@pytest.mark.parametrize("turn", [1, 2])
def test_each_test_gets_its_own_tmp_path(tmp_path, shared_tmp, turn):
    """Dos tests de la misma ejecución: misma carpeta `run-*`, `tmp_path` distintos."""
    _seen.append((shared_tmp, tmp_path))
    if turn == 2:
        (run_a, tmp_a), (run_b, tmp_b) = _seen[-2:]
        assert run_a == run_b
        assert tmp_a != tmp_b
