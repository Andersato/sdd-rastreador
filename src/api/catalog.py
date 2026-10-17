"""Catálogo fijo de combustibles que expone la API (design.md, D5).

Los nombres son los que guarda la ingesta (el campo `Precio …` de la API sin
el prefijo). Los identificadores se escriben a mano: son el contrato con la
futura interfaz. Amoniaco y Metanol quedan fuera hasta conocer su unidad con
datos reales.
"""

from dataclasses import dataclass

PER_LITRE = "€/l"
PER_KG = "€/kg"
FUEL = "combustible"
ADDITIVE = "aditivo"


@dataclass(frozen=True)
class Fuel:
    name: str
    slug: str
    unit: str
    kind: str = FUEL

    def as_dict(self) -> dict:
        return {"name": self.name, "slug": self.slug, "unit": self.unit, "kind": self.kind}


CATALOG: tuple[Fuel, ...] = (
    Fuel("Adblue", "adblue", PER_LITRE, ADDITIVE),
    Fuel("Biodiesel", "biodiesel", PER_LITRE),
    Fuel("Bioetanol", "bioetanol", PER_LITRE),
    Fuel("Biogas Natural Comprimido", "biogas-natural-comprimido", PER_KG),
    Fuel("Biogas Natural Licuado", "biogas-natural-licuado", PER_KG),
    Fuel("Diésel Renovable", "diesel-renovable", PER_LITRE),
    Fuel("Gas Natural Comprimido", "gas-natural-comprimido", PER_KG),
    Fuel("Gas Natural Licuado", "gas-natural-licuado", PER_KG),
    Fuel("Gases licuados del petróleo", "gases-licuados-del-petroleo", PER_LITRE),
    Fuel("Gasoleo A", "gasoleo-a", PER_LITRE),
    Fuel("Gasoleo B", "gasoleo-b", PER_LITRE),
    Fuel("Gasoleo Premium", "gasoleo-premium", PER_LITRE),
    Fuel("Gasolina 95 E10", "gasolina-95-e10", PER_LITRE),
    Fuel("Gasolina 95 E25", "gasolina-95-e25", PER_LITRE),
    Fuel("Gasolina 95 E5", "gasolina-95-e5", PER_LITRE),
    Fuel("Gasolina 95 E5 Premium", "gasolina-95-e5-premium", PER_LITRE),
    Fuel("Gasolina 95 E85", "gasolina-95-e85", PER_LITRE),
    Fuel("Gasolina 98 E10", "gasolina-98-e10", PER_LITRE),
    Fuel("Gasolina 98 E5", "gasolina-98-e5", PER_LITRE),
    Fuel("Gasolina Renovable", "gasolina-renovable", PER_LITRE),
    Fuel("Hidrogeno", "hidrogeno", PER_KG),
)

BY_SLUG = {fuel.slug: fuel for fuel in CATALOG}
BY_NAME = {fuel.name: fuel for fuel in CATALOG}
