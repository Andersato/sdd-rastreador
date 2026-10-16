"""Programa de arranque del servicio `scheduler`.

Escribe el crontab (una comprobación cada hora en el minuto 17), lanza
supercronic y una comprobación inmediata, y se queda vigilándolos:

- Recoge a los hijos que terminan y, cuando ya no le queda ninguno, sale con
  el código de supercronic (si muere por su cuenta, Docker reinicia el
  servicio). Espera también a la comprobación de arranque, que no es trabajo
  de supercronic, para que no muera a mitad del guardado.
- Al recibir SIGTERM o SIGINT (`docker compose stop`) manda SIGTERM a todos
  los procesos del contenedor. supercronic lanza cada trabajo en su propio
  grupo de procesos y, al pararse, espera a que terminen sin avisarles: sin
  esto, una ingesta en curso seguiría hasta que Docker la matase. La
  ingesta trata SIGTERM como Ctrl+C y no deja nada a medias.
"""

import os
import signal
import subprocess
import sys
from datetime import datetime, timezone

from src.ingestion.scheduled import madrid_time

CRONTAB_PATH = "/tmp/crontab"
CHECK_COMMAND = "python /app/container/check.py"
CRON_MINUTE = 17  # nunca :00, la hora punta de peticiones a la API
SUPERCRONIC = ["/usr/local/bin/supercronic", "-passthrough-logs", "-quiet"]


def crontab() -> str:
    return f"{CRON_MINUTE} * * * * {CHECK_COMMAND}\n"


def startup_line(env: dict[str, str], now: datetime) -> str:
    interval = env.get("CAPTURE_INTERVAL_HOURS")
    configured = repr(interval) if interval else "6 (por defecto)"
    return (f"{madrid_time(now)} · programador en marcha: comprobación ahora y cada hora en el "
            f"minuto {CRON_MINUTE}; intervalo configurado: {configured}")


def stop_all(signum, frame, kill=os.kill) -> None:
    # En Linux, kill(-1) llega a todos los procesos del contenedor salvo al
    # init (PID 1) y a este mismo.
    try:
        kill(-1, signal.SIGTERM)
    except ProcessLookupError:
        pass


def main(
    env: dict[str, str],
    popen=subprocess.Popen,
    wait=os.wait,
    install=signal.signal,
    platform=sys.platform,
    now=None,
) -> int:
    # kill(-1) fuera de un contenedor alcanzaría a todos los procesos del
    # usuario: este programa solo se ejecuta dentro de la imagen (Linux).
    if platform != "linux":
        print("Error: el programador solo se ejecuta dentro del contenedor", file=sys.stderr)
        return 2
    with open(CRONTAB_PATH, "w") as out:
        out.write(crontab())
    print(startup_line(env, now or datetime.now(timezone.utc)), flush=True)
    install(signal.SIGTERM, stop_all)
    install(signal.SIGINT, stop_all)
    cron = popen([*SUPERCRONIC, CRONTAB_PATH])
    popen([sys.executable, "/app/container/check.py"])  # comprobación de arranque
    # Al parar, supercronic sale sin esperar a la comprobación de arranque (no
    # es trabajo suyo): se espera a todos los hijos antes de salir, porque al
    # terminar el contenedor se matarían a mitad del ROLLBACK (D12).
    code = None
    while True:
        try:
            pid, status = wait()
        except ChildProcessError:
            return 1 if code is None else code
        if pid == cron.pid:
            code = os.waitstatus_to_exitcode(status)
            if code < 0:  # muerto por una señal: 128 + número, como el shell (D8)
                code = 128 - code


if __name__ == "__main__":
    sys.exit(main(dict(os.environ)))
