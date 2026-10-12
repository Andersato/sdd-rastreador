# Tasks

## 1. Comprobaciones previas e infraestructura de tests con Docker

- [x] 1.1 Comprobar a mano en OrbStack, y anotar el resultado en design.md (Riesgos):
  - (a) un contenedor alcanza un servidor del Mac que escucha en `127.0.0.1` a través de `host.docker.internal`;
  - (b) Compose respeta `create_host_path: false`: sin `./data` falla y no la crea;
  - (c) con `docker compose -f <ruta absoluta>/docker-compose.yml` lanzado desde otra carpeta, Compose lee el `.env` de la carpeta del proyecto y no el de la carpeta actual;
  - (d) si `~/.docker/config.json` tiene proxies, `-e NO_PROXY=…` los anula.

  Si (a) falla, añadir a `tests/http_server.py` un parámetro opcional de dirección de escucha, sin cambiar el valor por defecto, y verificar que `pytest tests/unit/test_http_server.py` sigue pasando
- [x] 1.2 Registrar la marca `docker` en `pyproject.toml` y crear `tests/docker/__init__.py` y `tests/docker/conftest.py`, con salto automático si `docker info` falla. Verificar que con Docker parado `pytest -m docker` sale como «skipped» y que `pytest -m "not docker"` sigue pasando entero
- [x] 1.3 Crear `tests/docker/helpers.py` (design, decisión 7) con:
  - el proyecto temporal: copia de `docker-compose.yml`, `.env` con el UID/GID indicado y `data/`, y opcionalmente `Dockerfile`, `.dockerignore`, `src/` y `container/` para reconstruir;
  - un entorno mínimo para el subproceso;
  - `run_ingest(...)`, con `-T`, `--name` único, `-e NO_PROXY=…` y `-e no_proxy=…`, que exige `--url` y solo admite el servidor local, `http://127.0.0.1:9/` o un nombre `.invalid`;
  - la comprobación de que no queda contenedor;
  - una función que abre la base en lectura y escritura y ejecuta `SELECT count(*) FROM sqlite_master`, para que SQLite deshaga un diario pendiente antes de `db_dump`.

  Verificar con tests unitarios del helper, sin Docker, que:
  - lanzar sin `--url` o con otra URL (p. ej. la del Ministerio) falla antes de llamar a Docker;
  - el entorno no hereda `HOST_UID`, `HOST_GID` ni variables de proxy.
- [x] 1.4 Añadir a `LocalServer` (`tests/http_server.py`) un aviso opcional por ruta de «respuesta enviada por completo» (un `threading.Event` que se activa cuando termina el `write`, con los datos entregados al sistema, no necesariamente recibidos por el cliente), sin cambiar el comportamiento actual (design, decisión 7). Verificar con un test nuevo en `tests/unit/test_http_server.py` que el aviso no está activo antes de la petición y sí lo está cuando el cliente ha leído el cuerpo entero, y que el resto de ese archivo sigue pasando

## 2. Programa de arranque

- [x] 2.1 Crear `container/entrypoint.py` (design, decisión 3; requisitos «Usuario del host configurado y distinto de root» y «Argumentos adicionales del comando»). Recibe `uid`, `gid` y `argv` como parámetros y:
  - rechaza el usuario 0 y el grupo 0, cada uno con su mensaje, con código 2;
  - rechaza `--db` y `--db=…`;
  - si no, fija la carpeta de trabajo en `/app` y hace `execv` de `<sys.executable> -m src.ingestion --db /app/data/prices.db <argumentos>`.

  Verificar con `tests/unit/test_entrypoint.py`, que carga el script por ruta:
  - usuario 0, grupo 0, `--db x` y `--db=x` → código 2, mensaje esperado y sin `exec`;
  - `--url U --help` → `exec` con `--db /app/data/prices.db` y los argumentos en el mismo orden;
  - `--d x` → se pasa tal cual, porque lo rechaza argparse por ambiguo.

## 3. Imagen y contexto de construcción

- [x] 3.1 Crear `Dockerfile` (design, decisiones 1 y 2; requisitos «Imagen con Python 3.12 sin archivos de desarrollo» y «Ejecución con un usuario sin privilegios»):
  - imagen base `python:3.12-slim-bookworm`;
  - `WORKDIR /app`;
  - usuario `app` 10001:10001;
  - `COPY` solo de `src/` y `container/`;
  - `PYTHONDONTWRITEBYTECODE=1` y `PYTHONUNBUFFERED=1`;
  - `ENTRYPOINT` hacia `/app/container/entrypoint.py`.

  Verificar que `docker build .` termina sin errores y que `docker run --rm <imagen> --help` muestra la ayuda de la ingesta, con código 0 y sin petición
