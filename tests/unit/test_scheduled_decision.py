"""«Intervalo configurable» y «Cuándo toca capturar»: funciones puras (D6)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.ingestion.scheduled import INTERRUPTED, InvalidInterval, is_due, parse_interval
from src.ingestion.storage import LastSnapshot

UTC = timezone.utc


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def last(text, stations=10):
    return LastSnapshot(at(text), stations)


# --- parse_interval -----------------------------------------------------------

@pytest.mark.parametrize(("text", "hours"), [(None, 6), ("", 6), (" ", 6), (" 6 ", 6), ("06", 6),
                                             ("3", 3), ("1", 1), ("24", 24)])
def test_valid_intervals(text, hours):
    assert parse_interval(text) == hours


@pytest.mark.parametrize("text", ["0", "25", "6.5", "seis", "-1"])
def test_invalid_intervals_name_the_value(text):
    with pytest.raises(InvalidInterval) as exc:
        parse_interval(text)
    assert repr(text) in str(exc.value)
    assert "horas enteras de 1 a 24" in str(exc.value)


# --- is_due -------------------------------------------------------------------

def test_interval_met():
    """Escenario: Intervalo cumplido (faltan 40 s)."""
    assert is_due(last("2026-10-12T08:17:40Z"), at("2026-10-12T14:17:00Z"), 6).due


def test_interval_not_met():
    """Escenario: Intervalo no cumplido."""
    decision = is_due(last("2026-10-12T10:05:00Z"), at("2026-10-12T14:17:00Z"), 6)
    assert not decision.due
    assert decision.reason == "no toca capturar: última captura hace 4 h 12 min (intervalo 6 h)"


def test_exactly_at_the_margin():
    """Escenario: Justo en el margen (5 h 45 min)."""
    assert is_due(last("2026-10-12T08:32:00Z"), at("2026-10-12T14:17:00Z"), 6).due
    assert not is_due(last("2026-10-12T08:32:01Z"), at("2026-10-12T14:17:00Z"), 6).due


def test_no_captures():
    """Escenario: Sin capturas."""
    assert is_due(None, at("2026-10-12T14:17:00Z"), 6).due


def test_interrupted_ingestion():
    """Escenario: Diario pendiente de una ingesta cortada."""
    decision = is_due(INTERRUPTED, at("2026-10-12T14:17:00Z"), 6)
    assert decision.due
    assert "quedó a medias" in decision.notice


def test_recent_manual_capture():
    """Escenario: Captura manual reciente (13:20 de Madrid = 11:20Z)."""
    manual = last("2026-10-12T11:20:00Z")
    assert not is_due(manual, at("2026-10-12T12:17:00Z"), 6).due  # 14:17 de Madrid
    assert is_due(manual, at("2026-10-12T17:17:00Z"), 6).due  # 19:17: 5 h 57 min


def test_capture_slightly_in_the_future():
    """Escenario: Última captura poco en el futuro (33 min)."""
    decision = is_due(last("2026-10-12T14:50:00Z"), at("2026-10-12T14:17:00Z"), 6)
    assert not decision.due
    assert "posterior a la actual" in decision.reason


def test_capture_exactly_one_hour_in_the_future():
    """Escenario: Justo 1 hora en el futuro."""
    assert not is_due(last("2026-10-12T15:17:00Z"), at("2026-10-12T14:17:00Z"), 6).due


def test_capture_far_in_the_future():
    """Escenario: Última captura muy en el futuro."""
    decision = is_due(last("2030-01-01T00:00:00Z"), at("2026-10-12T14:17:00Z"), 6)
    assert decision.due
    assert "2030-01-01T00:00:00Z" in decision.notice


def test_default_and_configured_intervals():
    """Escenarios: Intervalo por defecto (5 h → no) e Intervalo configurado (3 h → sí)."""
    now = at("2026-10-12T14:17:00Z")
    assert not is_due(LastSnapshot(now - timedelta(hours=5), 10), now, parse_interval(None)).due
    assert is_due(LastSnapshot(now - timedelta(hours=3), 10), now, parse_interval("3")).due


def test_october_repeated_0217():
    """Escenario: Cambio de hora de octubre: la segunda 02:17 no toca."""
    first_0217 = last("2026-10-25T00:17:00Z")  # 02:17 CEST
    assert not is_due(first_0217, at("2026-10-25T01:17:00Z"), 6).due  # 02:17 CET
