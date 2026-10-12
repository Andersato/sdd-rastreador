"""Escenarios TLS con la CLI real como subproceso y un servidor HTTPS local.

Requisitos: "Cifrados ofrecidos al conectar con la API" y "Verificación del
certificado de la API". La CLI confía en la autoridad de prueba
(`fixtures/tls/ca.pem`) solo porque se le pasa en el entorno del subproceso.
"""

import ssl
import urllib.request
from urllib.error import URLError

import pytest

from tests.builders import response, station
from tests.helpers import db_dump, run_cli
from tests.http_server import TLS_FIXTURES, LocalServer
from tests.storage_helpers import ingest, query

TRUST_TEST_CA = {"SSL_CERT_FILE": str(TLS_FIXTURES / "ca.pem")}


@pytest.fixture
def https_server():
    servers = []

    def start(cipher, cert="localhost"):
        tls = (TLS_FIXTURES / f"{cert}.pem", TLS_FIXTURES / f"{cert}.key", cipher)
        server = LocalServer(tls=tls).start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.stop()


def existing_db(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"})))
    return db


@pytest.mark.parametrize("cipher", ["AES256-GCM-SHA384", "AES128-GCM-SHA256"])
def test_scenario_server_only_accepts_rsa_cipher(https_server, tmp_path, cipher):
    """Escenarios: Servidor que solo acepta AES256-GCM-SHA384 / AES128-GCM-SHA256."""
    db = tmp_path / "prices.db"
    server = https_server(cipher)
    url = server.add_fixture("/api", "valid_two_stations.json")
    assert url.startswith("https://127.0.0.1:")
    result = run_cli(url, db, env=TRUST_TEST_CA)
    assert result.returncode == 0, result.stderr
    assert server.total_requests() == 1
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert query(db, "SELECT COUNT(*) FROM stations") == [(2,)]


def test_scenario_https_to_https_redirect(https_server, tmp_path):
    """Escenario: Redirección HTTPS a HTTPS."""
    db = tmp_path / "prices.db"
    server_b = https_server("AES128-GCM-SHA256")
    target = server_b.add_fixture("/api", "valid_two_stations.json")
    server_a = https_server("AES256-GCM-SHA384")
    url = server_a.add("/api", status=301, headers={"Location": target})
    result = run_cli(url, db, env=TRUST_TEST_CA)
    assert result.returncode == 0, result.stderr
    assert server_a.requests == {"/api": 1}
    assert server_b.requests == {"/api": 1}
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert query(db, "SELECT COUNT(*) FROM stations") == [(2,)]


@pytest.mark.parametrize(
    "cert", ["selfsigned", "other"], ids=["certificado-no-reconocido", "nombre-no-coincide"]
)
def test_scenario_certificate_rejected(https_server, tmp_path, cert):
    """Escenarios: Certificado no reconocido / Nombre del servidor que no coincide."""
    db = existing_db(tmp_path)
    before = db_dump(db)
    server = https_server("AES256-GCM-SHA384", cert=cert)
    url = server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db, env=TRUST_TEST_CA)
    assert result.returncode != 0
    assert "no se ha podido conectar con la API:" in result.stderr
    assert "CERTIFICATE_VERIFY_FAILED" in result.stderr
    assert server.total_requests() == 0
    assert db_dump(db) == before


def test_scenario_plain_http_url(http_server, tmp_path):
    """Escenario: URL sin TLS."""
    db = tmp_path / "prices.db"
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    assert url.startswith("http://127.0.0.1:")
    result = run_cli(url, db)
    assert result.returncode == 0, result.stderr
    assert http_server.total_requests() == 1
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert query(db, "SELECT COUNT(*) FROM stations") == [(2,)]


@pytest.mark.parametrize("cipher", ["AES256-GCM-SHA384", "AES128-GCM-SHA256"])
def test_control_default_python_context_is_rejected(https_server, cipher):
    """Control de los escenarios «Servidor que solo acepta …»: con el contexto
    por defecto de Python (misma autoridad de prueba) el servidor rechaza el
    saludo TLS. Así esos escenarios solo pasan gracias a `tls_context()`."""

    server = https_server(cipher)
    url = server.add_fixture("/api", "valid_two_stations.json")
    ctx = ssl.create_default_context(cafile=str(TLS_FIXTURES / "ca.pem"))
    with pytest.raises(URLError) as exc_info:
        urllib.request.urlopen(url, timeout=5, context=ctx)
    assert isinstance(exc_info.value.reason, ssl.SSLError)
    assert server.total_requests() == 0
