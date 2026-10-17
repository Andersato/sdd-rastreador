"""Escenarios de la descarga al Mac (`database-backup`: «Descarga de las copias al
Mac», «Verificación de las copias descargadas», «Rotación en el Mac» y la
parte del script de «Acceso restringido para las copias»).

El VPS se sustituye por una carpeta local (`--source`): nunca hay red ni SSH.
Hace falta el rsync de Homebrew, como en el uso real; sin él se saltan.
"""

import gzip
import os
import shutil
import stat
from datetime import date, datetime, timedelta, timezone

import pytest

from src.backup import pull
from src.backup.rotation import backup_name
from tests.builders import response, station
from tests.storage_helpers import ingest, query

NOW = datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc)  # 10:00 de Madrid
TODAY = date(2026, 10, 17)

try:
    RSYNC = pull.find_rsync()
except pull.PullError:
    RSYNC = None

needs_rsync = pytest.mark.skipif(RSYNC is None, reason="falta el rsync de Homebrew")


def make_db(path, captures):
    body = response(station("S0", **{"Precio Gasoleo A": "1,459"}))
    for n in range(captures):
        ingest(path, body, instant=NOW - timedelta(hours=6 * (captures - n)))
    return path


def gz_copy(folder, day, captures, tmp_path):
    db = make_db(tmp_path / f"base-{day}-{captures}.db", captures)
    target = folder / backup_name(day)
    with open(db, "rb") as src, gzip.open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return target


@pytest.fixture
def vps(tmp_path):
    folder = tmp_path / "vps-backups"
    folder.mkdir()
    return folder


@pytest.fixture
def mac(tmp_path):
    return tmp_path / "Backups" / "precios-gasolineras"


def run(source, dest, *extra, rsync=None, candidates=None):
    lines = []
    args = ["--source", str(source), "--dest", str(dest), *extra]
    if rsync:
        args += ["--rsync", rsync]
    code = pull.main(args, now=NOW, out=lines.append,
                     candidates=candidates or pull.RSYNC_CANDIDATES)
    return code, "\n".join(lines)


def state(folder):
    if not folder.exists():
        return None
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file()}


def snapshots_in(gz, tmp_path):
    out = tmp_path / f"check-{gz.name}.db"
    with gzip.open(gz) as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return query(out, "SELECT COUNT(*) FROM snapshots")[0][0]


# --- Descarga de las copias al Mac --------------------------------------------

@needs_rsync
def test_first_download(vps, mac, tmp_path):
    """Escenario: Primera descarga."""
    for n, day in enumerate([date(2026, 10, 15), date(2026, 10, 16), TODAY], start=1):
        gz_copy(vps, day, n, tmp_path)
    code, out = run(vps, mac)
    assert code == 0, out
    assert sorted(os.listdir(mac)) == [backup_name(d) for d in
                                       (date(2026, 10, 15), date(2026, 10, 16), TODAY)]
    assert "copias nuevas: 3" in out
    assert "la más reciente del VPS: prices-2026-10-17.db.gz (3 capturas, verificada ahora)" in out


@needs_rsync
def test_nothing_new(vps, mac, tmp_path):
    """Escenarios: Sin novedades y Dos ejecuciones el mismo día."""
    gz_copy(vps, TODAY, 2, tmp_path)
    assert run(vps, mac)[0] == 0
    before = state(mac)
    code, out = run(vps, mac)
    assert code == 0 and "copias nuevas: 0" in out
    assert "ya estaba en el Mac" in out
    assert state(mac) == before


@needs_rsync
def test_copies_removed_in_the_vps_stay_in_the_mac(vps, mac, tmp_path):
    """Escenario: Copias borradas en el VPS."""
    gz_copy(vps, date(2026, 10, 9), 1, tmp_path)
    gz_copy(vps, TODAY, 2, tmp_path)
    run(vps, mac)
    (vps / backup_name(date(2026, 10, 9))).unlink()
    assert run(vps, mac)[0] == 0
    assert (mac / backup_name(date(2026, 10, 9))).exists()


