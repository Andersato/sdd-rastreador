"""Qué copias se conservan (D5). Lo usan el VPS y el Mac.

Solo cuentan los archivos `prices-AAAA-MM-DD.db.gz` con una fecha real que
no sea posterior al día en curso (de Madrid); el resto son ajenos. Manda la
fecha del nombre, no la del archivo.
"""

import re
from datetime import date
from pathlib import Path

DAILY = 7
WEEKLY = 4
NAME_RE = re.compile(r"prices-(\d{4})-(\d{2})-(\d{2})\.db\.gz")


def backup_name(day: date) -> str:
    return f"prices-{day.isoformat()}.db.gz"


def parse_name(name: str) -> date | None:
    """Fecha de un nombre de copia, o None si no sigue el patrón o la fecha no existe."""
    match = NAME_RE.fullmatch(name)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def classify(names, today: date) -> tuple[dict[date, str], list[str]]:
    """({fecha: nombre} de las copias válidas, nombres con fecha futura)."""
    valid, future = {}, []
    for name in names:
        day = parse_name(name)
        if day is None:
            continue
        if day > today:
            future.append(name)
        else:
            valid[day] = name
    return valid, sorted(future)


def keep(dates, today: date | None = None) -> set[date]:
    """Las 7 más recientes y, de las demás, la última de cada una de las 4 semanas
    (lunes a domingo) más recientes con copia y sin ninguna diaria."""
    ordered = sorted(set(dates), reverse=True)
    daily = ordered[:DAILY]
    daily_weeks = {day.isocalendar()[:2] for day in daily}
    latest_of_week = {}
    for day in ordered[DAILY:]:
        week = day.isocalendar()[:2]
        if week not in daily_weeks:
            latest_of_week.setdefault(week, day)  # `ordered` va de más a menos reciente
    weekly = [latest_of_week[week] for week in sorted(latest_of_week, reverse=True)[:WEEKLY]]
    return set(daily) | set(weekly)


def rotate(folder: Path, today: date) -> tuple[list[str], list[str]]:
    """Borra de `folder` las copias que sobran. Devuelve (borradas, con fecha futura)."""
    valid, future = classify((p.name for p in folder.iterdir() if p.is_file()), today)
    kept = keep(valid, today)
    removed = []
    for day in sorted(set(valid) - kept):
        (folder / valid[day]).unlink()
        removed.append(valid[day])
    return removed, future
