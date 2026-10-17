"""`container/scheduler.py` y `container/check.py`, sin Docker (D8, D12)."""

import importlib.util
import os
import signal
from datetime import datetime, timezone

import pytest

from tests.helpers import REPO_ROOT

CONTAINER = REPO_ROOT / "container"
NOW = datetime(2026, 10, 12, 12, 17, tzinfo=timezone.utc)


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(CONTAINER))  # check.py importa entrypoint
    spec = importlib.util.spec_from_file_location(f"container_{name}", CONTAINER / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scheduler(monkeypatch, tmp_path):
    module = load("scheduler", monkeypatch)
    monkeypatch.setattr(module, "CRONTAB_PATH", str(tmp_path / "crontab"))
    monkeypatch.setattr(module, "MARKER", str(tmp_path / "backup-pending"))
    return module


class Handlers:
    """Sustituye a `signal.signal`: el manejador real hace kill(-1) y nunca
    debe instalarse en el proceso de pytest."""

    def __init__(self):
        self.installed = {}

    def __call__(self, sig, handler):
        self.installed[sig] = handler


def run_main(scheduler, popen, wait, handlers=None):
    return scheduler.main({}, popen=popen, wait=wait, install=handlers or Handlers(),
                          platform="linux", now=NOW)


@pytest.fixture
def check(monkeypatch):
    return load("check", monkeypatch)


# --- scheduler.py -------------------------------------------------------------

def no_backup(*args):
    """Sustituye a la copia de después de la comprobación (rutas del contenedor)."""


def test_crontab_runs_check_every_hour_at_minute_17_and_backup_at_0443(scheduler):
    """Escenarios: Comprobaciones horarias y Copia de madrugada (crontab)."""
    assert scheduler.crontab() == ("17 * * * * python /app/container/check.py\n"
                                   "43 4 * * * python /app/container/backup.py --daily\n")


class FakeProc:
    def __init__(self, pid):
        self.pid = pid


def fake_wait(*results):
    """Sustituye a `os.wait`: devuelve `results` y después, sin hijos, ChildProcessError."""
    pending = iter(results)

    def wait():
        try:
            return next(pending)
        except StopIteration:
            raise ChildProcessError from None

    return wait


def test_starts_supercronic_and_startup_check_then_exits_with_supercronic(scheduler, capsys):
    launched = []
    wait = fake_wait((200, 0), (100, 3 << 8))  # termina la comprobación y luego supercronic

    def popen(args):
        launched.append(args)
        return FakeProc(100 if len(launched) == 1 else 200)

    code = run_main(scheduler, popen, wait)
    assert code == 3
    assert launched[0] == ["/usr/local/bin/supercronic", "-passthrough-logs", "-quiet",
                           scheduler.CRONTAB_PATH]
    assert launched[1][-2:] == ["/app/container/check.py", "--startup"]
    with open(scheduler.CRONTAB_PATH) as f:
        assert f.read() == scheduler.crontab()
    assert capsys.readouterr().out == (
        "2026-10-12 14:17:00 CEST · programador en marcha: comprobación ahora y cada hora en el "
        "minuto 17; intervalo configurado: 6 (por defecto); recogida desactivada "
        "(se activa con COLLECTION_ENABLED=true en .env)\n"
    )


class CountingWait:
    """Como `fake_wait`, pero cuenta las llamadas para saber si `main` siguió esperando."""

    def __init__(self, *results):
        self.calls = 0
        self._wait = fake_wait(*results)

    def __call__(self):
        self.calls += 1
        return self._wait()


def popen_two(launched):
    """supercronic es el PID 100 y la comprobación de arranque el 200."""
    def popen(args):
        launched.append(args)
        return FakeProc(100 if len(launched) == 1 else 200)
    return popen


def test_stop_waits_for_startup_check_after_supercronic_exits(scheduler):
    """D12 / Escenario: Parada durante una ingesta. supercronic sale antes que la
    comprobación de arranque: main sigue esperando hasta no tener hijos y
    devuelve el código de supercronic, no el de la comprobación."""
    wait = CountingWait((100, 3 << 8), (200, 130 << 8))
    code = run_main(scheduler, popen_two([]), wait)
    assert code == 3
    assert wait.calls == 3  # supercronic, comprobación y ChildProcessError


def test_supercronic_stopped_cleanly_returns_zero_after_reaping_all(scheduler):
    """D12: parada normal (supercronic sale con 0) con la comprobación aún viva."""
    wait = CountingWait((100, 0), (200, 0))
    assert run_main(scheduler, popen_two([]), wait) == 0
    assert wait.calls == 3


def test_no_children_before_seeing_supercronic_returns_1(scheduler):
    """D12: si os.wait se queda sin hijos sin haber visto salir a supercronic, devuelve 1."""
    wait = CountingWait()
    assert run_main(scheduler, popen_two([]), wait) == 1
    assert wait.calls == 1


def test_only_startup_check_reaped_returns_1(scheduler):
    """D12: solo termina la comprobación de arranque (código 0) y ya no hay hijos:
    sin código de supercronic, devuelve 1 y no el 0 de la comprobación."""
    wait = CountingWait((200, 0))
    assert run_main(scheduler, popen_two([]), wait) == 1
    assert wait.calls == 2


@pytest.mark.parametrize("sig, expected", [(signal.SIGKILL, 137), (signal.SIGTERM, 143)])
def test_supercronic_killed_by_signal_returns_128_plus_signal(scheduler, sig, expected):
    """supercronic muerto por una señal: 128 + número de la señal (D8)."""
    wait = CountingWait((100, sig), (200, 0))
    assert run_main(scheduler, popen_two([]), wait) == expected


def test_startup_line_shows_configured_interval(scheduler):
    assert "intervalo configurado: 'seis'" in scheduler.startup_line(
        {"CAPTURE_INTERVAL_HOURS": "seis"}, NOW)


def test_stop_signal_is_sent_to_every_process(scheduler):
    sent = []
    scheduler.stop_all(signal.SIGTERM, None, kill=lambda pid, sig: sent.append((pid, sig)))
    assert sent == [(-1, signal.SIGTERM)]


def test_handlers_installed_for_sigterm_and_sigint(scheduler):
    handlers = Handlers()
    before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    run_main(scheduler, lambda args: FakeProc(100), fake_wait((100, 0)), handlers)
    assert handlers.installed == {signal.SIGTERM: scheduler.stop_all,
                                  signal.SIGINT: scheduler.stop_all}
    assert {s: signal.getsignal(s) for s in before} == before  # pytest no se toca


def test_refuses_to_run_outside_linux(scheduler, capsys):
    def fail(*args):
        raise AssertionError("no debía lanzar nada")

    code = scheduler.main({}, popen=fail, wait=fail, install=fail, platform="darwin", now=NOW)
    assert code == 2
    assert "solo se ejecuta dentro del contenedor" in capsys.readouterr().err


# --- check.py -----------------------------------------------------------------

def test_check_passes_fixed_database_and_configuration(check):
    calls = []
    env = {"INGEST_API_URL": "http://127.0.0.1:9/api", "CAPTURE_INTERVAL_HOURS": "3",
           "COLLECTION_ENABLED": "true"}
    assert check.main(501, 20, env, run=lambda args: calls.append(args) or 0, after=no_backup) == 0
    assert calls == [[
        "--db=/app/data/prices.db",
        "--accept-command=docker compose run --rm ingest --accept-short-response",
        "--url=http://127.0.0.1:9/api",
        "--interval=3",
    ]]


def test_check_without_optional_configuration(check):
    calls = []
    check.main(501, 20, {"COLLECTION_ENABLED": "true"}, run=lambda args: calls.append(args) or 0,
               after=no_backup)
    assert calls == [["--db=/app/data/prices.db",
                      "--accept-command=docker compose run --rm ingest --accept-short-response"]]


@pytest.mark.parametrize(("uid", "gid", "reason"), [
    (0, 20, "no se permite ejecutar la ingesta como root"),
    (501, 0, "no se permite ejecutar la ingesta con el grupo root"),
])
def test_check_refuses_root_without_running(check, capsys, uid, gid, reason):
    calls = []
    assert check.main(uid, gid, {}, run=lambda args: calls.append(args), now=NOW) == 1
    assert calls == []
    out = capsys.readouterr().out
    assert out.startswith("2026-10-12 14:17:00 CEST · configuración no válida: ")
    assert reason in out


# --- check.py: COLLECTION_ENABLED y precedencia (scheduled-collection) --------

def never_run(args):
    raise AssertionError("no debía lanzar la comprobación (ni bloqueo, ni base, ni petición)")


def check_line(check, capsys, uid=501, gid=20, **env):
    code = check.main(uid, gid, env, run=never_run, now=NOW, after=no_backup)
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.startswith("2026-10-12 14:17:00 CEST · ")
    return code, out


@pytest.mark.parametrize("env", [{}, {"COLLECTION_ENABLED": ""}, {"COLLECTION_ENABLED": "false"},
                                 {"COLLECTION_ENABLED": "FALSE"}, {"COLLECTION_ENABLED": " false "}])
def test_check_disabled_does_nothing_and_says_how_to_enable(check, capsys, env):
    """Escenarios: Sin la variable; Variable vacía o false."""
    code, out = check_line(check, capsys, **env)
    assert code == 0
    assert "recogida desactivada en esta máquina" in out
    assert "COLLECTION_ENABLED=true en .env" in out


@pytest.mark.parametrize("value", ["yes", "1", "si"])
def test_check_invalid_value_is_invalid_configuration(check, capsys, value):
    """Escenario: Valor no válido."""
    code, out = check_line(check, capsys, COLLECTION_ENABLED=value)
    assert code == 1
    assert "configuración no válida" in out and repr(value) in out
    assert "solo 'true' activa la recogida" in out


@pytest.mark.parametrize("value", ["TRUE", " true ", "True"])
def test_check_enabled_forms_run_the_check(check, value):
    """Escenario: Formas admitidas."""
    calls = []
    check.main(501, 20, {"COLLECTION_ENABLED": value}, run=lambda args: calls.append(args) or 0,
               after=no_backup)
    assert len(calls) == 1


def test_root_without_variable_shows_root_not_disabled(check, capsys):
    """Escenario: Root sin la variable."""
    code, out = check_line(check, capsys, uid=0)
    assert code == 1
    assert "no se permite ejecutar la ingesta como root" in out
    assert "recogida desactivada" not in out


def test_invalid_interval_with_collection_disabled_shows_interval(check, capsys):
    """Escenario: Intervalo no válido con la recogida desactivada."""
    code, out = check_line(check, capsys, CAPTURE_INTERVAL_HOURS="seis", COLLECTION_ENABLED="false")
    assert code == 1
    assert "configuración no válida: CAPTURE_INTERVAL_HOURS no válido: 'seis'" in out
    assert "se admiten horas enteras de 1 a 24" in out
    assert "recogida desactivada" not in out


def test_root_with_invalid_value_shows_root_first(check, capsys):
    """Escenario: Valor no válido de la variable con root."""
    code, out = check_line(check, capsys, uid=0, COLLECTION_ENABLED="yes")
    assert "no se permite ejecutar la ingesta como root" in out
    assert "COLLECTION_ENABLED" not in out


def test_group_root_comes_before_interval(check, capsys):
    code, out = check_line(check, capsys, gid=0, CAPTURE_INTERVAL_HOURS="seis")
    assert "grupo root" in out and "CAPTURE_INTERVAL_HOURS" not in out


@pytest.mark.parametrize(("env", "text"), [
    ({"COLLECTION_ENABLED": "true"}, "; recogida activada"),
    ({"COLLECTION_ENABLED": " TRUE "}, "; recogida activada"),
    ({}, "; recogida desactivada (se activa con COLLECTION_ENABLED=true en .env)"),
    ({"COLLECTION_ENABLED": "yes"}, "; COLLECTION_ENABLED no válido ('yes')"),
])
def test_startup_line_shows_collection_state(scheduler, env, text):
    """Escenarios: Habilitada; Formas admitidas; Sin la variable; Valor no válido."""
    assert scheduler.startup_line(env, NOW).endswith(text)


# --- check.py: copia de arranque y reintento después de la captura (D6, D8) ----

class Recorder:
    def __init__(self, due=True):
        self.events, self._due = [], due

    def run(self, args):
        self.events.append("captura")
        return 0

    def copy(self, db, backups, clock, out, marker):
        self.events.append(("copia", str(db), str(backups), str(marker)))
        return 0

    def retry(self, db, backups, clock, out, marker):
        self.events.append(("reintento", str(marker)))
        return None

    def due(self, backups, now):
        return self._due

    def after(self, check):
        return lambda uid, gid, env, startup, clock: check.backup_after_check(
            uid, gid, env, startup, clock, copy=self.copy, retry=self.retry, due=self.due)


ENABLED = {"COLLECTION_ENABLED": "true"}


def test_startup_check_captures_first_then_copies(check):
    """Escenario: Arranque con captura pendiente (primero la ingesta)."""
    rec = Recorder(due=True)
    check.main(501, 20, ENABLED, run=rec.run, now=NOW, startup=True, after=rec.after(check))
    assert rec.events == ["captura", ("copia", "/app/data/prices.db", "/app/backups",
                                      "/tmp/backup-pending")]


def test_startup_check_without_old_copy_does_not_copy(check):
    """Escenario: Apagado solo a la hora de la copia (no toca copiar al arrancar)."""
    rec = Recorder(due=False)
    check.main(501, 20, ENABLED, run=rec.run, now=NOW, startup=True, after=rec.after(check))
    assert rec.events == ["captura"]


def test_hourly_check_retries_pending_copy_after_deciding(check):
    """Escenario: Orden en una comprobación con copia pendiente."""
    rec = Recorder()
    check.main(501, 20, ENABLED, run=rec.run, now=NOW, after=rec.after(check))
    assert rec.events == ["captura", ("reintento", "/tmp/backup-pending")]


def test_invalid_interval_does_not_capture_but_still_copies(check, capsys):
    """D8: con un intervalo no válido no se captura, pero la copia de arranque
    (última copia de hace 30 h) y el reintento sí se hacen, sin peticiones."""
    rec = Recorder(due=True)
    env = {**ENABLED, "CAPTURE_INTERVAL_HOURS": "seis"}
    assert check.main(501, 20, env, run=never_run, now=NOW, startup=True,
                      after=rec.after(check)) == 1
    assert rec.events == [("copia", "/app/data/prices.db", "/app/backups", "/tmp/backup-pending")]
    assert "CAPTURE_INTERVAL_HOURS no válido" in capsys.readouterr().out
    rec = Recorder()
    check.main(501, 20, env, run=never_run, now=NOW, after=rec.after(check))
    assert rec.events == [("reintento", "/tmp/backup-pending")]


@pytest.mark.parametrize(("uid", "gid", "env"), [
    (0, 20, ENABLED), (501, 0, ENABLED), (501, 20, {}), (501, 20, {"COLLECTION_ENABLED": "yes"}),
], ids=["root", "grupo-root", "desactivada", "valor-no-valido"])
def test_no_copy_when_copies_are_not_allowed(check, uid, gid, env):
    """Escenarios: Con la recogida desactivada (arranque) y root/grupo root lo paran todo."""
    rec = Recorder(due=True)
    check.main(uid, gid, env, run=never_run, now=NOW, startup=True, after=rec.after(check))
    check.main(uid, gid, env, run=never_run, now=NOW, after=rec.after(check))
    assert rec.events == []


def test_scheduler_removes_pending_marker_at_start(scheduler, tmp_path):
    """D6: tras reiniciar el programador, una copia pendiente no se recupera."""
    marker = tmp_path / "backup-pending"
    marker.write_text("2026-10-12")
    run_main(scheduler, lambda args: FakeProc(100), fake_wait((100, 0)))
    assert not marker.exists()


# --- backup.py -----------------------------------------------------------------

@pytest.fixture
def backup(monkeypatch):
    return load("backup", monkeypatch)


def backup_main(backup, *argv, uid=501, gid=20, env=None, run=None):
    calls = []

    def fake_run(db, backups, clock, out, marker):
        calls.append((str(db), str(backups), marker and str(marker)))
        return 0

    code = backup.main(uid, gid, ENABLED if env is None else env, list(argv),
                       run=run or fake_run, clock=lambda: NOW)
    return code, calls


def test_daily_copy_uses_pending_marker(backup):
    code, calls = backup_main(backup, "--daily")
    assert code == 0
    assert calls == [("/app/data/prices.db", "/app/backups", "/tmp/backup-pending")]


def test_manual_copy_never_leaves_pending(backup):
    code, calls = backup_main(backup, "--manual")
    assert calls == [("/app/data/prices.db", "/app/backups", None)]


@pytest.mark.parametrize(("uid", "gid", "env", "text"), [
    (501, 20, {}, "copias desactivadas en esta máquina; se activan con COLLECTION_ENABLED=true en .env"),
    (501, 20, {"COLLECTION_ENABLED": "false"}, "copias desactivadas en esta máquina"),
    (0, 20, ENABLED, "configuración no válida: no se permite ejecutar la ingesta como root"),
    (501, 0, ENABLED, "configuración no válida: no se permite ejecutar la ingesta con el grupo root"),
    (0, 20, {}, "configuración no válida: no se permite ejecutar la ingesta como root"),
    (501, 20, {"COLLECTION_ENABLED": "yes"}, "configuración no válida: COLLECTION_ENABLED no válido"),
], ids=["sin-variable", "false", "root", "grupo-root", "root-sin-variable", "valor-no-valido"])
def test_backup_refused_without_creating_anything(backup, capsys, uid, gid, env, text):
    """Escenarios: Recogida desactivada (04:43) y Copia a mano en el Mac: código
    distinto de 0, sin llamar a la copia (nada se crea en ./backups)."""
    for mode in ("--daily", "--manual"):
        code, calls = backup_main(backup, mode, uid=uid, gid=gid, env=env)
        assert code == 2 and calls == []
        assert text in capsys.readouterr().out


def test_backup_ignores_invalid_interval(backup):
    """D8: el intervalo solo afecta a la captura; la copia diaria se hace."""
    code, calls = backup_main(backup, "--daily", env={**ENABLED, "CAPTURE_INTERVAL_HOURS": "seis"})
    assert code == 0 and len(calls) == 1


def test_backup_interrupted_returns_130(backup, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    code, _ = backup_main(backup, "--manual", run=interrupted)
    assert code == 130
    assert "copia interrumpida" in capsys.readouterr().out


def test_backup_needs_a_mode(backup):
    with pytest.raises(SystemExit):
        backup_main(backup)


@pytest.mark.parametrize(("instant", "name"), [
    ("2026-10-17T02:43:00+00:00", "prices-2026-10-17.db.gz"),  # 04:43 CEST
    ("2026-10-25T03:43:00+00:00", "prices-2026-10-25.db.gz"),  # 04:43 CET, día del cambio
    ("2027-03-28T02:43:00+00:00", "prices-2027-03-28.db.gz"),  # 04:43 CEST, día del cambio
])
def test_copy_name_uses_madrid_date_on_dst_days(instant, name):
    """Escenarios: Copia de madrugada y Cambios de hora (lógica con reloj
    inyectado): la copia de las 04:43 de Madrid lleva la fecha de ese día."""
    from src.backup.make import madrid_date
    from src.backup.rotation import backup_name

    assert backup_name(madrid_date(datetime.fromisoformat(instant))) == name
