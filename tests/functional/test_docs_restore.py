"""Requisito «Restauración documentada y probada» (`database-backup`): lo que
`docs/restore.md` debe decir. La prueba real la hace el usuario (tarea 3.7)."""

import re

import pytest

from tests.helpers import REPO_ROOT


@pytest.fixture(scope="module")
def doc():
    return (REPO_ROOT / "docs" / "restore.md").read_text(encoding="utf-8")


def code_blocks(text):
    return "\n".join(re.findall(r"```sh\n(.*?)```", text, flags=re.S))


def test_mac_restore_in_a_new_folder_with_checks(doc):
    """Escenario: Restauración en el Mac (procedimiento)."""
    mac = doc.split("## 1. En el Mac", 1)[1].split("## 2.", 1)[0]
    code = code_blocks(mac)
    assert "mkdir \"$DESTINO\"" in code and "gunzip -c" in code
    assert "PRAGMA integrity_check" in code and "SELECT COUNT(*) FROM snapshots" in code
    assert "data/prices.db" not in code
    assert "línea del log del VPS" in mac


def test_vps_restore_with_scheduler_stopped_and_old_db_set_aside(doc):
    """Escenario: Destino ocupado."""
    vps = doc.split("## 2. En un VPS", 1)[1].split("## Prueba", 1)[0]
    code = code_blocks(vps)
    lines = code.splitlines()
    stop = next(i for i, line in enumerate(lines) if "docker compose stop" in line)
    aside = next(i for i, line in enumerate(lines) if "mv data/prices.db" in line)
    check = next(i for i, line in enumerate(lines) if "integrity_check" in line)
    up = next(i for i, line in enumerate(lines) if "docker compose up -d" in line)
    assert stop < aside < check < up
    assert "SELECT COUNT(*) FROM snapshots" in code
    assert not re.search(r"\brm\b[^\n]*data/prices\.db", code)


def test_never_overwrites_an_existing_db(doc):
    assert "nunca se sobrescribe un `prices.db` que ya existe" in doc


def test_result_table(doc):
    """Escenario: Resultado anotado (la tabla; los valores los pone la tarea 3.7)."""
    table = doc.split("## Prueba de la restauración en el Mac", 1)[1]
    assert "| Fecha | Copia usada |" in table and "Capturas restauradas" in table
