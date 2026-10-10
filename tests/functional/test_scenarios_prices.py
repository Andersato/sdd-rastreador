"""Escenarios de precios, de principio a fin (descarga, parser, SQLite y resumen).

Requisitos: "Conversión de números con coma decimal", "Precio vacío o ausente
significa que no vende ese combustible", "Combustibles guardados" y "Precios
inválidos".
"""

import pytest

from tests.builders import response, station
from tests.scenario_helpers import (
    LAT,
    LON,
    assert_no_warnings,
    assert_one_warning,
    run_ingestion,
)
from tests.storage_helpers import ingest, prices_of, query, station_row

ALL_FUELS = [
    "Biodiesel", "Bioetanol", "Gas Natural Comprimido", "Gas Natural Licuado",
    "Gases licuados del petróleo", "Gasoleo A", "Gasoleo B", "Gasoleo Premium",
    "Gasolina 95 E10", "Gasolina 95 E5", "Gasolina 95 E5 Premium",
    "Gasolina 98 E10", "Gasolina 98 E5", "Hidrogeno", "Adblue",
]


def fuel_rows(db, station_id, fuel):
    """Filas de `prices` de ese combustible: debe ser [] si "no se guarda nada" (ni 0 ni vacío)."""
    return query(db, "SELECT price FROM prices WHERE station_id = ? AND fuel = ?", (station_id, fuel))


# --- Conversión de números con coma decimal ---------------------------------

def test_scenario_price_with_decimal_comma(http_server, tmp_path, capsys):
    """Escenario: Precio con coma decimal."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{"Precio Gasoleo A": "1,459"})), capsys
    )
    assert code == 0
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert query(db, "SELECT typeof(price) FROM prices") == [("real",)]
    assert_no_warnings(out)


def test_scenario_coordinates_with_decimal_comma_and_negative_sign(http_server, tmp_path, capsys):
    """Escenario: Coordenadas con coma decimal y signo negativo."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{LAT: "40,416775", LON: "-3,703790"})), capsys
    )
    assert code == 0
    assert station_row(db, "4375")[6:] == (40.416775, -3.70379)
    assert_no_warnings(out)


def test_scenario_spaces_around_and_more_decimals(http_server, tmp_path, capsys):
    """Escenario: Espacios alrededor y más decimales."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{"Precio Gasolina 95 E5": " 1,5290 "})), capsys
    )
    assert code == 0
    assert prices_of(db, "4375") == {"Gasolina 95 E5": 1.529}
    assert_no_warnings(out)


@pytest.mark.parametrize("value", ["\t1,459\n", " 1,459 ", "\r\n 1,459 \t"])
def test_scenario_tabs_and_newlines_around(http_server, tmp_path, capsys, value):
    """Escenario: Tabuladores y saltos de línea alrededor (también espacios no separables)."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{"Precio Gasoleo A": value})), capsys
    )
    assert code == 0
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert_no_warnings(out)


def test_scenario_decimal_point(http_server, tmp_path, capsys):
    """Escenario: Punto decimal."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{"Precio Gasoleo A": "1.459"})), capsys
    )
    assert code == 0
    assert fuel_rows(db, "4375", "Gasoleo A") == []
    assert_one_warning(out, "4375", "Gasoleo A", '"1.459"')


# --- Precio vacío o ausente --------------------------------------------------

def test_scenario_fuel_without_price(http_server, tmp_path, capsys):
    """Escenario: Combustible sin precio."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server,
        db,
        response(station("4375", **{"Precio Gasoleo A": "1,459", "Precio Hidrogeno": ""})),
        capsys,
    )
    assert code == 0
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert fuel_rows(db, "4375", "Hidrogeno") == []
    assert_no_warnings(out)


def test_scenario_price_with_only_spaces(http_server, tmp_path, capsys):
    """Escenario: Precio con solo espacios."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server,
        db,
        response(station("4375", **{"Precio Gasoleo A": "1,459", "Precio Gasolina 98 E5": "   "})),
        capsys,
    )
    assert code == 0
    assert fuel_rows(db, "4375", "Gasolina 98 E5") == []
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert_no_warnings(out)


def test_scenario_missing_price_field(http_server, tmp_path, capsys):
    """Escenario: Campo de precio ausente."""
    db = tmp_path / "p.db"
    data = response(station("4375", **{"Precio Gasoleo A": "1,459"}))
    assert "Precio Hidrogeno" not in data["ListaEESSPrecio"][0]
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert fuel_rows(db, "4375", "Hidrogeno") == []
    assert_no_warnings(out)


def test_scenario_null_price(http_server, tmp_path, capsys):
    """Escenario: Precio null."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server,
        db,
        response(station("4375", **{"Precio Gasoleo A": "1,459", "Precio Hidrogeno": None})),
        capsys,
    )
    assert code == 0
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert fuel_rows(db, "4375", "Hidrogeno") == []
    assert_no_warnings(out)


