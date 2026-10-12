# Design

## Context

Ver proposal.md (Why) y la spec `ingestion-container` para los requisitos.
Estado actual relevante:

- **La ingesta** (`python -m src.ingestion`):
  - solo usa la librería estándar;
  - acepta `--db`, `--url` y una opción oculta `--deadline`;
  - termina con 0 si guarda la captura, con 1 si falla y con 2 si un
    argumento es incorrecto (lo decide argparse);
  - si la corta una señal, el código lo pone la señal (130 con SIGINT, 143 o
    137 con `docker stop`).
- **Cómo guarda `storage.save_snapshot`:**
  - Si la base no existe, la crea en un temporal `<db>.tmp-<hex>` en la
    misma carpeta y la mueve con `os.replace`.
  - Si existe, escribe en una transacción `BEGIN IMMEDIATE` con el diario de
    SQLite en modo rollback (`prices.db-journal` junto a la base).
  - Por tanto, el usuario del contenedor necesita poder escribir en la
    carpeta, no solo en el archivo.
- **Ruta por defecto:** `storage.DEFAULT_DB_PATH` se calcula a partir de
  `__file__` y es `<proyecto>/data/prices.db`. Dentro de la imagen será
  `/app/data/prices.db`.
- **Señales:** la ingesta no instala ningún manejador de SIGTERM. Python
  solo convierte SIGINT en `KeyboardInterrupt`.
- **Tests actuales:**
  - bloquean la red externa en el proceso de pytest (`tests/conftest.py`);
  - simulan la API con `tests/http_server.py`, que escucha en `127.0.0.1`;
  - `tests/builders.py` genera respuestas de cualquier tamaño;
  - `tests/helpers.db_dump` abre la base en solo lectura;
  - `tests/fixtures/real_sample.json` solo tiene 4 estaciones.
- **Entorno de esta máquina:** Docker lo da OrbStack, con Compose v5.

## Goals / Non-Goals

**Goals:**
- Que la imagen y el servicio cumplan la spec sin cambiar el código de
  `src/ingestion/`.
- Que la mayor parte de la spec se compruebe con tests automáticos en el
  Mac. Esos tests nunca llaman a la API real ni tocan `data/prices.db` ni el
  `.env` del usuario.

**Non-Goals:**
- Imagen multiplataforma o publicada en un registro.
- Endurecimiento adicional del contenedor (sistema de archivos de solo
  lectura, limitar capacidades): se valorará en `add-vps-deployment`.

## Decisions

### 1. Imagen base `python:3.12-slim-bookworm`
- **Por qué esta imagen:** es oficial y pequeña. Trae los certificados raíz
  necesarios para conectar por HTTPS con el Ministerio y SQLite ≥ 3.24, que
  exige `storage`.
- **Alternativas descartadas:**
  - Alpine: usa otra libc y otras versiones de SQLite, y no aporta nada para
    un proceso de un minuto.
  - Distroless: no tiene shell, lo que complica depurar y la lista de
    comprobación.
- **Qué se copia:** solo `src/` → `/app/src` y `container/` → `/app/container`.
  No se instala nada con `pip`, porque la ingesta no tiene dependencias.
- **`WORKDIR /app`:** imprescindible. `python -m src.ingestion` busca el
  paquete `src` en la carpeta de trabajo, y la imagen base usa `/` por
  defecto, lo que daría «No module named src».
- **Variables de entorno:**
  - `PYTHONDONTWRITEBYTECODE=1`, porque el usuario de ejecución no puede
    escribir en `/app`;
  - `PYTHONUNBUFFERED=1`, para que la salida aparezca en orden en
    `docker compose run`.

### 2. Usuario por defecto en la imagen y usuario del host en Compose
- **Usuario de la imagen:**
  - se crea un usuario y grupo `app` con número 10001 y se declara
    `USER 10001:10001`, así que `docker run` sin Compose nunca es root;
  - `/app` y su contenido pertenecen a root y los demás solo pueden leerlos.
- **Usuario en Compose:**
  - el servicio fija `user: "${HOST_UID:?…}:${HOST_GID:?…}"`;
  - si alguna de las dos variables falta o está vacía, Compose se niega a
    ejecutar y muestra el mensaje que va tras `?`, que indica qué variable
    falta y remite al README;
  - así el proceso usa el UID/GID del usuario del host, y los archivos que
    cree en `./data` quedan a su nombre.
- **Alternativas descartadas:**
  - argumentos de construcción: obligan a reconstruir en cada máquina;
  - usuario fijo 1000: falla con el 1001 del escenario;
  - `chown` en el arranque: necesita root.
