"""Estado de la salud del servicio (design.md, D9).

`desactualizada` si la última captura tiene más de dos veces el intervalo de
captura más una hora. El intervalo se lee con las mismas reglas que el
programador; si no es válido, la salud lo dice.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.ingestion.scheduled import InvalidInterval, parse_interval

OK = "ok"
STALE = "desactualizada"
INVALID_CONFIG = "configuracion_no_valida"
ERROR = "error"


@dataclass(frozen=True)
class HealthState:
    status: str
    stale_after_hours: int | None
    message: str | None = None


def stale_after_hours(interval_h: int) -> int:
    return 2 * interval_h + 1


def health_state(downloaded_at: datetime, now: datetime, interval_text: str | None) -> HealthState:
    try:
        interval_h = parse_interval(interval_text)
    except InvalidInterval as exc:
        return HealthState(INVALID_CONFIG, None, str(exc))
    threshold = stale_after_hours(interval_h)
    # Una captura con fecha en el futuro tiene antigüedad negativa: ok.
    status = STALE if now - downloaded_at > timedelta(hours=threshold) else OK
    return HealthState(status, threshold)
