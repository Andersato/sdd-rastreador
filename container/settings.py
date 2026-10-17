"""Configuración del programador leída de `.env` (a través de Compose).

`COLLECTION_ENABLED` decide si esta máquina recoge y hace copias: solo una
máquina debe hacerlo, para no partir el histórico en dos bases.
"""

ENABLE_HINT = "se activa con COLLECTION_ENABLED=true en .env"


class InvalidSetting(ValueError):
    """Valor de configuración no válido."""


def parse_enabled(text: str | None) -> bool:
    """`true` → activada; ausente, vacío o `false` → desactivada; otro valor → error.

    Sin distinguir mayúsculas e ignorando espacios alrededor. Compose ya
    recorta los espacios de `.env`, pero la variable puede llegar también
    pasada directamente (`-e`).
    """
    value = (text or "").strip().lower()
    if value == "true":
        return True
    if value in ("", "false"):
        return False
    raise InvalidSetting(
        f"COLLECTION_ENABLED no válido: {text!r}; solo 'true' activa la recogida"
    )


def collection_state(env: dict[str, str]) -> str:
    """Texto para la línea de arranque: activada, desactivada o valor no válido."""
    try:
        enabled = parse_enabled(env.get("COLLECTION_ENABLED"))
    except InvalidSetting:
        return f"COLLECTION_ENABLED no válido ({env.get('COLLECTION_ENABLED')!r})"
    return "recogida activada" if enabled else f"recogida desactivada ({ENABLE_HINT})"
