"""Requisito "Descarga única de precios en JSON" y respuestas inválidas (cliente)."""

import json
from datetime import datetime, timezone

import pytest

from src.ingestion.client import fetch_prices
from src.ingestion.errors import DownloadError, InvalidResponseError
from tests.helpers import closed_port_url
from tests.http_server import TRUNCATED_CLOSE, TRUNCATED_LENGTH

VALID = json.dumps({"ResultadoConsulta": "OK", "ListaEESSPrecio": [{"IDEESS": "1"}]}).encode()
FIXED = datetime(2026, 10, 10, 17, 5, 30, tzinfo=timezone.utc)


def fetch(url):
    return fetch_prices(url, deadline_s=5, now=lambda: FIXED)


def test_normal_run_single_request_with_accept_header(http_server):
    url = http_server.add("/api", body=VALID)
    data, instant = fetch(url)
    assert data["ResultadoConsulta"] == "OK"
    assert instant == FIXED
    assert http_server.total_requests() == 1
    assert http_server.received_headers["/api"]["Accept"] == "application/json"


def test_redirect_is_followed_once(http_server):
    http_server.add("/new", body=VALID)
    url = http_server.add("/old", status=301, headers={"Location": http_server.url("/new")})
    data, _ = fetch(url)
    assert data["ResultadoConsulta"] == "OK"
    assert http_server.requests == {"/old": 1, "/new": 1}
    assert http_server.received_headers["/new"]["Accept"] == "application/json"


def test_503_without_retry(http_server):
    url = http_server.add("/api", status=503, body=b"busy")
    with pytest.raises(DownloadError, match="HTTP 503"):
        fetch(url)
    assert http_server.total_requests() == 1


def test_http_500(http_server):
    url = http_server.add("/api", status=500, body=b"error")
    with pytest.raises(DownloadError, match="HTTP 500"):
        fetch(url)
    assert http_server.total_requests() == 1


@pytest.mark.parametrize("status", [204, 206])
def test_final_status_other_than_200(http_server, status):
    url = http_server.add("/api", status=status, body=b"" if status == 204 else VALID)
    with pytest.raises(DownloadError, match=f"HTTP {status}"):
        fetch(url)


def test_empty_body(http_server):
    url = http_server.add_fixture("/api", "empty.json")
    with pytest.raises(InvalidResponseError, match="vacía"):
        fetch(url)


@pytest.mark.parametrize("fixture", ["not_json.xml", "not_json.html"])
def test_not_json(http_server, fixture):
    url = http_server.add_fixture("/api", fixture)
    with pytest.raises(InvalidResponseError, match="no es JSON"):
        fetch(url)


def test_truncated_with_content_length(http_server):
    url = http_server.add("/api", body=VALID[:-10], mode=TRUNCATED_LENGTH)
    with pytest.raises(DownloadError, match="incompleta"):
        fetch(url)


def test_truncated_by_closing_connection(http_server):
    url = http_server.add_fixture("/api", "valid_two_stations.json", mode=TRUNCATED_CLOSE)
    with pytest.raises(InvalidResponseError, match="no es JSON"):
        fetch(url)


def test_root_not_object_reaches_parser(http_server):
    url = http_server.add_fixture("/api", "root_list.json")
    data, _ = fetch(url)
    assert data == []


def test_connection_refused():
    with pytest.raises(DownloadError, match="no se ha podido conectar"):
        fetch(closed_port_url())


def test_utf8_bom_accepted(http_server):
    url = http_server.add("/api", body=b"\xef\xbb\xbf" + VALID)
    data, _ = fetch(url)
    assert data["ResultadoConsulta"] == "OK"


@pytest.mark.parametrize(
    "body",
    [b"1" * 5000, b"[" * 100_000 + b"]" * 100_000],
    ids=["entero-demasiado-largo", "anidamiento-excesivo"],
)
def test_pathological_json_is_invalid_response(http_server, body):
    url = http_server.add("/api", body=body)
    with pytest.raises(InvalidResponseError, match="no es JSON"):
        fetch(url)


@pytest.mark.parametrize(
    "url",
    ["sin-esquema", "http://127.0.0.1:abc/api", "http://127.0.0.1/con espacios"],
    ids=["sin-esquema", "puerto-no-numerico", "con-espacios"],
)
def test_malformed_url_is_download_error(url):
    with pytest.raises(DownloadError, match="URL no válida"):
        fetch(url)


def test_http_error_response_is_closed(http_server, monkeypatch):
    from urllib.error import HTTPError

    closed = []
    real_close = HTTPError.close

    def spy_close(self):
        closed.append(self.code)
        real_close(self)

    monkeypatch.setattr(HTTPError, "close", spy_close)
    url = http_server.add("/api", status=503, body=b"busy")
    with pytest.raises(DownloadError, match="HTTP 503"):
        fetch(url)
    assert closed == [503]
