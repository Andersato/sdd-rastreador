"""Requisitos de `server-deployment`: lo que el runbook (`docs/vps-deployment.md`)
debe decir. Lo que se ve solo en el VPS lo verifica el usuario (tareas 4.4-4.6)."""

import re

import pytest

from tests.helpers import REPO_ROOT


@pytest.fixture(scope="module")
def doc():
    return (REPO_ROOT / "docs" / "vps-deployment.md").read_text(encoding="utf-8")


def sections(doc):
    return dict(re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", doc, flags=re.S | re.M))


def section(doc, start):
    return next(body for title, body in sections(doc).items() if title.startswith(start))


def code(text):
    return "\n".join(re.findall(r"```(?:sh)?\n(.*?)```", text, flags=re.S))


def test_server_data(doc):
    """Escenario: Datos del servidor."""
    head = doc.split("\n## ", 1)[0]
    for needed in ("IONOS", "Ubuntu 26.04", "x86_64", "2026-10-16", "15:17", "reinicio"):
        assert needed in head


def test_every_block_says_where(doc):
    """Escenario: Dónde se lanza cada comando: cada bloque de comandos va
    precedido de [Consola IONOS], [Panel de IONOS], [VPS] o [Mac]."""
    places = ("[Consola IONOS]", "[Panel de IONOS]", "[VPS]", "[Mac]")
    for title, body in sections(doc).items():
        if "```sh" in body:
            assert any(place in body for place in places), title


def test_no_secrets(doc):
    """Escenario: Sin secretos."""
    assert "<IP_DEL_VPS>" in doc
    # 127.0.0.1 y 0.0.0.0 no son la dirección del servidor: los nombra la API (prices-api).
    addresses = set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", doc))
    assert addresses <= {"127.0.0.1", "0.0.0.0"}
    assert "PRIVATE KEY" not in doc
    assert not re.search(r"ssh-ed25519 AAAA[0-9A-Za-z+/]{20,}", doc)


def test_web_console(doc):
    """Escenario: Consola web de IONOS."""
    part = section(doc, "2. Usuario `deploy`")
    assert "no permite pegar" in part and "teclado" in part and "inglés" in part
    for char in ("`-`", "`/`", "`:`", "`@`"):
        assert char in part
    commands = code(part).splitlines()
    assert commands and all(len(line.split("#")[0]) < 40 for line in commands)
    assert not any("-" in line.split("#")[0] for line in commands)


def test_key_only_access(doc):
    """Escenario: Acceso solo por clave."""
    part = section(doc, "4. Acceso solo por clave")
    for needed in ("00-solo-claves.conf", "PasswordAuthentication no",
                   "KbdInteractiveAuthentication no", "PermitRootLogin no", "50-cloud-init.conf",
                   "sshd -t", "sshd -T", "passwd -l deploy", "otra"):
        assert needed in part, needed
    assert part.index("sshd -t") < part.index("systemctl reload ssh") < part.index("sshd -T")


def test_firewall(doc):
    """Escenario: Cortafuegos."""
    part = code(section(doc, "6. Cortafuegos"))
    assert part.index("ufw allow OpenSSH") < part.index("ufw enable") < part.index("ufw status")
    assert "OpenSSH (v6)" in section(doc, "6. Cortafuegos")


def test_docker_from_ubuntu(doc):
    """Escenario: Docker desde los paquetes de Ubuntu."""
    part = section(doc, "7. Docker")
    assert "apt install -y docker.io docker-compose-v2" in part
    assert "usermod -aG docker deploy" in part and "docker compose version" in part
    assert "download.docker.com" not in doc


def test_deploy_key(doc):
    """Escenario: Clave de despliegue."""
    part = section(doc, "8. Repositorio")
    assert "ssh-keygen" in part and "Deploy keys" in part
    assert "sin" in part.lower() and "Allow write access" in part
    assert "git clone git@github.com:" in part


def test_swap_and_upgrades(doc):
    """Escenarios: Swap, Actualizaciones automáticas y Reinicio automático a las 05:30."""
    part = section(doc, "5. Sistema")
    assert "fallocate -l 2G /swapfile" in part and "/etc/fstab" in part
    assert "swapon --show" in part and "free -h" in part and "8 GB" in part
    assert "timedatectl set-timezone Europe/Madrid" in part
    assert "unattended-upgrades" in part and "20auto-upgrades" in part
    assert 'Automatic-Reboot "true"' in part and 'Automatic-Reboot-Time "05:30"' in part
    assert "04:43" in part and "06:17" in part


def test_project_configuration(doc):
    """Escenarios: .env del VPS, Variable comprobada antes de arrancar, Carpetas y
    Espacio en disco."""
    config = section(doc, "9. Configuración")
    assert "id -u" in config and "id -g" in config
    assert "mkdir -p data backups" in config and "ls -ld data backups" in config
    assert "df -h" in config and "240 GB" in config and "11 copias" in config
    start = code(section(doc, "12. Primer arranque"))
    lines = start.splitlines()
    up = next(i for i, line in enumerate(lines) if line.startswith("docker compose up -d"))
    grep = next(i for i, line in enumerate(lines) if line.startswith("grep COLLECTION_ENABLED .env"))
    assert grep < up
    assert "COLLECTION_ENABLED=true" in lines[grep - 1]


def test_migration(doc):
    """Escenarios: Migración correcta, Número de capturas distinto y Programador del
    Mac parado antes de copiar."""
    part = section(doc, "11. Migración")
    commands = code(part)
    assert commands.index("docker compose stop") < commands.index(".backup")
    assert "docker compose ps" in commands and "scp" in commands
    assert "PRAGMA integrity_check" in commands and "SELECT COUNT(*) FROM snapshots" in commands
    assert "sin `COLLECTION_ENABLED`" in part
    assert "no se arranca el programador del VPS" in part and "sin borrarla" in part
    assert "no se borra ni se modifica" in part


def test_startup_and_reboot_verification(doc):
    """Escenarios: Verificación tras reinicio, tras el primer arranque y Recogida
    desactivada por error."""
    part = section(doc, "12. Primer arranque")
    assert "recogida activada" in part and "No se da el despliegue por bueno" in part
    assert "recogida desactivada en esta máquina" in part
    assert "sudo reboot" in part and "docker compose ps" in part and "minuto 17" in part


def test_update_procedure(doc):
    """Escenarios: Actualización, Actualizar el VPS ya desplegado y Fallo al construir."""
    part = section(doc, "13. Actualizar")
    first = code(part.split("### Actualizar el VPS ya desplegado", 1)[0])
    order = ["docker compose run --rm backup", "git pull", "docker compose build",
             "docker compose up -d", "docker compose ps", "docker compose logs"]
    positions = [first.index(step) for step in order]
    assert positions == sorted(positions)
    assert "git checkout" in part
    old = code(part.split("### Actualizar el VPS ya desplegado", 1)[1])
    assert old.index("mkdir -p backups") < old.index("docker compose up -d")
    assert old.index("COLLECTION_ENABLED=true") < old.index("docker compose up -d")
    assert "mode=ro" in old
    for forbidden in ("down -v", "git clean", "rm -rf data", "rm -rf backups", "rm data", "rm backups"):
        assert forbidden not in code(doc)


def test_supercronic_warning(doc):
    """Escenario: Aviso en el log."""
    assert "process reaping disabled, not pid 1" in doc
    assert "tini" in doc and "proceso 1" in doc


def test_homebrew_rsync_in_the_runbook(doc):
    assert "brew install rsync" in doc and "openrsync" in doc


def test_unattended_upgrades_check_expected_output_and_how_to_enable(doc):
    """Escenario: Actualizaciones automáticas: cómo comprobar que está instalado y
    activo, la salida esperada y cómo activarlo si no lo está."""
    part = section(doc, "5. Sistema").split("### 5.4", 1)[1]
    for needed in ("dpkg -l unattended-upgrades", "systemctl is-enabled unattended-upgrades",
                   "systemctl is-active unattended-upgrades", "enabled", "active",
                   "apt install -y unattended-upgrades", "dpkg-reconfigure"):
        assert needed in part, needed


def test_timezone_is_checked_with_expected_output(doc):
    """Escenario: Reinicio automático a las 05:30 (zona horaria comprobada con
    `timedatectl`, que muestra `Europe/Madrid`)."""
    part = section(doc, "5. Sistema").split("### 5.3", 1)[1].split("### 5.4", 1)[0]
    commands = code(part).splitlines()
    assert commands.index("sudo timedatectl set-timezone Europe/Madrid") < commands.index("timedatectl")
    assert "Time zone: Europe/Madrid" in part
    reboot = section(doc, "5. Sistema").split("### 5.4", 1)[1]
    assert "05:30" in reboot and "04:43" in reboot and re.search(r"minuto\s+17", reboot)


def test_disk_space_before_first_start_and_in_updates(doc):
    """Escenario: Espacio en disco (`df -h` antes del primer arranque y en la
    actualización)."""
    start = code(section(doc, "12. Primer arranque"))
    assert start.index("df -h") < start.index("docker compose up -d")
    update = code(section(doc, "13. Actualizar").split("### Actualizar el VPS ya desplegado", 1)[0])
    assert "df -h" in update


def test_documented_startup_line_is_the_real_one(doc, monkeypatch):
    """Escenario: Verificación tras reinicio (el texto exacto que se espera ver): la
    línea de arranque que copia el runbook es la que escribe `scheduler.py` con
    `COLLECTION_ENABLED=true` y el intervalo por defecto."""
    import importlib.util
    from datetime import datetime, timezone

    container = REPO_ROOT / "container"
    monkeypatch.syspath_prepend(str(container))
    spec = importlib.util.spec_from_file_location("container_scheduler_doc", container / "scheduler.py")
    scheduler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scheduler)
    line = scheduler.startup_line({"COLLECTION_ENABLED": "true"},
                                  datetime(2026, 10, 17, 8, 15, tzinfo=timezone.utc))
    expected = line.split(" · ", 1)[1]
    assert f"… · {expected}\n" in section(doc, "12. Primer arranque")


