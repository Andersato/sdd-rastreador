"""Requisito "Ubicación de la base de datos" con la CLI real y sin `--db`.

Para no escribir nunca en el `data/` real, se copia `src/` a una carpeta
temporal que hace de proyecto y la CLI se lanza desde esa copia.
"""

import shutil

import pytest

from tests.helpers import REPO_ROOT, run_cli
from tests.storage_helpers import query

REAL_DEFAULT_DB = REPO_ROOT / "data" / "prices.db"


def file_state(path):
    """Estado del archivo para comprobar que no se toca: None si no existe."""
    if not path.exists():
        return None
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns, path.read_bytes())


@pytest.fixture
def project_copy(tmp_path):
    project = tmp_path / "sdd-rastreador"
    shutil.copytree(REPO_ROOT / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__"))
    return project


def test_scenario_launched_from_another_folder(http_server, tmp_path, project_copy):
    """Escenario: Lanzada desde otra carpeta."""
    elsewhere = tmp_path / "tmp"
    elsewhere.mkdir()
    real_before = file_state(REAL_DEFAULT_DB)
    url = http_server.add_fixture("/api", "valid_two_stations.json")

    from_elsewhere = run_cli(url, None, cwd=elsewhere, project_root=project_copy)
    assert from_elsewhere.returncode == 0, from_elsewhere.stderr
    db = project_copy / "data" / "prices.db"
    assert db.exists()
    assert list(elsewhere.iterdir()) == []

    # Lanzada desde la carpeta del proyecto, usa el mismo archivo.
    from_project = run_cli(url, None, cwd=project_copy, project_root=project_copy)
    assert from_project.returncode == 0, from_project.stderr
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(2,)]
    assert sorted(p.name for p in (project_copy / "data").iterdir()) == ["prices.db"]

    assert file_state(REAL_DEFAULT_DB) == real_before


def test_scenario_db_option_with_missing_folder(http_server, tmp_path, project_copy):
    """Escenario: Ruta indicada con --db (la carpeta no existe y el data/ del proyecto no se toca)."""
    db = tmp_path / "pruebas" / "otra.db"
    real_before = file_state(REAL_DEFAULT_DB)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db, cwd=tmp_path, project_root=project_copy)
    assert result.returncode == 0, result.stderr
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert not (project_copy / "data").exists()
    assert file_state(REAL_DEFAULT_DB) == real_before