- **Por qué `HOST_UID`/`HOST_GID` y no `UID`/`GID`:**
  - bash define `UID` pero no la exporta, así que Compose la vería vacía;
  - unos nombres propios no suelen estar exportados en la terminal, que
    tendría prioridad sobre `.env`.
- **El archivo `.env`:**
  - va en `.gitignore` y en `.dockerignore`;
  - Compose lo lee de la carpeta del proyecto, la del `docker-compose.yml`;
  - el README explica cómo crearlo:
    `printf 'HOST_UID=%s\nHOST_GID=%s\n' "$(id -u)" "$(id -g)" > .env`.
- **`docker compose build` también necesita `.env`:** Compose interpola
  todo el archivo antes de construir. Se documenta.

### 3. Programa de arranque `container/entrypoint.py`, fuera de `src/ingestion/`
- **Dónde y por qué ese nombre:**
  - `ENTRYPOINT ["python", "/app/container/entrypoint.py"]`;
  - la carpeta se llama `container/` y no `docker/` para no chocar con el
    paquete `docker` de Python si algún día se instala, porque la raíz está
    en el `pythonpath` de los tests.
- **Qué hace, en orden:**
  1. Si el usuario o el grupo son 0, muestra «no se permite ejecutar como
     root» (o «…con el grupo root») y termina con código 2.
  2. Si algún argumento es `--db` o empieza por `--db=`, muestra que la base
     de datos no se puede cambiar en el contenedor y termina con código 2.
  3. Si no, fija la carpeta de trabajo en `/app` (`os.chdir`) y sustituye
     el proceso (`os.execv`) por
     `<sys.executable> -m src.ingestion --db /app/data/prices.db <argumentos>`.
     Usar `sys.executable` y fijar la carpeta explícitamente evita depender
     del `PATH` y del `WORKDIR` de la imagen.
- **Consecuencias del `execv`:**
  - el código de salida, la ayuda y los errores de argumentos son
    exactamente los de la ingesta;
  - ninguna comprobación hace peticiones: las dos primeras salen antes de
    lanzar la ingesta y `--help` sale antes de descargar.
- **Abreviaturas de `--db`:** argparse acepta abreviaturas, pero `--d` es
  ambigua con `--deadline` y argparse la rechaza con código 2. No hay otra
  abreviatura posible de `--db`.
- **Por qué en Python:**
  - se puede probar sin Docker, porque recibe `uid`, `gid` y `argv` como
    parámetros;
  - evita problemas de comillas con los argumentos;
  - los tests lo cargan por ruta (`importlib.util.spec_from_file_location`).
- **Por qué fuera de `src/ingestion/`:** así la ingesta no cambia.
- **Por qué se pasa `--db` aunque `DEFAULT_DB_PATH` ya apunte a
  `/app/data/prices.db`:** lo pidió el usuario, y deja la ruta explícita y a
  salvo de cambios futuros de ese valor por defecto.
- **Lo que verá el usuario y se documenta en el README:**
  - la ayuda sigue mostrando `--db` y `prog="python -m src.ingestion"`;
  - el resumen dice «Captura guardada en /app/data/prices.db», que es la
    ruta dentro del contenedor y corresponde a `./data/prices.db` del host.

### 4. `docker-compose.yml`
```yaml
services:
  ingest:
    build: .
    image: precios-gasolineras-ingest
    user: "${HOST_UID:?…}:${HOST_GID:?…}"
    init: true
    restart: "no"
    volumes:
      - type: bind
        source: ./data
        target: /app/data
        bind:
          create_host_path: false
```
- **`create_host_path: false`:** si `./data` no existe, Docker se niega a
  crearla, con el mensaje «bind source path does not exist: …/data», que
  basta para «indica que falta la carpeta». Hace falta la sintaxis larga:
  la corta crearía la carpeta, y en Linux quedaría a nombre de root.
- **`init: true`:** pone un pequeño init como proceso 1 que reenvía las
  señales.
  - Sin él, Python sería el proceso 1, el núcleo ignoraría SIGTERM y
    `docker stop` tardaría 10 s en matar con SIGKILL.
  - Con él, SIGTERM mata la ingesta enseguida. Como no hay manejador, el
    efecto es el mismo que SIGKILL: no se ejecuta `ROLLBACK` (ver decisión 5).
  - SIGINT (Ctrl+C) llega como `KeyboardInterrupt`.