- [x] 3.2 Crear `.dockerignore` con la lista de design (decisión 6; requisito «Contexto de construcción sin archivos ajenos a la ingesta») y añadir `.env` a `.gitignore`. Verificar con `git check-ignore .env`
- [x] 3.3 Tests de la imagen en `tests/docker/test_image.py` (requisitos «Imagen con Python 3.12…» y «Ejecución con un usuario sin privilegios»; escenario «Configuración local fuera de la imagen»), lanzando con `--entrypoint` y sin ejecutar la ingesta:
  - Python 3.12.x;
  - `import pytest` falla;
  - no hay ningún `prices.db` ni `.env` en toda la imagen, ni ningún `*.db` en `/app`;
  - no existen `tests/`, `.venv/`, `openspec/` ni `data/` en `/app`;
  - sin Compose, `id -u` e `id -g` son distintos de 0.

  Verificar que pasan con `pytest -m docker tests/docker/test_image.py`
- [x] 3.4 Tests del contexto de construcción en `tests/docker/test_build_context.py` (requisito «Contexto de construcción…»). Usan una carpeta temporal con `data/prices.db`, `.env`, `.venv/`, `tests/`, `openspec/` y `src/x.db` falsos, y etiquetas `:test-*` que se borran al terminar. Comprueban que:
  - la imagen auxiliar `FROM python:3.12-slim-bookworm` + `COPY . /ctx` no contiene ninguno de esos archivos;
  - dos construcciones que solo cambian `tests/` dan los mismos archivos y hashes en `/app`.

  Verificar que pasan

## 4. Servicio de Compose

- [x] 4.1 Crear `docker-compose.yml` según design (decisión 4; requisitos «Lanzamiento único…», «Base de datos en la carpeta ./data del host», «Carpeta ./data inexistente» y «Usuario del host configurado…»). Verificar que `docker compose config` no da errores con un `.env` válido
- [x] 4.2 Tests en `tests/docker/test_compose_user.py` (requisitos «Usuario del host configurado…» y «Ejecución con un usuario sin privilegios»):
  - sin `.env`, con `.env` sin `HOST_UID` y con `.env` sin `HOST_GID` → código ≠ 0, un mensaje que nombra la variable que falta, 0 peticiones y `data/` igual;
  - `HOST_UID=0` → código ≠ 0, mensaje de root, 0 peticiones y `data/` igual;
  - `HOST_UID=1001` y `HOST_GID=0` → código ≠ 0, mensaje de grupo root, 0 peticiones y `data/` igual;
  - con el UID/GID del Mac (p. ej. 501:20), `docker compose run --rm --entrypoint id ingest` muestra ese UID/GID.

  Verificar que pasan
- [x] 4.3 Tests en `tests/docker/test_compose_run.py` (requisito «Lanzamiento único…»), con fixtures de `tests/fixtures/` y `data/` temporal:
  - `valid_two_stations.json` → código 0, resumen mostrado, 1 petición y ningún contenedor restante;
  - `with_warnings.json` → código 0 y aviso mostrado;
  - HTTP 503 → mismo código que la ingesta (≠ 0), 1 sola petición, ningún contenedor restante (no se reinicia) y base igual;
  - puerto cerrado (`http://127.0.0.1:9/`) y nombre `.invalid` → código ≠ 0 y base igual;
  - `lista_empty.json` → código ≠ 0 y nada guardado.

  Verificar que pasan
- [x] 4.4 Tests en `tests/docker/test_compose_args.py` (requisito «Argumentos adicionales del comando»):
  - `--url` al servidor local → 1 petición a ese servidor y la captura en `data/` del proyecto temporal;
  - `--help` → código 0, 0 peticiones y `data/` igual;
  - `--db /tmp/otra.db` y `--db=/tmp/otra.db` → código ≠ 0, mensaje, 0 peticiones, ninguna base creada y `data/` igual.

  Verificar que pasan
