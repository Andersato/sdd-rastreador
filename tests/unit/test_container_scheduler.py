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


def test_starts_supercronic_and_startup_check_then_exits_with_supercronic(scheduler, capsys):
    launched = []
    waits = iter([(200, 0), (100, 3 << 8)])  # termina la comprobación y luego supercronic

    def popen(args):
        launched.append(args)
        return FakeProc(100 if len(launched) == 1 else 200)

    code = run_main(scheduler, popen, lambda: next(waits))
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


def test_startup_line_shows_configured_interval(scheduler):
    assert "intervalo configurado: 'seis'" in scheduler.startup_line(
        {"CAPTURE_INTERVAL_HOURS": "seis"}, NOW)


def test_stop_signal_is_sent_to_every_process(scheduler):
    sent = []
    scheduler.stop_all(signal.SIGTERM, None, kill=lambda pid, sig: sent.append((pid, sig)))
    assert sent == [(-1, signal.SIGTERM)]


def test_handlers_installed_for_sigterm_and_sigint(scheduler):
    waits = iter([(100, 0)])
    handlers = Handlers()
    before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    run_main(scheduler, lambda args: FakeProc(100), lambda: next(waits), handlers)
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