- **`restart: "no"`:** lo deja explícito, aunque `run` nunca reinicia.
- **`image:`:** da un nombre fijo a la imagen. `run` la reutiliza si existe y
  solo construye si falta. Por eso el README pide `docker compose build`
  tras cada cambio.
- **Comando:** solo se usa `docker compose run --rm ingest`, que devuelve el
  código de salida del contenedor.

### 5. Integridad ante interrupciones
- **No hace falta código nuevo:** la escritura ya es atómica.
  - Base nueva: temporal + `os.replace`.
  - Base existente: una única transacción.
- **Si se corta durante la descarga:** no se ha escrito nada.
- **Si se corta durante el guardado:**
  - Con SIGINT, el `except BaseException` de `storage` hace `ROLLBACK`, o la
    transacción ya estaba confirmada.
  - Con SIGTERM (`docker stop`) o SIGKILL, el proceso muere sin `ROLLBACK`.
    Puede quedar `prices.db-journal`, un diario pendiente que SQLite usa
    para deshacer la transacción la próxima vez que se abre la base para
    escribir.
  - Si era la primera ejecución, queda un `prices.db.tmp-*` huérfano y no
    existe `prices.db`.
- **Restos que pueden quedar:** ninguno corrompe la base ni deja una captura
  a medias visible. Se documentan en el README como restos inofensivos.
- **En los tests:** una conexión de solo lectura no puede deshacer un diario
  pendiente. Por eso, tras un corte, los tests abren la base una vez en
  lectura y escritura y ejecutan una lectura
  (`SELECT count(*) FROM sqlite_master`), que es lo que hace que SQLite
  deshaga el diario, como haría la siguiente ingesta. Después usan
  `db_dump`.

### 6. `.dockerignore`
Se usan patrones `**/` para que valgan en cualquier carpeta:
```
.venv/
data/
tests/
openspec/
.env
**/*.db
**/*.db-journal
**/*.db.tmp-*
**/__pycache__/
.pytest_cache/
.git/
.claude/
.idea/
CLAUDE.md
requirements-dev.txt
```
- Además, el Dockerfile solo copia `src/` y `container/`.
- El `.dockerignore` evita que el resto se envíe a Docker, incluida la base
  de 4,3 MB.
- Los tests comprueban las dos cosas por separado.

### 7. Tests con Docker
- **Organización:**
  - viven en `tests/docker/` (con `__init__.py`) y llevan la marca `docker`,
    registrada en `pyproject.toml`;
  - se saltan si `docker info` falla;
  - `pytest -m "not docker"` los excluye.
- **Imágenes:**
  - un fixture de sesión construye `precios-gasolineras-ingest` una vez con
    `docker compose build`, desde el repo;
  - `HOST_UID`/`HOST_GID` se pasan como variables del subproceso, no con un
    `.env`, para no crear ni pisar el `.env` del repo;
  - las construcciones con contexto falso (tarea 3.4) y las
    reconstrucciones usan otras etiquetas (`precios-gasolineras-ingest:test-*`)
    y se borran al terminar.
- **Proyecto temporal por test:**
  - contiene una copia de `docker-compose.yml`, su propio `.env` y su propia
    `data/`;
  - se lanza con `docker compose -f <tmp>/docker-compose.yml run --rm --name
    <único> ingest …`;
  - las rutas relativas (`./data`, `.env`) se resuelven contra esa carpeta;
  - la imagen ya existe, así que `run` no construye;
  - `data/prices.db` real nunca se monta.
- **Reconstrucción** («Los datos sobreviven al contenedor y a la imagen»):
  el proyecto temporal recibe también `Dockerfile`, `.dockerignore`, `src/`
  y `container/`, y se reconstruye ahí con su propio `.env` y la etiqueta
  `precios-gasolineras-ingest:test-rebuild`. Para eso, la copia de
  `docker-compose.yml` sustituye `image:` por esa etiqueta.
- **Entorno controlado:** el subproceso de `docker` recibe solo `PATH`,
  `HOME`, las variables `DOCKER_*` que existan y las que fije el test.
- **Proxy:** se pasan `-e NO_PROXY=host.docker.internal,127.0.0.1` y
  `-e no_proxy=…` (urllib da prioridad a la variable en minúsculas) por si el
  cliente Docker tiene proxies configurados.
- **Sin TTY:** `run_ingest` usa siempre `docker compose run -T`, para que la
  salida normal y la de errores no se mezclen.