def test_vps_unreachable_leaves_the_mac_untouched(tmp_path, mac):
    """Escenario: VPS inaccesible (aquí, un origen que no existe)."""
    if RSYNC is None:
        pytest.skip("falta el rsync de Homebrew")
    code, out = run(tmp_path / "no-existe", mac)
    assert code == 1
    assert "no se han podido listar las copias del VPS" in out
    assert not mac.exists()


@needs_rsync
def test_vps_unreachable_leaves_an_existing_mac_folder_untouched(vps, mac, tmp_path):
    """Escenario: VPS inaccesible, con copias ya descargadas y restos de un corte
    en `descargando/`: la carpeta del Mac queda exactamente igual."""
    gz_copy(vps, date(2026, 10, 16), 1, tmp_path)
    assert run(vps, mac)[0] == 0
    (mac / "descargando").mkdir()
    (mac / "descargando" / "prices-2026-10-17.db.gz").write_bytes(b"medio")
    before = state(mac)
    code, out = run(tmp_path / "no-existe", mac)
    assert code == 1 and "no se han podido listar las copias del VPS" in out
    assert state(mac) == before


@needs_rsync
def test_downloads_go_to_the_downloading_subfolder(vps, mac, tmp_path):
    """Escenario: Dónde se descarga: rsync escribe en `descargando/`; solo ya
    verificada pasa a la carpeta principal, y `descargando/` no queda al final."""
    gz_copy(vps, TODAY, 2, tmp_path)
    calls = tmp_path / "destinos.txt"
    wrapper = tmp_path / "rsync-anota"
    wrapper.write_text(f"""#!/bin/sh
case "$*" in
  *--version*|*--list-only*|*--dry-run*) exec {RSYNC} "$@";;
esac
for last; do :; done
echo "$last" >> {calls}
ls -A "$(dirname "$last")" > {tmp_path}/principal-durante.txt
exec {RSYNC} "$@"
""")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    code, out = run(vps, mac, rsync=str(wrapper))
    assert code == 0, out
    assert calls.read_text().splitlines() == [f"{mac / 'descargando'}/"]
    # Mientras se descargaba, la copia aún no estaba en la carpeta principal.
    assert "prices-2026-10-17.db.gz" not in (tmp_path / "principal-durante.txt").read_text()
    assert sorted(os.listdir(mac)) == ["prices-2026-10-17.db.gz"]


@needs_rsync
def test_connection_cut_halfway(vps, mac, tmp_path):
    """Escenario: Conexión cortada a mitad (rsync que falla al descargar y deja su
    temporal); la siguiente ejecución limpia `descargando/`."""
    gz_copy(vps, date(2026, 10, 16), 1, tmp_path)
    run(vps, mac)
    gz_copy(vps, TODAY, 2, tmp_path)
    before = state(mac)
    wrapper = tmp_path / "rsync-cortado"
    wrapper.write_text(f"""#!/bin/sh
case "$*" in
  *--version*|*--list-only*|*--dry-run*) exec {RSYNC} "$@";;
esac
for last; do :; done
echo medio > "$last/.prices-2026-10-17.db.gz.Ab12Cd"
echo "rsync: connection unexpectedly closed" >&2
exit 12
""")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    code, out = run(vps, mac, rsync=str(wrapper))
    assert code == 1 and "connection unexpectedly closed" in out
    assert not (mac / "prices-2026-10-17.db.gz").exists()
    assert {k: v for k, v in state(mac).items() if not k.startswith("descargando")} == before
    code, _ = run(vps, mac)
    assert code == 0
    assert (mac / "prices-2026-10-17.db.gz").exists()
    assert not (mac / "descargando").exists()


@needs_rsync
def test_no_copies_in_the_vps(vps, mac, tmp_path):
    """Escenario: Ninguna copia en el VPS."""
    gz_copy(vps, date(2026, 10, 16), 1, tmp_path)
    run(vps, mac)
    for p in vps.iterdir():
        p.unlink()
    before = state(mac)
    code, out = run(vps, mac)
    assert code == 1 and "no hay copias en el VPS" in out
    assert state(mac) == before


