"""Requisito «Formato de las cifras en los mensajes»."""

import pytest

from src.ingestion.formatting import percentage, thousands
from src.ingestion.storage import is_short


@pytest.mark.parametrize(
    ("n", "text"),
    [(7, "7"), (10, "10"), (999, "999"), (9000, "9.000"), (12000, "12.000"), (1234567, "1.234.567")],
)
def test_thousands_separator(n, text):
    assert thousands(n) == text


@pytest.mark.parametrize(
    ("part", "whole", "text"),
    [
        (9000, 12000, "75,0 %"),
        (9599, 12000, "79,9 %"),
        (9500, 12000, "79,1 %"),
        (8800, 9000, "97,7 %"),
        (7, 10, "70,0 %"),
        (9600, 12000, "80,0 %"),
        (12150, 12000, "101,2 %"),
    ],
)
def test_percentage_is_truncated_to_tenths(part, whole, text):
    assert percentage(part, whole) == text


@pytest.mark.parametrize(
    ("stations", "reference", "short"),
    [(9600, 12000, False), (9599, 12000, True), (9000, 12000, True), (12150, 12000, False),
     (8, 10, False), (7, 10, True), (0, 1, True)],
)
def test_short_response_threshold_with_integers(stations, reference, short):
    """Límites de «Respuesta con demasiadas pocas estaciones»: menos del 80 %."""
    assert is_short(stations, reference) is short
