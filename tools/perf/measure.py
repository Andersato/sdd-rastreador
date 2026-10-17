"""Mide cada ruta de la API (design.md, D13).

Uso: python tools/perf/measure.py http://127.0.0.1:8765 [--times 20]

Lanza `--times` veces cada ruta con parámetros representativos (Madrid,
gasoleo-a, radio 50 km) y muestra el tiempo más lento de cada una, medido
desde este programa. Contra una API local, la red es despreciable; a través
del túnel, el tiempo sin red está en el log de la API.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

LIMIT_S = 1.0
NEARBY = "/api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=gasoleo-a&radius_km=50&limit=100"


def fetch(url: str) -> tuple[int, dict, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            status, body = response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        status, body = exc.code, json.loads(exc.read())
    return status, body, time.perf_counter() - started


def routes(base: str) -> dict[str, str]:
    status, body, _ = fetch(base + NEARBY)
    if status != 200 or not body["data"]["stations"]:
        raise SystemExit(f"la búsqueda de cercanas no da resultados ({status}): {body}")
    station = body["data"]["stations"][0]["id"]
    return {
        "/api/health": "/api/health",
        "/api/fuels": "/api/fuels",
        "/api/stations/nearby": NEARBY,
        "/api/stations/{station_id}": f"/api/stations/{station}",
        "/api/provinces/prices": "/api/provinces/prices?fuel=gasoleo-a",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base")
    parser.add_argument("--times", type=int, default=20)
    args = parser.parse_args(argv)
    base = args.base.rstrip("/")
    slow = False
    for name, path in routes(base).items():
        timings = []
        for _ in range(args.times):
            status, _, elapsed = fetch(base + path)
            if status != 200:
                raise SystemExit(f"{name}: respuesta {status}")
            timings.append(elapsed)
        worst = max(timings)
        slow |= worst >= LIMIT_S
        print(f"{name:30} máx {worst * 1000:7.1f} ms   media {sum(timings) / len(timings) * 1000:7.1f} ms")
    print("Todas por debajo de 1 s." if not slow else "ATENCIÓN: alguna ruta tarda 1 s o más.")
    return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())
