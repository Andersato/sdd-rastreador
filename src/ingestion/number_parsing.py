"""Conversión de los números de la API ("1,459", "-3,703790") a valores numéricos.

No se llama `numbers.py` para no tapar el módulo estándar `numbers`.
"""

import math
import re
from decimal import Decimal

# Solo dígitos ASCII: `\d` aceptaría dígitos de otros alfabetos.
_DECIMAL_COMMA = re.compile(r"-?[0-9]+(,[0-9]+)?")


def parse_decimal(value: object) -> float | None:
    """Devuelve el número, o None si el valor no tiene el formato de la API.

    Acepta solo texto con coma decimal y cualquier número de decimales,
    ignorando los espacios en blanco de alrededor. El punto decimal ("1.459"),
    el texto vacío, cualquier valor que no sea texto y un número tan grande
    que no cabe en un float (sería infinito) son formato inválido.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _DECIMAL_COMMA.fullmatch(text):
        return None
    number = float(Decimal(text.replace(",", ".")))
    return number if math.isfinite(number) else None
