"""Requisito «Comprobaciones de Linux en el VPS» (`server-deployment`): lo que
`docs/container-checks.md` debe decir. La ejecución real la hace el usuario."""

import re

import pytest

from tests.helpers import REPO_ROOT

TITLE = "## 4. Comprobaciones de Linux en el VPS"


@pytest.fixture(scope="module")
def doc():
    return (REPO_ROOT / "docs" / "container-checks.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def section(doc):
    assert TITLE in doc
    return re.split(r"^## ", doc.split(TITLE, 1)[1], maxsplit=1, flags=re.MULTILINE)[0]


def test_temporary_folder_outside_the_real_project(section):
    """Escenario: Carpeta temporal."""
    assert "~/ingest-check-" in section
    assert 'rm -rf "$PRUEBA"' in section
    assert "~/sdd-rastreador/data" in section and "no se tocan" in section
    commands = [line for line in section.splitlines() if line.startswith(("ic ", "docker ", "mv ", "sudo "))]
    assert not any("sdd-rastreador/data" in line or "sdd-rastreador/backups" in line
                   for line in commands)


def test_real_scheduler_untouched(section):
    """Escenario: Sin tocar el programador real: otro proyecto, sin build ni up."""
    assert "-p ingest-check" in section
    code = "\n".join(re.findall(r"```sh\n(.*?)```", section, flags=re.S))
    assert "build" not in code
    assert not re.search(r"\bic up\b|compose[^\n]* up\b", code)
    assert "ic run --rm ingest --url" in code


def test_fixture_server_without_opening_ports(section):
    """Escenario: Servidor de respuestas guardadas sin abrir puertos."""
    code = "\n".join(re.findall(r"```sh\n(.*?)```", section, flags=re.S))
    assert "tests/fixtures" in code
    assert "ufw allow" not in code and "-p 8000" not in code and "--publish" not in code
    assert code.count("sudo ufw status") == 2  # antes y después


def test_the_four_linux_scenarios(section):
    """Escenario: Escenarios cubiertos."""
    for name in ("Usuario del host con número distinto de 1000", "Base existente en Linux",
                 "Carpeta sin permiso de escritura", "Base de datos a nombre de otro usuario"):
        assert name in section
    assert section.count("Esperado:") >= 4


def test_results_table_with_room_for_date_and_result(doc):
    table = doc.split("### Lista de Linux en el VPS", 1)[1].split("###", 1)[0]
    assert "| Fecha | Escenario | Resultado |" in table
    for letter in "ABCD":
        assert f"| {letter} |" in table


def test_https_already_verified(doc):
    """Escenario: Conexión HTTPS real."""
    assert "15:17" in doc and "2026-10-16" in doc
    assert "No hace falta\n   repetirla" in doc


def test_post_archive_backup_checks_on_dst_days(doc):
    assert "copia diaria" in doc
    assert "grep '2026-10-25 04:4'" in doc and "grep '2027-03-28 04:4'" in doc
