"""«Catálogo de combustibles» e identificador corto (prices-api, D5)."""

import re
import unicodedata

from src.api.catalog import ADDITIVE, BY_SLUG, CATALOG, FUEL, PER_KG, PER_LITRE

EXPECTED = {
    "Adblue": "adblue",
    "Biodiesel": "biodiesel",
    "Bioetanol": "bioetanol",
    "Biogas Natural Comprimido": "biogas-natural-comprimido",
    "Biogas Natural Licuado": "biogas-natural-licuado",
    "Diésel Renovable": "diesel-renovable",
    "Gas Natural Comprimido": "gas-natural-comprimido",
    "Gas Natural Licuado": "gas-natural-licuado",
    "Gases licuados del petróleo": "gases-licuados-del-petroleo",
    "Gasoleo A": "gasoleo-a",
    "Gasoleo B": "gasoleo-b",
    "Gasoleo Premium": "gasoleo-premium",
    "Gasolina 95 E10": "gasolina-95-e10",
    "Gasolina 95 E25": "gasolina-95-e25",
    "Gasolina 95 E5": "gasolina-95-e5",
    "Gasolina 95 E5 Premium": "gasolina-95-e5-premium",
    "Gasolina 95 E85": "gasolina-95-e85",
    "Gasolina 98 E10": "gasolina-98-e10",
    "Gasolina 98 E5": "gasolina-98-e5",
    "Gasolina Renovable": "gasolina-renovable",
    "Hidrogeno": "hidrogeno",
}


def slug_rule(name: str) -> str:
    """La regla de la spec: minúsculas, sin tildes ni diéresis, espacios → guion."""
    plain = "".join(c for c in unicodedata.normalize("NFD", name)
                    if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", "-", plain.lower())


def test_catalog_content():
    """Escenario: Contenido del catálogo."""
    assert {fuel.name: fuel.slug for fuel in CATALOG} == EXPECTED
    assert len(CATALOG) == 21
    names = {fuel.name for fuel in CATALOG}
    assert "Amoniaco" not in names and "Metanol" not in names


def test_units():
    """Escenario: Unidades."""
    per_kg = {fuel.name for fuel in CATALOG if fuel.unit == PER_KG}
    assert per_kg == {"Gas Natural Comprimido", "Gas Natural Licuado",
                      "Biogas Natural Comprimido", "Biogas Natural Licuado", "Hidrogeno"}
    assert sum(fuel.unit == PER_LITRE for fuel in CATALOG) == 16
    assert PER_LITRE == "€/l" and PER_KG == "€/kg"


def test_adblue_is_an_additive():
    """Escenario: AdBlue."""
    adblue = BY_SLUG["adblue"]
    assert (adblue.kind, adblue.unit) == (ADDITIVE, "€/l")
    assert ADDITIVE == "aditivo" and FUEL == "combustible"
    assert [fuel.slug for fuel in CATALOG if fuel.kind != FUEL] == ["adblue"]


def test_every_slug_follows_the_rule():
    """Escenario: Identificadores (y los 21 del catálogo)."""
    for fuel in CATALOG:
        assert fuel.slug == slug_rule(fuel.name)
    assert slug_rule("Gasolina 95 E5 Premium") == "gasolina-95-e5-premium"
    assert slug_rule("Gases licuados del petróleo") == "gases-licuados-del-petroleo"
    assert slug_rule("Diésel Renovable") == "diesel-renovable"
