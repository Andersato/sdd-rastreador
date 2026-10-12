"""Requisitos «Usuario del host configurado y distinto de root» y «Ejecución
con un usuario sin privilegios» (con Compose)."""

import os

import pytest

from tests.docker.helpers import container_url, dir_state


@pytest.fixture
def api(http_server):
    http_server.add_fixture("/api", "valid_two_stations.json")
    return http_server


@pytest.mark.parametrize(
    "drop, missing",
    [(("HOST_UID", "HOST_GID"), "HOST_UID"), (("HOST_UID",), "HOST_UID"), (("HOST_GID",), "HOST_GID")],
)
def test_missing_user_config(project, api, drop, missing):
    if len(drop) == 2:
        project.remove_env()
    else:
        project.write_env(drop=drop)
    before = dir_state(project.data)
    result = project.run_ingest(url=container_url(api, "/api"))
    assert result.returncode != 0
    assert missing in result.stderr
    assert api.total_requests() == 0
    assert dir_state(project.data) == before


@pytest.mark.parametrize(
    "uid, gid, message",
    [(0, 20, "como root (usuario 0)"), (1001, 0, "con el grupo root (grupo 0)")],
)
def test_root_user_or_group_refused(project, api, uid, gid, message):
    project.write_env(uid=uid, gid=gid)
    before = dir_state(project.data)
    result = project.run_ingest(url=container_url(api, "/api"))
    assert result.returncode != 0
    assert message in result.stderr
    assert api.total_requests() == 0
    assert dir_state(project.data) == before


def test_runs_with_host_user(project):
    result = project.run_entrypoint("id")
    assert result.returncode == 0, result.stderr
    assert f"uid={os.getuid()} " in result.stdout
    assert f"gid={os.getgid()}" in result.stdout


@pytest.mark.parametrize("missing", ["HOST_UID", "HOST_GID"])
def test_empty_user_config_value(project, api, missing):
    """Escenario «Configuración del usuario ausente»: `.env` con el valor vacío."""
    (project.root / ".env").write_text(
        "".join(f"{k}={'' if k == missing else 1001}\n" for k in ("HOST_UID", "HOST_GID"))
    )
    before = dir_state(project.data)
    result = project.run_ingest(url=container_url(api, "/api"))
    assert result.returncode != 0
    assert missing in result.stderr
    assert api.total_requests() == 0
    assert dir_state(project.data) == before


def test_user_and_group_come_from_env(project):
    """Escenario «Servicio lanzado con Compose»: el usuario y grupo son los de
    `.env`, aunque no coincidan con los del proceso que lanza Compose."""
    project.write_env(uid=1001, gid=1002)
    result = project.run_entrypoint("id")
    assert result.returncode == 0, result.stderr
    assert "uid=1001 " in result.stdout
    assert "gid=1002" in result.stdout
