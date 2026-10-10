import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parents[1] / "fixtures"

JSON_FIXTURES = [
    "valid_two_stations.json", "valid_three_stations.json", "with_warnings.json",
    "root_list.json", "root_string.json", "resultado_error.json", "resultado_missing.json",
    "lista_missing.json", "lista_empty.json", "lista_object.json", "lista_string.json",
    "station_not_object.json", "ideess_missing.json", "ideess_empty.json",
    "ideess_spaces.json", "ideess_number.json", "ideess_null.json",
    "ideess_duplicate.json", "ideess_duplicate_spaces.json", "fecha_invalid.json",
]
OTHER_FIXTURES = ["not_json.xml", "not_json.html", "empty.json"]


@pytest.mark.parametrize("name", JSON_FIXTURES)
def test_json_fixture_loads(name):
    with open(FIXTURES / name, encoding="utf-8") as f:
        json.load(f)


@pytest.mark.parametrize("name", OTHER_FIXTURES)
def test_other_fixture_exists(name):
    assert (FIXTURES / name).exists()


def test_empty_fixture_is_zero_bytes():
    assert (FIXTURES / "empty.json").stat().st_size == 0
