"""Limpieza de textos, redondeos y fecha de la fuente (prices-api, D7 y D8)."""

from datetime import datetime, timezone

import pytest

from src.api.formatting import average, clean_text, round_half_up, source_date_text

UTC = timezone.utc


def utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


# --- textos -------------------------------------------------------------------

def test_spaces_around_are_removed():
    """Escenario: Texto con espacios."""
    assert clean_text(" GALP ") == "GALP"


def test_tabs_and_non_breaking_spaces():
    """Escenario: Tabuladores y espacios interiores."""
    assert clean_text("\tCALLE  MAYOR, 1 ") == "CALLE  MAYOR, 1"


@pytest.mark.parametrize("value", ["", "   ", "\t ", None])
def test_empty_text_is_null(value):
    """Escenario: Texto vacío."""
    assert clean_text(value) is None


# --- redondeos ----------------------------------------------------------------

def test_average_with_half():
    """Escenario: Media con mitad."""
    assert average([1.404, 1.405]) == 1.405


def test_madrid_average():
    """Escenario: Media de Madrid."""
    assert average([1.459, 1.459, 1.399, 1.299]) == 1.404


def test_distances_round_half_up():
    """Escenario: Mismo precio y distancias que se redondean igual."""
    assert round_half_up(2.0141, 2) == 2.01
    assert round_half_up(2.0112, 2) == 2.01
    assert round_half_up(2.005, 2) == 2.01  # round() de float daría 2.0
    assert round_half_up(3.4046, 2) == 3.4


# --- fecha de la fuente -------------------------------------------------------

def test_summer_offset():
    """Escenario: Captura de origen."""
    assert source_date_text("2026-10-16T09:26:34", utc("2026-10-16T07:26:37Z")) == \
        "2026-10-16T09:26:34+02:00"


def test_winter_offset():
    """Escenario: Fecha de la fuente en horario de invierno."""
    assert source_date_text("2026-11-02T06:16:58", utc("2026-11-02T05:17:03Z")) == \
        "2026-11-02T06:16:58+01:00"


def test_no_source_date():
    """Escenario: Captura sin fecha de la fuente."""
    assert source_date_text(None, utc("2026-11-02T05:17:03Z")) is None


def test_repeated_hour_second_time():
    """Escenario: Hora repetida."""
    assert source_date_text("2026-10-25T02:30:00", utc("2026-10-25T01:31:00Z")) == \
        "2026-10-25T02:30:00+01:00"


def test_repeated_hour_first_time():
    """Escenario: Hora repetida, primera vez."""
    assert source_date_text("2026-10-25T02:30:00", utc("2026-10-25T00:31:00Z")) == \
        "2026-10-25T02:30:00+02:00"


def test_hour_that_does_not_exist():
    """Escenario: Hora que no existe."""
    assert source_date_text("2027-03-28T02:30:00", utc("2027-03-28T01:31:00Z")) is None
