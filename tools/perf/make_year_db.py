"""Base sintética de un año para medir la API (design.md, D13).

Uso: python tools/perf/make_year_db.py DESTINO.db COPIA.db [--captures 1460]

Copia `COPIA.db` (una copia de seguridad ya descomprimida, que se abre en solo
lectura) en `DESTINO.db` y repite su última captura, cada 6 horas, hasta
tener `--captures` capturas. Ocupa unos 4-5 GB con 1.460: bórrala al
terminar. Ni el destino ni la copia pueden estar en `./data` del proyecto, y
el destino no puede existir: nunca se toca el histórico real.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DATA = (REPO_ROOT / "data").resolve()
MADRID = ZoneInfo("Europe/Madrid")
STEP = timedelta(hours=6)
COMMIT_EVERY = 50


class Refused(Exception):
    pass


def check_paths(destination: Path, copy: Path) -> None:
    for path, what in ((destination, "el destino"), (copy, "la copia")):
        if Path(path).resolve().is_relative_to(REAL_DATA):
            raise Refused(f"{what} no puede estar en {REAL_DATA}: es el histórico real")
    if Path(destination).exists():
        raise Refused(f"el destino ya existe: {destination}")
    if not Path(copy).is_file():
        raise Refused(f"no existe la copia: {copy}")


def utc_text(instant: datetime) -> str:
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def make(destination: Path, copy: Path, captures: int, progress=print) -> int:
    """Crea la base; devuelve el número de capturas que tiene al terminar."""
    check_paths(destination, copy)
    source = sqlite3.connect(Path(copy).resolve().as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(destination, isolation_level=None)
    try:
        source.backup(target)
        last_id, last_at = target.execute(
            "SELECT id, downloaded_at FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
        count = target.execute("SELECT count(*) FROM snapshots").fetchone()[0]
        instant = datetime.fromisoformat(last_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        target.execute("BEGIN")
        while count < captures:
            instant += STEP
            local = instant.astimezone(MADRID).replace(tzinfo=None).isoformat(timespec="seconds")
            new_id = target.execute(
                "INSERT INTO snapshots (downloaded_at, source_date) VALUES (?, ?)",
                (utc_text(instant), local)).lastrowid
            target.execute("INSERT INTO prices (snapshot_id, station_id, fuel, price) "
                           "SELECT ?, station_id, fuel, price FROM prices WHERE snapshot_id = ?",
                           (new_id, last_id))
            count += 1
            if count % COMMIT_EVERY == 0:
                target.execute("COMMIT")
                progress(f"{count} capturas")
                target.execute("BEGIN")
        target.execute("COMMIT")
    finally:
        source.close()
        target.close()
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("destination", type=Path)
    parser.add_argument("copy", type=Path)
    parser.add_argument("--captures", type=int, default=1460)
    args = parser.parse_args(argv)
    try:
        total = make(args.destination, args.copy, args.captures)
    except Refused as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    size = args.destination.stat().st_size / 1e9
    print(f"Base creada: {args.destination} ({total} capturas, {size:.1f} GB). Bórrala al terminar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
