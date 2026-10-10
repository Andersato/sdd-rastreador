"""Requisito "Tiempo límite de la descarga" (cliente, plazo reducido)."""

import time

import pytest

from src.ingestion.client import fetch_prices
from src.ingestion.errors import DownloadTimeout
from tests.http_server import HANG, SLOW

DEADLINE = 1.0


def assert_times_out(url, server):
    start = time.monotonic()
    with pytest.raises(DownloadTimeout, match=r"se agotó el tiempo de descarga \(1 s\)"):
        fetch_prices(url, deadline_s=DEADLINE)
    assert time.monotonic() - start < DEADLINE + 2
    assert server.total_requests() == 1


def test_server_that_never_answers(http_server):
    url = http_server.add("/api", mode=HANG)
    assert_times_out(url, http_server)


def test_server_that_sends_very_slowly(http_server):
    url = http_server.add("/api", body=b'{"ResultadoConsulta": "OK"}' * 5, mode=SLOW, delay=0.3)
    assert_times_out(url, http_server)
