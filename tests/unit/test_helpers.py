import sqlite3

import pytest

from tests.helpers import db_dump, run_cli


def test_run_cli_rejects_external_url(tmp_path):
    with pytest.raises(ValueError, match="solo acepta URLs locales"):
        run_cli(
            "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/",
            tmp_path / "x.db",
        )


def test_db_dump_missing_file(tmp_path):
    assert db_dump(tmp_path / "nope.db") == "no existe"


def test_db_dump_contents(tmp_path):
    path = tmp_path / "x.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (a)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    assert db_dump(path) == {"user_version": 3, "t": [(1,)]}


def test_run_cli_without_db_rejects_real_project(http_server):
    # Sin --db la CLI usaría el data/ real del proyecto: run_cli lo impide.
    url = http_server.add("/api", body=b"{}")
    with pytest.raises(ValueError, match="copia del proyecto"):
        run_cli(url, None)
    assert http_server.total_requests() == 0
