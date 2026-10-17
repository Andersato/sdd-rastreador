"""Configuración de Compose del servicio `api` (prices-api): «Puerto solo en
127.0.0.1 del host», «Carpeta ./data montada en solo lectura» y la rotación
de «Log de la API limitado y sin ubicaciones exactas».

Solo `docker compose config`, sobre una copia del `docker-compose.yml` real
sin cambiar el puerto (`real_api_port=True`): aquí no se arranca nada.
"""

import json

import pytest

from tests.docker.helpers import API, make_project


@pytest.fixture
def config(tmp_path):
    project = make_project(tmp_path, uid=1000, gid=1000, real_api_port=True)
    (project.root / ".env").write_text(
        "HOST_UID=1000\nHOST_GID=1000\nCOLLECTION_ENABLED=true\n")
    result = project.compose("config", "--format", "json", timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout), project


def test_only_published_port_is_the_api_on_localhost(config):
    """Escenario: Configuración de Compose."""
    data, _ = config
    published = [(name, port) for name, service in data["services"].items()
                 for port in service.get("ports", [])]
    assert len(published) == 1
    name, port = published[0]
    assert name == API
    assert (port["host_ip"], str(port["published"]), port["target"]) == ("127.0.0.1", "8000", 8000)


def test_api_mounts_only_data_read_only(config):
    """Escenario: Montajes de la API."""
    data, project = config
    volumes = data["services"][API]["volumes"]
    assert len(volumes) == 1
    volume = volumes[0]
    assert volume["type"] == "bind"
    assert volume["source"] == str(project.data)
    assert volume["target"] == "/app/data"
    assert volume["read_only"] is True
    assert volume["bind"]["create_host_path"] is False


def test_api_log_rotation(config):
    """Escenario: Rotación."""
    data, _ = config
    logging = data["services"][API]["logging"]
    assert logging["driver"] == "json-file"
    assert logging["options"] == {"max-size": "10m", "max-file": "3"}


def test_vps_env_gives_user_1000_to_scheduler_and_api(config):
    """Escenarios: Arranque en el VPS (los dos servicios con usuario 1000 y grupo 1000
    del `.env` del VPS) y Configuración de Compose (servicios que arrancan)."""
    data, _ = config
    started = {name for name, service in data["services"].items() if "profiles" not in service}
    assert started == {"api", "scheduler"}
    assert {name: data["services"][name]["user"] for name in started} == {
        "api": "1000:1000", "scheduler": "1000:1000"}


def test_api_service_settings(config):
    data, _ = config
    api = data["services"][API]
    assert api["restart"] == "unless-stopped"
    assert api["user"] == "1000:1000"
    assert api["entrypoint"] == ["python", "/app/container/api.py"]
    assert api["environment"]["TZ"] == "Europe/Madrid"
    assert "CAPTURE_INTERVAL_HOURS" in api["environment"]
    assert "profiles" not in api
