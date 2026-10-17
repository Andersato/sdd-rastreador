"""Limpieza de textos, redondeos y fechas de las respuestas (design.md, D7 y D8).

Nada de esto toca la base: solo cambia lo que se devuelve.
"""

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
UTC = timezone.utc


def clean_text(value: str | None) -> str | None:
    """Sin espacios en blanco alrededor (también tabuladores y no separables);
    los del interior se dejan. Vacío → None."""
    if value is None:
        return None
    text = value.strip()  # str.strip quita todo espacio Unicode, incluido U+00A0
    return text or None


def _decimal(value: float) -> Decimal:
    return Decimal(repr(value))


def round_half_up(value: float | Decimal, places: int) -> float:
    exact = value if isinstance(value, Decimal) else _decimal(value)
    return float(exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def average(prices: list[float], places: int = 3) -> float:
    """Media exacta de los precios, redondeada con la mitad hacia arriba."""
    total = sum((_decimal(p) for p in prices), Decimal(0))
    return round_half_up(total / len(prices), places)


def utc_text(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def source_date_text(local: str | None, downloaded_at: datetime) -> str | None:
    """Fecha de la fuente (hora de Madrid sin zona) con su desfase.

    En la hora repetida de octubre se elige el desfase que deja el instante
    más cerca de la descarga; en la hora que no existe de marzo, None.
    """
    if not local:
        return None
    try:
        naive = datetime.fromisoformat(local)
    except ValueError:
        return None
    candidates = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=MADRID, fold=fold)
        # Si al pasar a UTC y volver no sale la misma hora, esa hora no existe.
        if aware.astimezone(UTC).astimezone(MADRID).replace(tzinfo=None) == naive:
            candidates.append(aware)
    if not candidates:
        return None
    best = min(candidates, key=lambda aware: abs(aware.astimezone(UTC) - downloaded_at))
    return best.isoformat()
