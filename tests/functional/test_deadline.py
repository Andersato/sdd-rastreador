"""El plazo total corta el proceso completo, no solo la función de descarga."""

import time

from tests.helpers import run_cli
from tests.http_server import SLOW


def test_process_ends_within_deadline_with_slow_server(http_server, tmp_path):
    url = http_server.add_fixture("/api", "valid_two_stations.json", mode=SLOW, delay=0.2)
    start = time.monotonic()
    result = run_cli(url, tmp_path / "prices.db", deadline=1)
    elapsed = time.monotonic() - start
    assert result.returncode != 0
    assert "se agotó el tiempo de descarga (1 s)" in result.stderr
    # Holgado para máquinas cargadas (arranque del subproceso + 1 s de plazo),
    # pero muy por debajo de lo que tardaría el servidor lento (~0,2 s por byte).
    assert elapsed < 1 + 3, f"el proceso tardó {elapsed:.1f} s"
    assert not (tmp_path / "prices.db").exists()