def all_prices_empty():
    return {f"Precio {fuel}": "" for fuel in ALL_FUELS}


def test_scenario_new_station_without_any_price(http_server, tmp_path, capsys):
    """Escenario: Estación sin ningún precio (estación nueva: se registra)."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server,
        db,
        response(
            station("4375", **{"Precio Gasoleo A": "1,459"}),
            station("5120", **{"Rótulo": "CEPSA", **all_prices_empty()}),
        ),
        capsys,
    )
    assert code == 0
    assert station_row(db, "5120")[1] == "CEPSA"
    assert prices_of(db, "5120") == {}
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert "Precios guardados: 1" in out
    assert_no_warnings(out)


def test_scenario_existing_station_without_any_price(http_server, tmp_path, capsys):
    """Escenario: Estación sin ningún precio (estación existente: se actualiza)."""
    db = tmp_path / "p.db"
    ingest(db, response(station("5120", **{"Precio Gasoleo A": "1,399"})))
    code, out, _ = run_ingestion(
        http_server, db, response(station("5120", **{"Rótulo": "CEPSA", **all_prices_empty()})), capsys
    )
    assert code == 0
    assert station_row(db, "5120")[1] == "CEPSA"
    assert prices_of(db, "5120", snapshot_id=1) == {"Gasoleo A": 1.399}
    assert prices_of(db, "5120", snapshot_id=2) == {}
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(2,)]
    assert "Estaciones procesadas: 1 (0 nuevas, 1 actualizada)" in out


# --- Combustibles guardados --------------------------------------------------

def test_scenario_several_fuels_in_one_station(http_server, tmp_path, capsys):
    """Escenario: Varios combustibles en una estación."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server,
        db,
        response(
            station(
                "4375",
                **{
                    "Precio Gasolina 95 E5": "1,529",
                    "Precio Gasoleo A": "1,459",
                    "Precio Gases licuados del petróleo": "0,899",
                },
            )
        ),
        capsys,
    )
    assert code == 0
    assert prices_of(db, "4375") == {
        "Gasolina 95 E5": 1.529,
        "Gasoleo A": 1.459,
        "Gases licuados del petróleo": 0.899,
    }
    assert "Precios guardados: 3" in out


# --- Precios inválidos -------------------------------------------------------

def test_scenario_price_with_unexpected_format(http_server, tmp_path, capsys):
    """Escenario: Precio con formato inesperado."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server,
        db,
        response(station("4375", **{"Precio Gasoleo A": "1,4a9", "Precio Gasolina 95 E5": "1,529"})),
        capsys,
    )
    assert code == 0
    assert prices_of(db, "4375") == {"Gasolina 95 E5": 1.529}
    assert fuel_rows(db, "4375", "Gasoleo A") == []
    assert station_row(db, "4375") is not None
    assert_one_warning(out, "4375", "Gasoleo A", '"1,4a9"')


def test_scenario_price_that_is_not_text(http_server, tmp_path, capsys):
    """Escenario: Precio que no es texto."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{"Precio Gasoleo A": 1.459})), capsys
    )
    assert code == 0
    assert fuel_rows(db, "4375", "Gasoleo A") == []
    assert_one_warning(out, "4375", "Gasoleo A", "1.459")


def test_scenario_zero_price(http_server, tmp_path, capsys):
    """Escenario: Precio cero."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{"Precio Gasoleo A": "0,000"})), capsys
    )
    assert code == 0
    assert fuel_rows(db, "4375", "Gasoleo A") == []
    assert query(db, "SELECT COUNT(*) FROM prices WHERE price <= 0") == [(0,)]
    assert_one_warning(out, "4375", "Gasoleo A", '"0,000"')


def test_scenario_negative_price(http_server, tmp_path, capsys):
    """Escenario: Precio negativo."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{"Precio Gasoleo A": "-1,459"})), capsys
    )
    assert code == 0
    assert fuel_rows(db, "4375", "Gasoleo A") == []
    assert_one_warning(out, "4375", "Gasoleo A", '"-1,459"')