def test_failed_build_keeps_previous_scheduler(doc):
    """Escenario: Fallo al construir."""
    part = section(doc, "13. Actualizar")
    assert re.search(r"sigue en marcha con la\s+imagen anterior", part)
    assert "git checkout <commit anterior>" in part


# --- «API en el VPS solo por túnel SSH» (prices-api) ---------------------------

API_UPDATE = "### Actualizar el VPS a la versión con la API"


@pytest.fixture(scope="module")
def api_update(doc):
    assert API_UPDATE in doc
    return doc.split(API_UPDATE, 1)[1].split("\n## ", 1)[0]


def test_update_to_the_api_version(api_update):
    """Escenario: Actualización a la versión con la API."""
    commands = code(api_update)
    steps = ["docker compose run --rm backup", "git pull", "docker compose build",
             "docker compose up -d", "docker compose ps",
             "curl -s http://127.0.0.1:8000/api/health", "sudo ss -tlnp", "sudo ufw status"]
    positions = [commands.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "127.0.0.1:8000" in api_update and "OpenSSH" in api_update
    assert "ufw allow" not in api_update


def test_health_just_after_starting(api_update):
    """Escenario: Salud justo después de arrancar."""
    assert "base_ocupada" in api_update and "desactualizada" in api_update
    assert "se repite" in api_update


def test_port_exposed_by_mistake(api_update):
    """Escenario: Puerto expuesto por error."""
    assert "0.0.0.0:8000" in api_update and "[::]:8000" in api_update
    assert "docker compose stop api" in api_update
    assert "docker-compose.yml" in api_update
    assert "No se toca `ufw`" in api_update


def test_tunnel_from_the_mac(doc):
    """Escenario: Túnel desde el Mac."""
    tunnel = section(doc, "14.")
    assert "ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>" in code(tunnel)
    assert "http://127.0.0.1:8000/api/docs" in tunnel
    assert "Ctrl+C" in tunnel
    assert "-L 8001:127.0.0.1:8000" in tunnel


def test_no_ufw_port_is_ever_opened(doc):
    """Requisito: el runbook nunca indica abrir un puerto en ufw para la API."""
    assert "ufw allow 8000" not in doc
    assert not re.search(r"ufw allow (?!OpenSSH)", code(doc))


def test_rollback_removes_the_api_container(doc):
    update = section(doc, "13.")
    assert "--remove-orphans" in update
