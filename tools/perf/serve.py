"""Lanza la API sobre una base cualquiera, para medir (design.md, D13).

Uso: python tools/perf/serve.py BASE.db [--port 8765]

Escucha solo en 127.0.0.1. Se para con Ctrl+C. Abre la base en solo lectura,
como en el contenedor.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main(argv=None) -> int:
    import uvicorn

    from src.api.app import create_app

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
