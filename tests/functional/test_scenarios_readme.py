"""Escenario «Instrucciones en el README» (requisito «Documentación del programador»
de `scheduled-collection`): se lee la sección del programador del README.

Solo se comprueba lo que se puede comprobar con texto (comandos y avisos);
que la redacción sea clara se revisa a mano.
"""

import re

import pytest

from tests.helpers import REPO_ROOT

SECTION_TITLE = "## Recogida automática (programador)"


@pytest.fixture(scope="module")
def section():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert SECTION_TITLE in text, "el README no tiene la sección del programador"
    body = text.split(SECTION_TITLE, 1)[1]
    return re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]


@pytest.mark.parametrize("command", [
    "docker compose up -d",
    "docker compose logs",
    "docker compose stop",
    "docker compose down",
    "docker compose run --rm ingest --accept-short-response",
    "CAPTURE_INTERVAL_HOURS",
    "INGEST_API_URL",
])
def test_scenario_readme_includes_commands(section, command):
    """Escenario: Instrucciones en el README (comandos y variables)."""
    assert command in section


def test_scenario_readme_interval_change_needs_up_again(section):
    """Escenario: Instrucciones en el README (tras cambiar el intervalo, volver a `up -d`)."""
    part = section.split("CAPTURE_INTERVAL_HOURS", 1)[1]
    assert re.search(r"vuelve a lanzar `docker compose up -d`", part)


def test_scenario_readme_docker_starts_at_login(section):
    """Escenario: Instrucciones en el README (el entorno de Docker arranca al iniciar sesión)."""
    assert "al iniciar sesión" in section
    assert "brew services start colima" in section


def test_scenario_readme_warns_against_venv(section):
    """Escenario: Instrucciones en el README (aviso de no usar `.venv` con el programador activo)."""
    assert re.search(r"No uses la ingesta\s+con `\.venv` mientras el programador está activo",
                     section)


def test_scenario_readme_api_url_only_for_tests(section):
    """Escenario: Instrucciones en el README (URL de la API presentada solo para pruebas)."""
    heading = next(line for line in section.splitlines() if "otra URL de la API" in line)
    assert heading.startswith("### ") and "pruebas" in heading.lower()
    part = section.split(heading, 1)[1]
    assert "INGEST_API_URL" in part
    assert "no la pongas en el uso normal" in part


def test_scenario_readme_one_machine_collects(section):
    """Escenario: Una sola máquina recoge."""
    heading = next(line for line in section.splitlines() if "Una sola máquina recoge" in line)
    part = section.split(heading, 1)[1].split("\n### ", 1)[0]
    assert "COLLECTION_ENABLED=true" in part
    assert "VPS" in part
    assert "no hace nada" in part
    assert re.search(r"no lances `docker compose run --rm ingest` contra la\s+API real en otra máquina",
                     part)
    assert "partiría" in part or "parte el histórico en dos bases" in part
    assert "backups" in section


def test_readme_backups_section():
    """2.9: sección de copias del README (cuándo, dónde, copia a mano, log)."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    body = text.split("## Copias de seguridad", 1)[1]
    body = re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]
    for needed in ("04:43", "26 horas", "docker compose run --rm backup", "backups/",
                   "prices-AAAA-MM-DD.db.gz", "7 más recientes", "4 semanales",
                   "copia guardada:", "copia pendiente:", "COLLECTION_ENABLED=true"):
        assert needed in body, needed


# --- «Documentación de la API en el README» (prices-api) ------------------------

API_TITLE = "## API de consulta"


@pytest.fixture(scope="module")
def api_section():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert API_TITLE in text, "el README no tiene la sección de la API"
    body = text.split(API_TITLE, 1)[1]
    return re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]


@pytest.mark.parametrize("needed", [
    "docker compose up -d",
    "http://127.0.0.1:8000/api/docs",
    "ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>",
    "./data",
    "./backups",
    "CAPTURE_INTERVAL_HOURS",
    "13 h",
    "solo lectura",
    "Nunca modifica la base",
    "8000 ya está ocupado",
])
def test_readme_api_section(api_section, needed):
    """Escenario: Lectura del README."""
    assert needed in api_section


def test_readme_health_states(api_section):
    for state in ("`ok`", "`desactualizada`", "`configuracion_no_valida`", "`error`"):
        assert state in api_section
    assert "dos veces" in api_section and "más 1 hora" in api_section
