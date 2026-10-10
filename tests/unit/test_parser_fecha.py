"""Fecha de la API (requisito "Captura con fecha y hora") a nivel de parser."""

import pytest

from src.ingestion.models import IngestionWarning
from src.ingestion.parser import parse_response
from tests.builders import response, station


def test_valid_fecha():
    result = parse_response(response(station(), fecha="10/10/2026 19:05:23"))
    assert result.source_date == "2026-10-10T19:05:23"
    assert result.warnings == []


def test_single_digit_fecha():
    result = parse_response(response(station(), fecha="1/2/2026 9:05:23"))
    assert result.source_date == "2026-02-01T09:05:23"
    assert result.warnings == []


def test_missing_fecha():
    result = parse_response(response(station(), drop=["Fecha"]))
    assert result.source_date is None
    assert result.warnings == [IngestionWarning(None, "Fecha", "(ausente)", "ausente")]


@pytest.mark.parametrize(
    "value, shown",
    [(None, "null"), ("2026-10-10 19:05", "2026-10-10 19:05"), ("31/02/2026 10:00:00", "31/02/2026 10:00:00")],
)
def test_invalid_fecha(value, shown):
    result = parse_response(response(station(**{"Precio Gasoleo A": "1,459"}), fecha=value))
    assert result.source_date is None
    assert result.warnings == [IngestionWarning(None, "Fecha", shown, "formato no válido")]
    assert len(result.prices) == 1
