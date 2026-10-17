"""Documentación de la copia fuera del VPS (`database-backup`: «Descarga
programada en el Mac» y «Acceso restringido para las copias»), y el rsync de
Homebrew en el README."""

import re

import pytest

from tests.helpers import REPO_ROOT


@pytest.fixture(scope="module")
def doc():
    return (REPO_ROOT / "docs" / "offsite-backups.md").read_text(encoding="utf-8")


def test_launchd_instructions(doc):
    """Escenario: Instrucciones de launchd."""
    plist = re.search(r"```xml\n(.*?)```", doc, flags=re.S).group(1)
    assert "<key>StartCalendarInterval</key>" in plist
    assert re.search(r"<key>Hour</key>\s*<integer>10</integer>", plist)
    assert re.search(r"<key>Minute</key>\s*<integer>0</integer>", plist)
    assert "<key>RunAtLoad</key>" in plist and "<true/>" in plist
    assert "StandardOutPath" in plist and "precios-gasolineras-backups.log" in plist
    assert "<IP_DEL_VPS>" in plist and not re.search(r"\d+\.\d+\.\d+\.\d+", plist)
    for command in ("launchctl bootstrap", "launchctl print", "launchctl bootout"):
        assert command in doc
    assert "dormido" in doc and "al despertar" in doc
    assert "apagado" in doc and "al iniciar sesión" in doc


def test_dedicated_key_not_personal(doc):
    """Escenario: Sin la clave personal."""
    assert "~/.ssh/precios-backups" in doc
    assert 'ssh-keygen -t ed25519 -N ""' in doc
    assert "No uses `ssh-copy-id`" in doc
    assert 'command="/usr/bin/rrsync -ro /home/deploy/sdd-rastreador/backups",restrict' in doc


def test_homebrew_rsync_documented(doc):
    assert "brew install rsync" in doc
    assert "/usr/bin/rsync" in doc and "openrsync" in doc and "no sirve" in doc


def test_readme_mentions_homebrew_rsync():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    part = text.split("### Segunda copia en el Mac", 1)[1].split("\n## ", 1)[0]
    assert "brew install rsync" in part and "docs/offsite-backups.md" in part
    assert "python -m src.backup.pull" in part
