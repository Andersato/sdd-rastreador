"""«Salud del servicio» e «Intervalo no válido en la salud»: reglas puras (D9)."""

from datetime import datetime, timedelta

import pytest

from src.api.health import INVALID_CONFIG, OK, STALE, health_state


def utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


CAPTURE = utc("2026-10-16T07:26:37Z")


def test_everything_ok():
    """Escenario: Todo correcto."""
    state = health_state(CAPTURE, utc("2026-10-16T10:00:00Z"), None)
    assert (state.status, state.stale_after_hours) == (OK, 13)


def test_old_capture():
    """Escenario: Captura antigua (13 h 0 min 23 s)."""
    state = health_state(CAPTURE, utc("2026-10-16T20:27:00Z"), "")
    assert state.status == STALE


def test_exactly_on_the_threshold():
    """Escenario: Justo en el umbral."""
    assert health_state(CAPTURE, CAPTURE + timedelta(hours=13), None).status == OK


def test_other_interval():
    """Escenario: Otro intervalo."""
    state = health_state(CAPTURE, CAPTURE + timedelta(hours=24, minutes=30), "12")
    assert (state.status, state.stale_after_hours) == (OK, 25)


def test_accepted_forms():
    """Escenario: Formas admitidas."""
    assert health_state(CAPTURE, CAPTURE, " 3 ").stale_after_hours == 7


def test_capture_in_the_future():
    """Escenario: Captura con fecha en el futuro."""
    assert health_state(CAPTURE, CAPTURE - timedelta(hours=2), None).status == OK


@pytest.mark.parametrize("value", ["25", "0", "6.5", "seis"])
def test_invalid_interval(value):
    """Escenario: Intervalo imposible."""
    state = health_state(CAPTURE, CAPTURE, value)
    assert (state.status, state.stale_after_hours) == (INVALID_CONFIG, None)
    assert repr(value) in state.message
    assert "horas enteras de 1 a 24" in state.message
