"""Utilidades para los tests funcionales de escenarios.

Ejecutan la ingesta completa en proceso (`main`: descarga contra el servidor
local, parser, guardado en SQLite y resumen), sin sustituir ninguna pieza
interna. Solo se inyecta el reloj, que `main` acepta como parámetro.
"""

import json
from datetime import datetime, timezone

from src.ingestion.__main__ import main

FIXED = datetime(2026, 10, 10, 17, 5, 30, tzinfo=timezone.utc)
LAT, LON = "Latitud", "Longitud (WGS84)"


def run_ingestion(server, db, data, capsys, path="/api", now=FIXED):
    """Sirve `data` (dict o bytes) en el servidor local y lanza la ingesta.

    Devuelve (código de salida, stdout, stderr).
    """
    body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
    url = server.add(path, body=body)
    code = main(["--url", url, "--db", str(db)], now=lambda: now)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def warning_lines(out):
    """Líneas de aviso del resumen (una por aviso)."""
    return [line for line in out.splitlines() if line.startswith("Aviso: ")]


def assert_one_warning(out, *parts):
    """Hay exactamente un aviso y contiene todos los textos de `parts`."""
    lines = warning_lines(out)
    assert "Avisos: 1" in out, out
    assert len(lines) == 1, lines
    for part in parts:
        assert part in lines[0], (part, lines[0])


def assert_no_warnings(out):
    assert "Avisos: 0" in out, out
    assert warning_lines(out) == []
