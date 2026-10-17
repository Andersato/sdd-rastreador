"""Rotación de las copias (`database-backup`, "Nombre y rotación de las copias" y
"Archivos ajenos y temporales en ./backups"), con nombres en una carpeta temporal."""

from datetime import date, timedelta

from src.backup.rotation import backup_name, keep, parse_name, rotate


def days(first, last):
    return [first + timedelta(n) for n in range((last - first).days + 1)]


def make(folder, dates, extra=()):
    for day in dates:
        (folder / backup_name(day)).write_bytes(b"x")
    for name in extra:
        (folder / name).write_bytes(b"ajeno")


def names(folder):
    return sorted(p.name for p in folder.iterdir())


def test_rotation_after_a_copy(tmp_path):
    """Escenario: Rotación tras una copia."""
    make(tmp_path, days(date(2026, 9, 1), date(2026, 10, 17)))
    removed, _ = rotate(tmp_path, date(2026, 10, 17))
    expected = [date(2026, 9, 13), date(2026, 9, 20), date(2026, 9, 27), date(2026, 10, 4),
                *days(date(2026, 10, 11), date(2026, 10, 17))]
    assert names(tmp_path) == sorted(backup_name(d) for d in expected)
    assert len(names(tmp_path)) == 11
    assert len(removed) == 36
    assert removed[0] == "prices-2026-09-01.db.gz" and removed[-1] == "prices-2026-10-10.db.gz"


def test_weeks_with_gaps(tmp_path):
    """Escenario: Semanas con huecos."""
    sparse = [date(2026, 8, 26), date(2026, 9, 2), date(2026, 9, 10), date(2026, 9, 16),
              date(2026, 9, 24)]
    make(tmp_path, sparse + days(date(2026, 10, 1), date(2026, 10, 7)))
    removed, _ = rotate(tmp_path, date(2026, 10, 7))
    assert removed == ["prices-2026-08-26.db.gz"]
    assert len(names(tmp_path)) == 11


def test_week_without_any_copy_does_not_count(tmp_path):
    """Escenario: Semana sin ninguna copia."""
    make(tmp_path, [date(2026, 9, 6), date(2026, 9, 13), date(2026, 9, 27), date(2026, 10, 4),
                    *days(date(2026, 10, 11), date(2026, 10, 17))])
    removed, _ = rotate(tmp_path, date(2026, 10, 17))
    assert removed == []
    assert len(names(tmp_path)) == 11


def test_first_copies(tmp_path):
    """Escenario: Primeras copias."""
    make(tmp_path, days(date(2026, 10, 15), date(2026, 10, 17)))
    assert rotate(tmp_path, date(2026, 10, 17)) == ([], [])
    assert len(names(tmp_path)) == 3


def test_impossible_date_is_foreign(tmp_path):
    """Escenario: Fecha imposible en el nombre."""
    assert parse_name("prices-2026-02-31.db.gz") is None
    make(tmp_path, days(date(2026, 10, 6), date(2026, 10, 17)), extra=["prices-2026-02-31.db.gz"])
    removed, future = rotate(tmp_path, date(2026, 10, 17))
    assert "prices-2026-02-31.db.gz" in names(tmp_path)
    assert "prices-2026-02-31.db.gz" not in removed and future == []


def test_future_date_is_foreign_and_reported(tmp_path):
    """Escenario: Fecha futura en el nombre: no ocupa ninguna diaria."""
    make(tmp_path, days(date(2026, 10, 6), date(2026, 10, 17)), extra=["prices-2030-01-01.db.gz"])
    removed, future = rotate(tmp_path, date(2026, 10, 17))
    assert future == ["prices-2030-01-01.db.gz"]
    assert "prices-2030-01-01.db.gz" in names(tmp_path)
    kept_days = [d for d in days(date(2026, 10, 11), date(2026, 10, 17))]
    for day in kept_days:
        assert backup_name(day) in names(tmp_path)


def test_foreign_files_are_untouched(tmp_path):
    """Escenario: Archivos ajenos."""
    make(tmp_path, days(date(2026, 10, 6), date(2026, 10, 17)),
         extra=["antes-de-migrar.db", "notas.txt", "prices-2026-10-01.db", "Prices-2026-10-01.db.gz"])
    rotate(tmp_path, date(2026, 10, 17))
    for name in ["antes-de-migrar.db", "notas.txt", "prices-2026-10-01.db", "Prices-2026-10-01.db.gz"]:
        assert (tmp_path / name).read_bytes() == b"ajeno"


def test_keep_is_by_name_date_only():
    assert keep([date(2026, 10, 17)]) == {date(2026, 10, 17)}
    assert keep([]) == set()
