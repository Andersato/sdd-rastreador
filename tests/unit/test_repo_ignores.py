"""Escenario «Fuera del repo y de la imagen» (parte del repo): `backups/` no se sube."""

import subprocess

from tests.helpers import REPO_ROOT


def test_backups_folder_is_ignored_by_git():
    result = subprocess.run(["git", "check-ignore", "-q", "backups/prices-2026-10-17.db.gz"],
                            cwd=REPO_ROOT)
    assert result.returncode == 0


def test_backups_folder_is_excluded_from_docker_context():
    lines = (REPO_ROOT / ".dockerignore").read_text().splitlines()
    assert "backups/" in lines
