"""Configuración común de los tests.

Ningún test puede salir a la red: solo se permiten conexiones a la propia
máquina (el servidor HTTP local de `tests/http_server.py`). El navegador de
los tests de la web es otro proceso: lo vigila su propia guarda de red
(`tests/web_fixtures.py`).
"""

import socket

import pytest

from tests.helpers import PROXY_VARS

# Fixtures de los tests de la web en Chromium (servidor, guarda de red…).
pytest_plugins = ["tests.web_fixtures"]

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in ALLOWED_HOSTS:
            raise socket.gaierror(f"red externa bloqueada en los tests: {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ALLOWED_HOSTS:
            raise OSError(f"red externa bloqueada en los tests: {host}")
        return real_connect(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    for var in PROXY_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


@pytest.fixture
def http_server():
    from tests.http_server import LocalServer

    server = LocalServer().start()
    yield server
    server.stop()