- [x] 4.5 Tests en `tests/docker/test_compose_data.py` (requisitos «Base de datos en la carpeta ./data del host», incluido «Funciona igual en macOS», y «Carpeta ./data inexistente»):
  - base con 1 captura → 2 capturas, la primera intacta (`db_dump`), y ningún otro archivo en `data/`;
  - `data/` vacía → `prices.db` con 1 captura y 2 estaciones, y ningún otro archivo;
  - ingesta, reconstrucción en el proyecto temporal (design, decisión 7) e ingesta → 2 capturas;
  - versión de estructura 7 → código ≠ 0 y base igual;
  - lanzado con `-f <ruta absoluta>` desde otra carpeta temporal → la captura va al proyecto y no se crea nada en la carpeta de lanzamiento;
  - sin `data/` → código ≠ 0, mensaje con la ruta, 0 peticiones y `data/` sigue sin existir.

  Verificar que pasan
- [x] 4.6 Tests en `tests/docker/test_compose_interrupt.py` (escenarios de interrupción; design, decisiones 5 y 7). Antes de comprobar la base, recuperan siempre el diario pendiente:
  - servidor en modo `HANG`, cortado con `docker stop` y con `docker kill --signal INT` → código ≠ 0 y solo la primera captura, intacta;
  - respuesta generada con `tests/builders.py` (unas 10 000 estaciones, cada una con precios), cortada con `docker stop` en cuanto aparece `data/prices.db-journal` en el host (vigilado cada pocos milisegundos, con tiempo límite, tras el aviso de «respuesta enviada» de la tarea 1.4) y con `docker kill --signal INT` a varios intervalos tras ese aviso → en cada repetición, una o dos capturas completas, con los precios de cada captura iguales a los de su respuesta;
  - en la variante `docker stop`, `prices.db-journal` debe seguir existiendo justo después del corte, antes de recuperar la base (prueba de que cayó durante el guardado); si el diario no aparece antes del tiempo límite, el test falla. La variante SIGINT solo comprueba las capturas completas.

  Verificar que pasan

## 5. Documentación

- [x] 5.1 Añadir al `README.md` la sección de Docker:
  - requisitos (Docker con Compose v2);
  - crear `.env` con `HOST_UID`/`HOST_GID` y la carpeta `./data`;
  - recomendación de copiar `data/prices.db` antes de la primera ejecución;
  - `docker compose build`, que necesita `.env` y hay que repetir tras cada cambio del código;
  - `docker compose run --rm ingest` y argumentos admitidos (`--url` y `--help` sí, `--db` no);
  - código de salida;
  - que `/app/data/prices.db` del resumen es `./data/prices.db` del host;
  - que la ayuda muestra `--db` aunque no se admita en el contenedor;
  - qué significa el error de Docker «bind source path does not exist»;
  - restos inofensivos tras un corte (`-journal`, `.tmp-*`).

  Verificar ejecutando los comandos del README tal como están escritos, sobre una copia del proyecto con `data/` vacía y `--url` hacia un servidor local
- [x] 5.2 Escribir `docs/container-checks.md` (design, decisión 8):
  - lista de comprobación en una máquina Linux de OrbStack (`orb create ubuntu ingest-check`), incluido el paso de añadir `deploy` al grupo `docker`, con el servidor local en `0.0.0.0` y `--url http://<IP de la máquina>:<puerto>/valid_two_stations.json`;
  - comandos y resultado esperado de «Usuario del host con número distinto de 1000», «Base existente en Linux», «Carpeta sin permiso de escritura» y «Base de datos a nombre de otro usuario»;
  - procedimiento de la ejecución real única por HTTPS, sobre una copia de `data/`.

  Verificar que cada escenario de esos requisitos tiene su paso

## 6. Verificación final

- [x] 6.1 Ejecutar `pytest` completo (con Docker en marcha) y `pytest -m "not docker"`. Verificar que todo pasa y que `data/prices.db` y `.env` reales (si existe) no han cambiado (mismo tamaño, fecha y hash antes y después)
- [x] 6.2 Recorrer la lista de comprobación de Linux en OrbStack y anotar el resultado en `docs/container-checks.md`. Verificar que todos los escenarios dan el resultado esperado
- [ ] 6.3 Hacer la ejecución real única por HTTPS sobre una copia de `data/` y anotar la fecha, el código de salida y el resumen en `docs/container-checks.md`. Verificar el código 0 y la captura nueva en la copia
