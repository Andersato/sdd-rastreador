"""Programa de arranque de la imagen (`container/entrypoint.py`), sin Docker."""

import importlib.util
import sys

import pytest

from tests.helpers import REPO_ROOT


def load_entrypoint():
    path = REPO_ROOT / "container" / "entrypoint.py"
    spec = importlib.util.spec_from_file_location("container_entrypoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entrypoint = load_entrypoint()


class Recorder:
    def __init__(self):
        self.calls = []

    def execv(self, path, argv):
        self.calls.append(("execv", path, list(argv)))

    def chdir(self, path):
        self.calls.append(("chdir", path))


def run(uid, gid, args):
    rec = Recorder()
    code = entrypoint.main(uid, gid, args, execv=rec.execv, chdir=rec.chdir)
    return code, rec.calls


@pytest.mark.parametrize(
    "uid, gid, args, message",
    [
        (0, 20, [], "como root (usuario 0)"),
        (0, 0, ["--help"], "como root (usuario 0)"),
        (1001, 0, [], "con el grupo root (grupo 0)"),
        (501, 20, ["--db", "/tmp/otra.db"], "la base de datos no se puede cambiar"),
        (501, 20, ["--db=/tmp/otra.db"], "la base de datos no se puede cambiar"),
        (501, 20, ["--url", "http://x/", "--db"], "la base de datos no se puede cambiar"),
    ],
)
def test_refuses_without_exec(capsys, uid, gid, args, message):
    code, calls = run(uid, gid, args)
    assert code == 2
    assert calls == []
    assert message in capsys.readouterr().err


def test_execs_ingestion_with_fixed_db_and_same_args():
    code, calls = run(501, 20, ["--url", "http://host.docker.internal:1234/api", "--help"])
    assert calls == [
        ("chdir", "/app"),
        (
            "execv",
            sys.executable,
            [sys.executable, "-m", "src.ingestion", "--db", "/app/data/prices.db",
             "--url", "http://host.docker.internal:1234/api", "--help"],
        ),
    ]


def test_ambiguous_abbreviation_is_left_to_argparse():
    # `--d` es ambigua (--db / --deadline): la rechaza argparse en la ingesta.
    code, calls = run(501, 20, ["--d", "x"])
    assert calls[-1][2][-2:] == ["--d", "x"]


def test_values_that_only_contain_db_are_not_refused():
    code, calls = run(501, 20, ["--url", "http://host.docker.internal:1/--db"])
    assert calls[-1][0] == "execv"
