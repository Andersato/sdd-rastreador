"""Hook `.claude/hooks/guard_real_project.py`: protege el proyecto real (programador,
imagen y data/) de los comandos Bash de cualquier agente."""

import importlib.util
import json
import subprocess
import sys

import pytest

from tests.helpers import REPO_ROOT

HOOK = REPO_ROOT / ".claude" / "hooks" / "guard_real_project.py"
REPO = str(REPO_ROOT)


def load_hook():
    spec = importlib.util.spec_from_file_location("guard_real_project", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = load_hook()

BLOCKED = [
    # docker compose sobre el proyecto real
    "docker compose up -d",
    "docker compose build",
    "docker compose down",
    "docker compose stop scheduler",
    "docker compose restart scheduler",
    "docker compose start",
    "docker compose run --rm ingest",
    "docker compose -f docker-compose.yml run --rm ingest --help",
    "docker compose -p sdd-rastreador stop",
    "docker compose --project-name=sdd-rastreador down",
    "COMPOSE_PROJECT_NAME=sdd-rastreador docker compose down",
    "docker compose --profile manual build",
    "docker-compose up -d",
    "cd /tmp && docker compose down",
    "git status && docker compose down",
    'bash -c "docker compose down"',
    "sh -c 'docker compose stop'",
    "echo $(docker compose stop)",
    "eval docker compose down",
    "sudo docker compose down",
    # contenedores del proyecto real
    "docker stop sdd-rastreador-scheduler-1",
    "docker rm -f sdd-rastreador-scheduler-1",
    "docker kill sdd-rastreador-scheduler-1",
    "docker restart sdd-rastreador-scheduler-1",
    "docker container stop sdd-rastreador-scheduler-1",
    "docker container rm sdd-rastreador-scheduler-1",
    "docker stop $(docker ps -q)",
    "docker ps -q | xargs docker stop",
    "docker ps -aq | xargs -n1 docker rm -f",
    "docker system prune -f",
    "docker container prune -f",
    "docker image prune -a",
    # imagen real
    "docker build -t precios-gasolineras-ingest .",
    "docker build --tag=precios-gasolineras-ingest:latest .",
    "docker buildx build -t precios-gasolineras-ingest .",
    "docker rmi precios-gasolineras-ingest",
    "docker image rm precios-gasolineras-ingest:latest",
    "docker tag otra-imagen precios-gasolineras-ingest",
    # data/
    "rm data/prices.db",
    "rm -rf data",
    "rm -f ./data/prices.db-journal",
    f"rm {REPO}/data/prices.db",
    "mv data/prices.db /tmp/",
    "cp /tmp/otra.db data/prices.db",
    "echo hola > data/x",
    "echo hola >> ./data/prices.db",
    "sqlite3 data/prices.db 'DELETE FROM prices'",
    f"sqlite3 {REPO}/data/prices.db",
    "touch data/x",
    "mkdir data/copias",
    "sed -i '' s/a/b/ data/x",
    "echo x | tee data/x",
    "dd if=/dev/zero of=data/prices.db count=1",
    "find data -delete",
    "cd data && rm prices.db",
    "git clean -fdx",
    ".venv/bin/python -m src.ingestion",
    "python -m src.ingestion --db data/prices.db",
    "python -m src.ingestion --db=data/prices.db --url http://127.0.0.1:1/api",
    "python -m src.ingestion.scheduled --db data/prices.db",
]

ALLOWED = [
    "docker compose logs scheduler",
    "docker compose logs -f --tail 20 scheduler",
    "docker compose ps",
    "docker compose ps -a scheduler",
    "docker compose -p pgtest-abcd up -d",
    "docker compose -p pgtest-abcd -f /tmp/x/docker-compose.yml down",
    "COMPOSE_PROJECT_NAME=pgtest-1 docker compose stop",
    "docker ps -a",
    "docker images",
    "docker stop pgtest-1234",
    "docker rm -f pgtest-1234",
    "docker build -t precios-gasolineras-ingest-test .",
    "docker image inspect precios-gasolineras-ingest --format '{{.Id}}'",
    "docker run --rm --entrypoint supercronic precios-gasolineras-ingest-test -version",
    "sqlite3 -readonly data/prices.db 'SELECT COUNT(*) FROM snapshots'",
    "cp data/prices.db ~/prices.db.copia",
    "ls -la data",
    "du -sh data",
    "echo data",
    ".venv/bin/python -m pytest tests -q",
    "python -m src.ingestion --url http://127.0.0.1:1/api --db /tmp/x.db",
    "python -m src.ingestion --help",
    "rm -rf /tmp/pgtest-1",
    "git status",
    "git clean -n",
    "openspec validate add-scheduled-collection --strict",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked(command):
    assert hook.deny_reason(command, REPO) is not None, command


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed(command):
    assert hook.deny_reason(command, REPO) is None, hook.deny_reason(command, REPO)


def test_data_path_depends_on_working_directory():
    assert hook.deny_reason("rm data/x", "/tmp") is None
    assert hook.deny_reason("rm prices.db", f"{REPO}/data") is not None


def run_hook(payload):
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30)


def test_script_denies_with_message_for_the_user():
    result = run_hook({"tool_name": "Bash", "cwd": REPO,
                       "tool_input": {"command": "docker compose down"}})
    assert result.returncode == 0
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    assert "las hace el usuario" in output["permissionDecisionReason"]


def test_script_allows_silently():
    result = run_hook({"tool_name": "Bash", "cwd": REPO,
                       "tool_input": {"command": "docker compose logs scheduler"}})
    assert (result.returncode, result.stdout) == (0, "")


def test_script_ignores_other_tools():
    result = run_hook({"tool_name": "Read", "tool_input": {"file_path": "data/prices.db"}})
    assert (result.returncode, result.stdout) == (0, "")


def test_script_blocks_if_input_is_not_json():
    result = subprocess.run([sys.executable, str(HOOK)], input="no es json",
                            capture_output=True, text=True, timeout=30)
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_script_runs_with_system_python():
    """El hook se lanza con el python3 del sistema (3.9 en macOS), no con el .venv."""
    result = subprocess.run(["/usr/bin/python3", str(HOOK)], timeout=30, capture_output=True,
                            text=True, input=json.dumps({"tool_name": "Bash", "cwd": REPO,
                                                         "tool_input": {"command": "rm -rf data"}}))
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