@needs_rsync
def test_only_copies_are_downloaded(vps, mac, tmp_path):
    """Escenarios: Solo se descargan copias y Descarga durante una copia en el VPS
    (el temporal de una copia en curso no se descarga)."""
    gz_copy(vps, TODAY, 1, tmp_path)
    (vps / "antes-de-migrar.db").write_bytes(b"x")
    (vps / "notas.txt").write_text("x")
    (vps / ".prices-2026-10-17.4242.gz.tmp").write_bytes(b"a medias")
    assert run(vps, mac)[0] == 0
    assert sorted(os.listdir(mac)) == ["prices-2026-10-17.db.gz"]


# --- Verificación de las copias descargadas ------------------------------------

@needs_rsync
def test_damaged_copy_goes_to_rejected(vps, mac, tmp_path):
    """Escenario: Copia dañada (truncada); el resto se descargan."""
    gz_copy(vps, date(2026, 10, 16), 1, tmp_path)
    bad = gz_copy(vps, TODAY, 2, tmp_path)
    bad.write_bytes(bad.read_bytes()[:200])
    code, out = run(vps, mac)
    assert code == 1
    assert (mac / "prices-2026-10-16.db.gz").exists()
    assert (mac / "rechazadas" / "prices-2026-10-17.db.gz").exists()
    assert not (mac / "prices-2026-10-17.db.gz").exists()
    assert "rechazada (en rechazadas/): prices-2026-10-17.db.gz" in out


@needs_rsync
def test_text_instead_of_gzip(vps, mac):
    """Escenario: Archivo que no es gzip."""
    (vps / "prices-2026-10-17.db.gz").write_text("hola")
    code, _ = run(vps, mac)
    assert code == 1
    assert (mac / "rechazadas" / "prices-2026-10-17.db.gz").read_text() == "hola"


@needs_rsync
def test_same_day_copy_changes_and_arrives_bad(vps, mac, tmp_path):
    """Escenario: Copia del mismo día que cambia y llega mal."""
    gz_copy(vps, TODAY, 28, tmp_path)
    run(vps, mac)
    good = (mac / "prices-2026-10-17.db.gz").read_bytes()
    target = vps / "prices-2026-10-17.db.gz"
    target.write_bytes(gz_copy(tmp_path, TODAY, 29, tmp_path).read_bytes()[:300])
    code, _ = run(vps, mac)
    assert code == 1
    assert (mac / "prices-2026-10-17.db.gz").read_bytes() == good
    assert (mac / "rechazadas" / "prices-2026-10-17.db.gz").exists()


@needs_rsync
def test_same_day_copy_changes_and_arrives_good(vps, mac, tmp_path):
    """Escenario: Copia del mismo día que cambia y llega bien."""
    gz_copy(vps, TODAY, 28, tmp_path)
    run(vps, mac)
    (tmp_path / "otra").mkdir()
    newer = gz_copy(tmp_path / "otra", TODAY, 29, tmp_path)
    shutil.copy(newer, vps / newer.name)
    assert run(vps, mac)[0] == 0
    assert sorted(os.listdir(mac)) == ["prices-2026-10-17.db.gz"]
    assert snapshots_in(mac / "prices-2026-10-17.db.gz", tmp_path) == 29


@needs_rsync
def test_rejected_copy_still_in_the_vps_is_retried(vps, mac, tmp_path):
    """Escenario: Copia rechazada que sigue en el VPS."""
    (vps / "prices-2026-10-17.db.gz").write_text("hola")
    run(vps, mac)
    (vps / "prices-2026-10-17.db.gz").write_text("adiós")
    code, _ = run(vps, mac)
    assert code == 1
    assert (mac / "rechazadas" / "prices-2026-10-17.db.gz").read_text() == "adiós"
    gz_copy(vps, TODAY, 3, tmp_path)
    assert run(vps, mac)[0] == 0
    assert (mac / "prices-2026-10-17.db.gz").exists()


# --- Rotación en el Mac ---------------------------------------------------------