- **Sin API real:** todo lanzamiento pasa por un helper que exige `--url` y
  solo admite tres tipos de destino:
  - el servidor local vía `host.docker.internal`, que en OrbStack y Docker
    Desktop llega a los servicios del Mac que escuchan en `127.0.0.1`;
  - un puerto cerrado del propio contenedor (`http://127.0.0.1:9/`);
  - un nombre `.invalid`, que nunca se resuelve.
- **Contar peticiones:**
  - los casos que no deben hacer ninguna (`.env` incompleto, root, `--db`,
    `--help`, `./data` ausente) también pasan `--url` al servidor local y
    comprueban que recibe 0;
  - el conteo sirve también para «una única petición» y para «no se
    reinicia»: 1 petición y ningún contenedor restante.
- **Usuario efectivo (501:20):** se observa con
  `docker compose run --rm --entrypoint id ingest`. En macOS el dueño de los
  archivos no es fiable.
- **Interrupciones** (se recuperan siempre como en la decisión 5):
  - Durante la descarga: el servidor local responde en modo `HANG`. El corte
    se hace con `docker stop <nombre>` en un test y con
    `docker kill --signal INT <nombre>` en otro.
  - Durante el guardado:
    - el test genera con `tests/builders.py` una respuesta de unas 10 000
      estaciones, cada una con precios, y la sirve desde el servidor local;
    - `LocalServer` gana un aviso opcional de «respuesta enviada por
      completo» por ruta (un `threading.Event` que se activa cuando
      termina el `write`, es decir, con los datos ya entregados al sistema,
      no necesariamente recibidos por el cliente), sin cambiar su
      comportamiento actual;
    - variante `docker stop`: tras ese aviso, el test vigila cada pocos
      milisegundos (con tiempo límite) hasta que aparece
      `data/prices.db-journal` en el host, y entonces lanza `docker stop`.
      Así el corte cae en el guardado de forma determinista;
    - variante SIGINT: tras el aviso se corta con
      `docker kill --signal INT` a varios intervalos;
    - en cada repetición, la base tiene una o dos capturas completas.
  - Prueba de que un corte cayó de verdad durante el guardado (solo en la
    variante `docker stop`):
    - basta con que exista `prices.db-journal` justo después del corte, antes
      de recuperar la base. En modo rollback, SQLite crea ese archivo al
      escribir y lo borra al confirmar, y SIGTERM mata sin `ROLLBACK`;
    - el test falla si ninguna repetición de `docker stop` lo deja;
    - «código ≠ 0 con la respuesta ya enviada» no sirve como prueba: también
      se da si el corte llega mientras se lee y se analiza el JSON, antes de
      guardar.
  - La variante SIGINT no tiene una prueba fiable, porque su `ROLLBACK`
    borra el diario. Solo se le comprueba que la base tiene una o dos
    capturas completas.
- **Contenido de la imagen:** se lanza con `--entrypoint`, sin ejecutar la
  ingesta, para comprobar:
  - `python --version`;
  - `python -c "import pytest"`;
  - `find / -name prices.db` y `find / -name .env`;
  - `ls /app`;
  - `id -u` e `id -g`.
- **Contexto de construcción:**
  - en una carpeta temporal se copian `src/`, `container/`, `Dockerfile` y
    `.dockerignore`;
  - se añaden `tests/`, `.venv/`, `openspec/`, `data/prices.db`, `.env` y un
    `src/x.db`, todos falsos;
  - se construye una imagen auxiliar `FROM python:3.12-slim-bookworm`
    (ya descargada) + `COPY . /ctx` con el mismo `.dockerignore`, y se lista
    `/ctx`;
  - para «Cambio solo en tests», se construye dos veces la imagen real desde
    esa carpeta, cambiando solo `tests/`, y se comparan la lista de archivos
    de `/app` y sus hashes.
- **Escenarios solo de Linux:** usuario 1001, dueño de los archivos, carpeta
  sin permiso y base a nombre de root. No se automatizan: van a la lista de
  comprobación manual (decisión 8).

### 8. Comprobación manual y ejecución real documentadas
`docs/container-checks.md` (en español) contiene:
- **Lista de comprobación en una máquina Linux de OrbStack**
  (`orb create ubuntu ingest-check`):
  - instalar Docker Engine y Compose;
  - crear el usuario `deploy` 1001:1001 y añadirlo al grupo `docker`, para
    que pueda usar Docker sin `sudo`;
  - copiar el proyecto (sin `data/`) y crear su `.env`;
  - recorrer los escenarios de «Escritura en ./data en un host Linux», con
    el comando exacto y el resultado esperado de cada uno (`ls -ln data/`,
    código de salida);
  - borrar la máquina al terminar.
