"""Comprueba cada modo del servidor local con `http.client` (sin la ingesta)."""

import http.client
import socket
import time

import pytest

from tests.http_server import HANG, SLOW, TRUNCATED_CLOSE, TRUNCATED_LENGTH


def get(server, path, timeout=5):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=timeout)
    conn.request("GET", path, headers={"Accept": "application/json"})
    return conn, conn.getresponse()


def test_normal_body_and_request_count(http_server):
    http_server.add("/ok", body=b'{"a": 1}')
    conn, resp = get(http_server, "/ok")
    assert resp.status == 200
    assert resp.read() == b'{"a": 1}'
    conn.close()
    assert http_server.count("/ok") == 1
    assert http_server.received_headers["/ok"]["Accept"] == "application/json"


def test_redirect_301(http_server):
    http_server.add("/old", status=301, headers={"Location": http_server.url("/new")})
    conn, resp = get(http_server, "/old")
    assert resp.status == 301
    assert resp.getheader("Location").endswith("/new")
    conn.close()


@pytest.mark.parametrize("status", [204, 206, 500, 503])
def test_status_codes(http_server, status):
    http_server.add("/s", status=status, body=b"" if status == 204 else b"x")
    conn, resp = get(http_server, "/s")
    assert resp.status == status
    resp.read()
    conn.close()


def test_empty_body(http_server):
    http_server.add("/empty", body=b"")
    conn, resp = get(http_server, "/empty")
    assert resp.status == 200
    assert resp.read() == b""
    conn.close()


def test_truncated_with_content_length(http_server):
    http_server.add("/t", body=b'{"ListaEESSPrecio": [', mode=TRUNCATED_LENGTH)
    conn, resp = get(http_server, "/t")
    with pytest.raises(http.client.IncompleteRead):
        resp.read()
    conn.close()


def test_truncated_by_closing_connection(http_server):
    body = b'{"ListaEESSPrecio": [{"IDEESS": "1"}]}'
    http_server.add("/t", body=body, mode=TRUNCATED_CLOSE)
    conn, resp = get(http_server, "/t")
    assert resp.read() == body[: len(body) // 2]
    conn.close()


def test_hang_never_answers(http_server):
    http_server.add("/hang", mode=HANG)
    with pytest.raises(socket.timeout):
        get(http_server, "/hang", timeout=0.5)


def test_slow_sends_byte_by_byte(http_server):
    http_server.add("/slow", body=b"abcdef", mode=SLOW, delay=0.2)
    # Desde antes de la petición: el tercer byte llega tras dos pausas (≥ 0,4 s).
    start = time.monotonic()
    conn, resp = get(http_server, "/slow")
    assert resp.read(3) == b"abc"
    assert time.monotonic() - start >= 0.4
    conn.close()


def test_sent_event_after_full_body(http_server):
    body = b"x" * 200_000
    http_server.add("/big", body=body)
    sent = http_server.sent("/big")
    assert not sent.is_set()
    conn, resp = get(http_server, "/big")
    assert resp.read() == body
    conn.close()
    assert sent.wait(timeout=5)
    assert not http_server.sent("/other").is_set()
