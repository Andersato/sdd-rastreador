"""Descarga al Mac de las copias del VPS (D10): python -m src.backup.pull --host deploy@IP

Es el Mac quien se conecta (modelo pull): el VPS no puede borrar nada aquí.
Pasos: comprobar el rsync de Homebrew y la clave dedicada; listar las copias
del VPS (solo `prices-AAAA-MM-DD.db.gz`); si eso falla, terminar sin tocar
nada del Mac. Después, descargar a `descargando/` las nuevas o cambiadas,
verificarlas y pasarlas a la carpeta principal (o a `rechazadas/` si fallan),
y, si no ha fallado ninguna, aplicar la rotación en el Mac.

Usa siempre el rsync de Homebrew, nunca el `/usr/bin/rsync` del sistema
(`openrsync`), que el `rrsync` del VPS rechaza.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.ingestion.formatting import thousands

from .make import madrid_date
from .rotation import parse_name, rotate
from .verify import VerificationError, verify_gz

DEFAULT_DEST = "~/Backups/precios-gasolineras"
DEFAULT_KEY = "~/.ssh/precios-backups"
RSYNC_CANDIDATES = ("/opt/homebrew/bin/rsync", "/usr/local/bin/rsync")
PATTERN = "prices-????-??-??.db.gz"
FILTERS = [f"--include={PATTERN}", "--exclude=*"]
DOWNLOADING, REJECTED = "descargando", "rechazadas"
EXIT_OK, EXIT_FAILED = 0, 1
TIMEOUT_S = 3600


class PullError(Exception):
    """Error que termina la ejecución sin tocar la carpeta del Mac."""


def find_rsync(explicit: str | None = None, candidates=RSYNC_CANDIDATES) -> str:
    """Ruta del rsync de Homebrew (rsync de GNU 3.x); `PullError` si no está."""
    for path in ([explicit] if explicit else candidates):
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            try:
                version = subprocess.run([path, "--version"], capture_output=True, text=True,
                                         timeout=30).stdout
            except OSError:
                continue
            if re.match(r"rsync\s+version\s+3\.", version) and "openrsync" not in version:
                return path
    raise PullError(
        "falta el rsync de Homebrew (" + (explicit or " o ".join(candidates)) + "); "
        "el de macOS (/usr/bin/rsync) no sirve con el VPS. Instálalo con: brew install rsync"
    )


class Remote:
    """Origen de las copias: el VPS por SSH, o una carpeta local (`--source`, tests)."""

    def __init__(self, rsync: str, host: str | None, key: Path | None, source: Path | None):
        self.rsync = rsync
        if source is not None:
            self.base, self.ssh = f"{source}/", []
        else:
            ssh = f"ssh -i {key} -o IdentitiesOnly=yes -o BatchMode=yes"
            self.base, self.ssh = f"{host}:./", ["-e", ssh]

    def run(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run([self.rsync, *self.ssh, *args], capture_output=True, text=True,
                              timeout=TIMEOUT_S)

    def list_names(self) -> list[str]:
        result = self.run("--list-only", *FILTERS, self.base)
        if result.returncode != 0:
            raise PullError("no se han podido listar las copias del VPS: " + _last(result))
        names = [line.split()[-1] for line in result.stdout.splitlines() if line.startswith("-")]
        return sorted(name for name in names if parse_name(name) is not None)

    def changed(self, dest: Path) -> list[str]:
        """Copias que faltan o difieren (tamaño o fecha) en `dest`, según rsync."""
        # -r para entrar en la carpeta; el filtro deja solo las copias de primer nivel.
        result = self.run("-rt", "--dry-run", "--itemize-changes", *FILTERS, self.base,
                          f"{dest}/")
        if result.returncode != 0:
            raise PullError("no se ha podido comparar con el VPS: " + _last(result))
        names = [line.split(None, 1)[1] for line in result.stdout.splitlines()
                 if line.startswith(">f")]
        return sorted(name for name in names if parse_name(name) is not None)

    def download(self, name: str, folder: Path) -> subprocess.CompletedProcess:
        return self.run("-t", self.base + name, f"{folder}/")


def _last(result: subprocess.CompletedProcess) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    return lines[-1] if lines else f"código {result.returncode}"


def pull(remote: Remote, dest: Path, now: datetime, out) -> int:
    names = remote.list_names()  # si falla, no se ha tocado nada del Mac
    if not names:
        out("no hay copias en el VPS; no se borra nada en el Mac")
        return EXIT_FAILED
    dest.mkdir(parents=True, exist_ok=True)
    downloading = dest / DOWNLOADING
    shutil.rmtree(downloading, ignore_errors=True)  # restos de un corte
    downloading.mkdir()
    new, rejected, errors, counts = [], {}, [], {}
    for name in remote.changed(dest):
        result = remote.download(name, downloading)
        got = downloading / name
        if result.returncode != 0 or not got.exists():
            errors.append(f"{name}: no se ha podido descargar ({_last(result)})")
            continue
        try:
            info = verify_gz(got, downloading)
        except VerificationError as exc:
            (dest / REJECTED).mkdir(exist_ok=True)
            os.replace(got, dest / REJECTED / name)
            rejected[name] = str(exc)
            continue
        os.replace(got, dest / name)
        new.append(name)
        counts[name] = info.snapshots
    shutil.rmtree(downloading, ignore_errors=True)
    removed = []
    if not rejected and not errors:
        removed, _ = rotate(dest, madrid_date(now))
    _summary(out, names, new, rejected, errors, removed, counts)
    return EXIT_FAILED if rejected or errors else EXIT_OK


def _summary(out, names, new, rejected, errors, removed, counts) -> None:
    out(f"copias nuevas: {len(new)}" + (f" ({', '.join(new)})" if new else ""))
    latest = names[-1]
    if latest in counts:
        detail = f"{thousands(counts[latest])} capturas, verificada ahora"
    elif latest in rejected:
        detail = "rechazada"
    else:
        detail = "ya estaba en el Mac"
    out(f"la más reciente del VPS: {latest} ({detail})")
    if removed:
        out("borradas por la rotación del Mac: " + ", ".join(removed))
    for name, reason in rejected.items():
        out(f"rechazada (en {REJECTED}/): {name} ({reason})")
    for line in errors:
        out(f"error: {line}")
    if rejected or errors:
        out("no se ha aplicado la rotación del Mac porque alguna copia ha fallado")


def main(argv: list[str] | None = None, now: datetime | None = None, out=print,
         candidates=RSYNC_CANDIDATES) -> int:
    args = _parse_args(argv)
    now = now or datetime.now(timezone.utc)

    def say(text: str) -> None:
        out(f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')} · {text}")

    try:
        rsync = find_rsync(args.rsync, candidates)
        key = Path(os.path.expanduser(args.key))
        if args.source is None:
            if not args.host:
                raise PullError("falta --host (por ejemplo, --host deploy@<IP_DEL_VPS>)")
            if not key.is_file():
                raise PullError(
                    f"no existe la clave dedicada {key}; créala con: "
                    f'ssh-keygen -t ed25519 -N "" -f {args.key} (ver docs/offsite-backups.md)')
        remote = Remote(rsync, args.host, key, Path(args.source) if args.source else None)
        return pull(remote, Path(os.path.expanduser(args.dest)), now, say)
    except PullError as exc:
        say(f"error: {exc}")
        return EXIT_FAILED
    except subprocess.TimeoutExpired:
        say("error: el VPS no ha respondido a tiempo")
        return EXIT_FAILED


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="python -m src.backup.pull",
        description="Descarga al Mac las copias de seguridad del VPS y las verifica.")
    parser.add_argument("--host", help="usuario@máquina del VPS, p. ej. deploy@<IP_DEL_VPS>")
    parser.add_argument("--dest", default=DEFAULT_DEST, help=f"carpeta del Mac (por defecto, {DEFAULT_DEST})")
    parser.add_argument("--key", default=DEFAULT_KEY, help=f"clave SSH dedicada (por defecto, {DEFAULT_KEY})")
    parser.add_argument("--rsync", default=None, help="ruta del rsync de Homebrew, si no es la habitual")
    parser.add_argument("--source", default=None, help=argparse.SUPPRESS)  # solo tests: carpeta local
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
