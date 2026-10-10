import pytest

from src.ingestion.number_parsing import parse_decimal


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1,459", 1.459),
        ("-3,703790", -3.70379),
        (" 1,5290 ", 1.529),
        ("\t1,459\n", 1.459),
        (" 1,459", 1.459),
        ("40,416775", 40.416775),
        ("2", 2.0),
    ],
)
def test_valid_numbers(text, expected):
    assert parse_decimal(text) == expected


@pytest.mark.parametrize(
    "value",
    ["1.459", "1,4a9", "abc", "", "   ", "١,٢", "1,", ",5", "1,459,1", "+1,459", 1.459, 1459, None, True],
)
def test_invalid_numbers(value):
    assert parse_decimal(value) is None


def test_number_too_large_for_float_is_invalid():
    # Cumple el formato, pero como float sería infinito.
    assert parse_decimal("1" * 400) is None
    assert parse_decimal("-" + "9" * 400 + ",5") is None
