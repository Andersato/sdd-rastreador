"""Hook PreToolUse (Bash): protege el proyecto real mientras el programador está en marcha.

Bloquea, para cualquier agente, los comandos Bash que:
- usan `docker compose` sobre el proyecto real (sin `-p pgtest-…`), salvo
  `docker compose logs` y `docker compose ps`, que son de solo lectura;
- paran, borran, matan o reinician contenedores que no sean `pgtest-…`
  (los del proyecto real se llaman `sdd-rastreador-…`);
- reconstruyen, sustituyen o borran la imagen `precios-gasolineras-ingest`;
- borran, mueven o escriben en `data/` (sqlite3 solo con `-readonly`).

Lee el JSON del hook por la entrada estándar. Si bloquea, escribe la decisión
`deny` con el motivo; si no, no escribe nada. Se analiza el comando entero:
comandos encadenados (`&&`, `;`, `|`), `bash -c "…"`, `$(…)`, `xargs`,
redirecciones (`>`, `>>`) y `cd`. Ante la duda, bloquea.

Compatible con el python3 del sistema de macOS (3.9). Si algo falla dentro del
hook, bloquea: un hook que falla dejaría pasar el comando.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
REAL_DATA = os.path.normpath(PROJECT_DIR / "data")
REAL_PROJECT = PROJECT_DIR.name.lower()
REAL_IMAGE = "precios-gasolineras-ingest"
TEST_PREFIX = "pgtest"

READ_ONLY_COMPOSE = {"logs", "ps"}
CONTAINER_KILLERS = {"stop", "rm", "kill", "restart"}
DOCKER_GLOBAL_WITH_VALUE = {"--context", "-c", "--host", "-H", "--config", "--log-level", "-l",
                            "--tlscacert", "--tlscert", "--tlskey"}
COMPOSE_GLOBAL_WITH_VALUE = {"-f", "--file", "-p", "--project-name", "--profile", "--env-file",
                             "--project-directory", "--ansi", "--progress", "--parallel"}
WRAPPERS = {"sudo", "env", "command", "time", "nohup", "exec", "builtin", "nice"}
SHELLS = {"sh", "bash", "zsh", "dash"}
CONTROL = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")", "{", "}", "\n"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>", "1>", "2>", "1>>", "2>>"}
# Escriben o borran en cualquiera de sus argumentos.
WRITERS_ANY_ARG = {"rm", "rmdir", "mv", "unlink", "shred", "truncate", "touch", "chmod", "chown",
                   "ln", "mkdir", "tee", "chgrp"}
# Escriben en su último argumento (destino).
WRITERS_LAST_ARG = {"cp", "rsync", "install", "scp"}

MESSAGE = ("Bloqueado por el hook del proyecto: {reason}. Las acciones sobre el proyecto real "
           "(programador, imagen o data/) las hace el usuario: dale el comando exacto y espera "
           "a que te pase el resultado.")


def deny_reason(command: str, cwd: str | None = None) -> str | None:
    """Motivo para bloquear `command`, o None si se permite."""
    return _analyze(command, os.path.normpath(cwd or str(PROJECT_DIR)), depth=0)


def _analyze(command: str, cwd: str, depth: int) -> str | None:
    if depth > 5:
        return "comando anidado demasiado complejo para comprobarlo"
    # Las sustituciones de comandos se analizan como comandos aparte; en el
    # comando de fuera queda "?" (un valor que no se conoce).
    flat = command.replace("$(", " ? ; ").replace("`", " ? ; ").replace("<(", " ? ; ")
    try:
        lexer = shlex.shlex(flat, posix=True, punctuation_chars=";&|()<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        if re.search(r"docker|data|sqlite3|\brm\b|\bmv\b", command):
            return "no se ha podido analizar el comando (comillas sin cerrar)"
        return None
    for segment in _segments(tokens):
        reason, cwd = _check_segment(segment, cwd, depth)
        if reason:
            return reason
    return None


def _segments(tokens: list[str]):
    current = []
    for token in tokens:
        if token in CONTROL:
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def _check_segment(tokens: list[str], cwd: str, depth: int) -> tuple[str | None, str]:
    words, redirect_targets = _split_redirects(tokens)
    for target in redirect_targets:
        if _in_real_data(target, cwd):
            return f"redirección que escribe en data/ ({target})", cwd
    env, words = _strip_prefix(words)
    if not words:
        return None, cwd
    name = os.path.basename(words[0])
    args = words[1:]
    if name == "cd":
        target = args[0] if args else str(Path.home())
        return None, os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
    if name in SHELLS and "-c" in args[:-1]:
        return _analyze(args[args.index("-c") + 1], cwd, depth + 1), cwd
    if name == "eval":
        return _analyze(" ".join(args), cwd, depth + 1), cwd
    if name == "xargs":
        inner = _xargs_command(args)
        if inner:
            # Los argumentos que añade xargs no se conocen: se marca con "?".
            return _check_segment([*inner, "?"], cwd, depth)[0], cwd
        return None, cwd
    if name == "docker":
        return _check_docker(args, env), cwd
    if name == "docker-compose":
        return _check_compose(args, env), cwd
    return _check_writes(name, args, cwd), cwd


def _split_redirects(tokens):
    words, targets = [], []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in REDIRECTS or re.fullmatch(r"\d*>+\|?|&>+", token):
            if i + 1 < len(tokens):
                targets.append(tokens[i + 1])
            i += 2
            continue
        if token in {"<", "<<", "<<<"}:
            i += 2
            continue
        words.append(token)
        i += 1
    return words, targets


def _strip_prefix(words):
    env = {}
    i = 0
    while i < len(words):
        word = words[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", word):
            key, _, value = word.partition("=")
            env[key] = value
        elif os.path.basename(word) in WRAPPERS:
            pass
        elif word.startswith("-") and i > 0 and os.path.basename(words[i - 1]) in WRAPPERS:
            pass  # opciones de sudo/env/nice…
        else:
            break
        i += 1
    return env, words[i:]


def _xargs_command(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in {"-I", "-n", "-P", "-L", "-d", "-s", "-E"} else 1
    return args[i:]


# --- Docker -------------------------------------------------------------------

def _check_docker(args, env) -> str | None:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in DOCKER_GLOBAL_WITH_VALUE else 1
    rest = args[i:]
    if not rest:
        return None
    sub, sub_args = rest[0], rest[1:]
    if sub == "compose":
        return _check_compose(sub_args, env)
    if sub in {"container", "image", "system", "buildx", "builder"} and sub_args:
        sub, sub_args = f"{sub} {sub_args[0]}", sub_args[1:]
    if sub in CONTAINER_KILLERS or sub in {f"container {c}" for c in CONTAINER_KILLERS}:
        return _check_container_targets(sub, sub_args)
    if sub in {"container rm", "container remove"}:
        return _check_container_targets(sub, sub_args)
    if sub.endswith("prune"):
        return f"`docker {sub}` puede borrar contenedores o la imagen del proyecto real"
    if sub in {"build", "buildx build", "image build"}:
        for tag in _option_values(sub_args, {"-t", "--tag"}):
            if _is_real_image(tag):
                return f"`docker {sub}` sustituiría la imagen real {REAL_IMAGE}"
        return None
    if sub in {"rmi", "image rm", "image remove"}:
        if any(_is_real_image(a) or a == "?" for a in _positional(sub_args)):
            return f"`docker {sub}` borraría la imagen real {REAL_IMAGE}"
        return None
    if sub in {"tag", "image tag"}:
        positional = _positional(sub_args)
        if len(positional) >= 2 and _is_real_image(positional[-1]):
            return f"`docker {sub}` sustituiría la imagen real {REAL_IMAGE}"
    return None


def _check_container_targets(sub, sub_args) -> str | None:
    targets = _positional(sub_args, with_value={"-t", "--time", "-s", "--signal"})
    if not targets:
        return None
    for target in targets:
        if not target.startswith(TEST_PREFIX):
            return (f"`docker {sub} {target}`: solo se pueden parar, borrar, matar o reiniciar "
                    f"contenedores {TEST_PREFIX}-… (el programador real es {REAL_PROJECT}-…)")
    return None


def _check_compose(args, env) -> str | None:
    project = env.get("COMPOSE_PROJECT_NAME")
    i = 0
    while i < len(args) and args[i].startswith("-"):
        option, has_value, value = args[i].partition("=")
        if option in {"-p", "--project-name"}:
            project = value if has_value else (args[i + 1] if i + 1 < len(args) else "")
        if has_value or option not in COMPOSE_GLOBAL_WITH_VALUE:
            i += 1
        else:
            i += 2
    sub = args[i] if i < len(args) else None
    if project and project.startswith(TEST_PREFIX):
        return None
    if sub is None or sub in READ_ONLY_COMPOSE:
        return None
    return (f"`docker compose {sub}` sobre el proyecto real (sin -p {TEST_PREFIX}-…); "
            "solo se permiten `docker compose logs` y `docker compose ps`")


def _option_values(args, names):
    values = []
    for i, arg in enumerate(args):
        option, has_value, value = arg.partition("=")
        if option in names:
            values.append(value if has_value else (args[i + 1] if i + 1 < len(args) else ""))
    return values


def _positional(args, with_value=frozenset()):
    result, i = [], 0
    while i < len(args):
        if args[i].startswith("-"):
            i += 2 if args[i] in with_value else 1
            continue
        result.append(args[i])
        i += 1
    return result


def _is_real_image(name: str) -> bool:
    return name in {REAL_IMAGE, f"{REAL_IMAGE}:latest", f"docker.io/library/{REAL_IMAGE}"}


# --- data/ --------------------------------------------------------------------

def _in_real_data(token: str, cwd: str) -> bool:
    if token == "?":
        return False
    value = token.partition("=")[2] if token.startswith("-") and "=" in token else token
    if not value or value.startswith("-"):
        return False
    path = os.path.normpath(os.path.join(cwd, os.path.expanduser(value)))
    return path == REAL_DATA or path.startswith(REAL_DATA + os.sep)


def _check_writes(name, args, cwd) -> str | None:
    in_data = [a for a in args if _in_real_data(a, cwd)]
    if name in WRITERS_ANY_ARG and (in_data or _in_real_data(".", cwd)):
        target = in_data[0] if in_data else "."
        return f"`{name}` sobre data/ ({target})"
    if name in WRITERS_LAST_ARG:
        positional = _positional(args)
        if positional and _in_real_data(positional[-1], cwd):
            return f"`{name}` escribe en data/ ({positional[-1]})"
    if name == "dd" and any(a.startswith("of=") and _in_real_data(a[3:], cwd) for a in args):
        return "`dd` escribe en data/"
    if name in {"sed", "gsed", "perl"} and any(a.startswith("-i") for a in args) and in_data:
        return f"`{name} -i` modifica un archivo de data/ ({in_data[0]})"
    if name == "sqlite3" and in_data and "-readonly" not in args:
        return f"`sqlite3` sobre data/ sin -readonly ({in_data[0]})"
    if name == "find" and in_data and any(a in {"-delete", "-exec", "-execdir"} for a in args):
        return "`find` con -delete/-exec sobre data/"
    if name == "git" and args and args[0] == "clean" and any(
            a.startswith("-") and not a.startswith("--") and ("x" in a or "X" in a) for a in args):
        return "`git clean -x` borraría data/ (está en .gitignore)"
    if name.startswith("python") and "-m" in args and not {"-h", "--help"} & set(args):
        module = args[args.index("-m") + 1] if args.index("-m") + 1 < len(args) else ""
        if module in {"src.ingestion", "src.ingestion.scheduled"}:
            dbs = _option_values(args, {"--db"})
            if not dbs or any(_in_real_data(db, cwd) for db in dbs):
                return f"`python -m {module}` escribiría en data/ (y llamaría a la API real)"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command") or ""
        reason = deny_reason(command, payload.get("cwd"))
    except Exception as exc:  # noqa: BLE001 — ante la duda, se bloquea
        reason = f"error interno del hook ({exc.__class__.__name__}: {exc})"
    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": MESSAGE.format(reason=reason),
            }
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
