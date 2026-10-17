"""Herramientas de medición de `tools/perf/` (prices-api, D13): nunca tocan el
histórico real ni modifican la copia de origen."""

import importlib.util

import pytest

from tests.api_helpers import basic_db, priced, save
from tests.helpers import REPO_ROOT, db_dump
from tests.storage_helpers import query


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "tools" / "perf" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_year_db = load("make_year_db")


@pytest.fixture
def copy(tmp_path):
    path = tmp_path / "copia.db"
    basic_db(path)
    return path


def test_refuses_an_existing_destination(tmp_path, copy):
    destination = tmp_path / "ya.db"
    destination.write_text("no tocar")
    with pytest.raises(make_year_db.Refused):
        make_year_db.make(destination, copy, 10)
    assert destination.read_text() == "no tocar"


@pytest.mark.parametrize("which", ["destination", "copy"])
def test_refuses_the_real_data_folder(tmp_path, copy, which):
    real = REPO_ROOT / "data" / "nunca-se-crea.db"
    args = {"destination": tmp_path / "nueva.db", "copy": copy, which: real}
    with pytest.raises(make_year_db.Refused, match="histórico real"):
        make_year_db.make(args["destination"], args["copy"], 10)
    assert not real.exists()


def test_main_exit_code_when_refused(tmp_path, copy, capsys):
    (tmp_path / "ya.db").write_text("x")
    assert make_year_db.main([str(tmp_path / "ya.db"), str(copy), "--captures", "3"]) == 2
    assert "ya existe" in capsys.readouterr().err


def test_repeats_the_last_capture_every_six_hours(tmp_path, copy):
    save(copy, priced("4375", {"Gasoleo A": "1,459"}), priced("5120", {"Gasoleo A": "1,479"}))
    before = db_dump(copy)
    destination = tmp_path / "anio.db"
    assert make_year_db.make(destination, copy, 6, progress=lambda line: None) == 6
    assert db_dump(copy) == before  # la copia de origen no cambia
    snapshots = query(destination, "SELECT id, downloaded_at, source_date FROM snapshots ORDER BY id")
    assert len(snapshots) == 6
    assert snapshots[2][1:] == ("2026-10-16T13:26:37Z", "2026-10-16T15:26:37")
    assert snapshots[5][1] == "2026-10-17T07:26:37Z"
    per_snapshot = query(destination, "SELECT snapshot_id, count(*) FROM prices GROUP BY 1")
    assert [n for _, n in per_snapshot[1:]] == [2] * 5