- **Cómo se evita la API real en esa máquina:**
  - en la propia máquina se sirve `tests/fixtures/` con
    `python3 -m http.server <puerto> --bind 0.0.0.0`;
  - se lanza la ingesta con
    `--url http://<IP de la máquina>:<puerto>/valid_two_stations.json`;
  - la IP se obtiene con `hostname -I | awk '{print $1}'`, y el contenedor
    llega a ella por la red de Docker sin configuración extra;
  - no hace falta `host.docker.internal` ni tocar `docker-compose.yml`.
- **Ejecución real:**
  - una única `docker compose run --rm ingest` contra la API del Ministerio,
    para comprobar el HTTPS desde la imagen;
  - se hace sobre una copia de `data/` en un proyecto aparte, no sobre la
    real;
  - se anotan la fecha, el código de salida y el resumen;
  - es una sola petición.

## Risks / Trade-offs

- **[Riesgo] `host.docker.internal` no llega al servidor local de los
  tests** (escucha en `127.0.0.1`).
  → La tarea 1.1 lo comprueba. Si falla, se añade a `LocalServer` un
  parámetro opcional de dirección de escucha, que solo usan los tests de
  Docker, sin cambiar el valor por defecto.
  - **Resultado de la tarea 1.1 (2026-10-12, OrbStack 29.4.0, Compose
    v5.1.2):**
    - (a) Un contenedor llega por `host.docker.internal` a un servidor del
      Mac que escucha en `127.0.0.1`. No hace falta cambiar `LocalServer`.
    - (b) Con `create_host_path: false` y sin `./data`, `run` termina con
      código 1 y el mensaje «bind source path does not exist: <ruta>/data».
      La carpeta no se crea.
    - (c) Con `-f <ruta absoluta>` lanzado desde otra carpeta que tiene su
      propio `.env`, Compose usa el `.env` del proyecto. Sin `.env`, falla
      con «required variable HOST_UID is missing a value: …» y código 1.
      Las variables del entorno sí tienen prioridad sobre `.env`
      (`HOST_UID=0` exportado llega al contenedor), así que hace falta el
      entorno mínimo de los tests.
    - (d) `~/.docker/config.json` no tiene proxies en esta máquina. Se pasan
      `NO_PROXY`/`no_proxy` igualmente.
    - Además: `run --rm` deja creada la red `<proyecto>_default`. Los tests
      hacen `docker compose down` al terminar cada proyecto temporal.
- **[Compromiso] El fixture de sesión reconstruye la imagen
  `precios-gasolineras-ingest` del usuario** con el código actual.
  → Es inofensivo: es la misma imagen que daría `docker compose build`. Se
  indica en un comentario del fixture.
- **[Riesgo] El contenedor sí tiene red real:** el bloqueo de `conftest.py`
  solo afecta al proceso de pytest.
  → El helper rechaza cualquier `--url` que no sea de los tres tipos
  permitidos. Hay un test unitario de esa comprobación.
- **[Riesgo] Los tests con Docker son lentos** (construcciones e
  interrupciones repetidas).
  → Una construcción por sesión, la marca `docker` para excluirlos y pocas
  repeticiones en los tests de interrupción.
- **[Compromiso] El mensaje de «falta `./data`» es el de Docker**, en
  inglés.
  → Se acepta porque menciona la ruta. El README explica qué significa.
- **[Compromiso] `docker compose build` también exige `.env`.**
  → Se documenta. A cambio, `run` falla con un mensaje claro si falta.
- **[Riesgo] `--d …`.**
  → argparse lo rechaza por ambiguo, sin hacer ninguna petición. Lo cubre un
  test unitario del programa de arranque.
- **[Riesgo] SIGTERM o SIGKILL dejan restos (`-journal`, `.tmp-*`).**
  → No afectan a la integridad (decisión 5). Documentado.

## Migration Plan

- **No hay migración:** la estructura de la base no cambia. El histórico se
  conserva porque el contenedor abre el mismo `data/prices.db` del host con
  el mismo código de guardado.
- **Puesta en marcha en el Mac:**
  1. Copiar `data/prices.db` a mano (recomendación del README).
  2. Crear `.env`.
  3. `docker compose build`.
  4. `docker compose run --rm ingest`.
- **Vuelta atrás:** si algo falla, se lanza la ingesta sin Docker como hasta
  ahora (`.venv/bin/python -m src.ingestion`), sobre el mismo archivo.
