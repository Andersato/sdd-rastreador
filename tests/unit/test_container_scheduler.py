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

def test_crontab_runs_check_every_hour_at_minute_17(scheduler):
    assert scheduler.crontab() == "17 * * * * python /app/container/check.py\n"


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
    assert launched[1][-1] == "/app/container/check.py"
    with open(scheduler.CRONTAB_PATH) as f:
        assert f.read() == scheduler.crontab()
    assert capsys.readouterr().out == (
        "2026-10-12 14:17:00 CEST · programador en marcha: comprobación ahora y cada hora en el "
        "minuto 17; intervalo configurado: 6 (por defecto)\n"
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
    env = {"INGEST_API_URL": "http://127.0.0.1:9/api", "CAPTURE_INTERVAL_HOURS": "-1"}
    assert check.main(501, 20, env, run=lambda args: calls.append(args) or 0) == 0
    assert calls == [[
        "--db=/app/data/prices.db",
        "--accept-command=docker compose run --rm ingest --accept-short-response",
        "--url=http://127.0.0.1:9/api",
        "--interval=-1",
    ]]


def test_check_without_optional_configuration(check):
    calls = []
    check.main(501, 20, {}, run=lambda args: calls.append(args) or 0)
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