@needs_rsync
def test_local_rotation(vps, mac, tmp_path):
    """Escenario: Rotación local (las mismas 11 copias que en el VPS)."""
    mac.mkdir(parents=True)
    day = date(2026, 9, 1)
    seed_gz = gz_copy(tmp_path, TODAY, 1, tmp_path)
    while day <= date(2026, 10, 16):
        shutil.copy(seed_gz, mac / backup_name(day))
        day += timedelta(days=1)
    gz_copy(vps, TODAY, 1, tmp_path)
    assert run(vps, mac)[0] == 0
    kept = sorted(n for n in os.listdir(mac) if n.endswith(".db.gz"))
    assert len(kept) == 11
    assert kept[:4] == [backup_name(date(2026, 9, d)) for d in (13, 20, 27)] + [
        backup_name(date(2026, 10, 4))]
    assert kept[4:] == [backup_name(date(2026, 10, d)) for d in range(11, 18)]


@needs_rsync
def test_rejected_new_copy_blocks_rotation(vps, mac, tmp_path):
    """Escenario: Copia nueva rechazada (no se borra nada del Mac)."""
    mac.mkdir(parents=True)
    seed_gz = gz_copy(tmp_path, TODAY, 1, tmp_path)
    for n in range(1, 20):
        shutil.copy(seed_gz, mac / backup_name(TODAY - timedelta(days=n)))
    (vps / "prices-2026-10-17.db.gz").write_text("hola")
    before = {k for k in state(mac) if not k.startswith("rechazadas")}
    assert run(vps, mac)[0] == 1
    assert {k for k in state(mac) if not k.startswith("rechazadas")} == before


# --- rsync de Homebrew y clave dedicada ----------------------------------------

def test_without_homebrew_rsync(tmp_path, mac):
    """Escenario: Sin el rsync de Homebrew: nunca usa /usr/bin/rsync."""
    code, out = run(tmp_path, mac, candidates=(str(tmp_path / "no-hay-rsync"),))
    assert code == 1
    assert "falta el rsync de Homebrew" in out and "brew install rsync" in out
    assert not mac.exists()


def test_system_rsync_is_refused(tmp_path, mac):
    if not os.path.exists("/usr/bin/rsync"):
        pytest.skip("no hay /usr/bin/rsync")
    code, out = run(tmp_path, mac, rsync="/usr/bin/rsync")
    assert code == 1 and "falta el rsync de Homebrew" in out


def test_missing_dedicated_key(tmp_path, mac, monkeypatch):
    """Escenario: Clave dedicada ausente: no prueba otra ni toca el Mac."""
    if RSYNC is None:
        pytest.skip("falta el rsync de Homebrew")
    calls = []
    monkeypatch.setattr(pull.subprocess, "run", lambda *a, **k: calls.append(a) or
                        pull.subprocess.CompletedProcess(a, 0, "rsync  version 3.5.1", ""))
    lines = []
    code = pull.main(["--host", "deploy@192.0.2.1", "--dest", str(mac),
                      "--key", str(tmp_path / "no-existe")], now=NOW, out=lines.append)
    assert code == 1
    assert "no existe la clave dedicada" in lines[0] and "ssh-keygen" in lines[0]
    assert all("--version" in call[0] for call in calls)  # solo la comprobación de versión
    assert not mac.exists()


def test_default_key_is_the_dedicated_one_and_default_folder():
    """Escenario: Sin la clave personal (configuración del script): por defecto,
    la clave dedicada `~/.ssh/precios-backups` y la carpeta
    `~/Backups/precios-gasolineras/`."""
    args = pull._parse_args(["--host", "deploy@<IP_DEL_VPS>"])
    assert args.key == "~/.ssh/precios-backups"
    assert args.dest.rstrip("/") == "~/Backups/precios-gasolineras"
    assert "id_ed25519" not in args.key and "id_rsa" not in args.key


def test_ssh_options_use_only_the_dedicated_key(tmp_path):
    key = tmp_path / "precios-backups"
    remote = pull.Remote("/opt/homebrew/bin/rsync", "deploy@<IP_DEL_VPS>", key, None)
    assert remote.ssh == ["-e", f"ssh -i {key} -o IdentitiesOnly=yes -o BatchMode=yes"]
    assert remote.base == "deploy@<IP_DEL_VPS>:./"
