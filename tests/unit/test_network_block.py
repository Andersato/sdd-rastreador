import socket
import threading

import pytest


def test_external_connection_is_blocked():
    with pytest.raises(OSError):
        socket.create_connection(("example.com", 80), timeout=1)


def test_external_ip_connection_is_blocked():
    sock = socket.socket()
    try:
        with pytest.raises(OSError, match="bloqueada"):
            sock.connect(("93.184.216.34", 80))
    finally:
        sock.close()


def test_local_connection_is_allowed():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = threading.Thread(target=lambda: server.accept()[0].close())
    accepted.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    finally:
        accepted.join(timeout=2)
        server.close()


def test_proxies_are_cleared():
    import os

    assert "http_proxy" not in os.environ
    assert "HTTPS_PROXY" not in os.environ
    assert os.environ["no_proxy"] == "127.0.0.1,localhost"
