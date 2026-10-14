"""Formato de las cifras en los mensajes de respuesta corta.

Con enteros, sin `float`: el porcentaje se trunca a décimas para que, por
ejemplo, 9.599 de 12.000 (79,99 %) se muestre como "79,9 %" y nunca como un
"80,0 %" que contradiría el rechazo.
"""


def thousands(n: int) -> str:
    """Entero con punto de miles: 12000 → "12.000"."""
    return f"{n:,}".replace(",", ".")


def percentage(part: int, whole: int) -> str:
    """Porcentaje truncado a una décima, con coma decimal: (9599, 12000) → "79,9 %"."""
    tenths = part * 1000 // whole
    return f"{thousands(tenths // 10)},{tenths % 10} %"
