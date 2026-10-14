# Design

## Context

Ver proposal.md (Why y Decisiones tomadas) y las tres specs delta. Estado
actual relevante:

- `src/ingestion/__main__.py` hace en una sola función: argumentos →
  descarga → parseo → guardado → resumen impreso. Errores controlados
  (`IngestionError`) → código 1.
- `storage.save_snapshot` escribe todo o nada; si la base no existe, la crea
  en un temporal `prices.db.tmp-<aleatorio>` y la renombra con `os.replace`.
  Por eso el bloqueo no puede ir sobre `prices.db`.
- `container/entrypoint.py` rechaza root y `--db`, y hace `execv` de la
  ingesta con `--db /app/data/prices.db`.
- `docker-compose.yml` tiene un único servicio `ingest` (`init: true`,
  `restart: "no"`, bind de `./data` sin crearla).
- Los tests de Docker trabajan sobre una copia temporal del proyecto y solo
  lanzan la ingesta con `--url` hacia `host.docker.internal` (servidor local).

## Goals / Non-Goals

**Goals:**
- Que la decisión "¿toca?" y la ingesta se ejecuten en un único proceso que
  tiene el bloqueo desde el principio hasta el final.
- Que toda la lógica nueva (bloqueo, 80 %, "¿toca?", formato de mensajes)
  viva en `src/ingestion/` y se pruebe con pytest sin Docker y con un reloj
  inyectado. Docker solo aporta el cron, la zona horaria y el arranque.
- Que el `ingest` manual siga igual, salvo los dos códigos de salida nuevos.

**Non-Goals:**
- Implementar nuestra propia planificación: los disparos horarios y los
  cambios de hora son cosa de supercronic.
- Probar de forma automática el paso real de las horas (esperar a :17) o los
  cambios de hora en el contenedor: se prueba la lógica con reloj inyectado y
  el resto se verifica a mano.
- Cambiar la estructura de la base de datos.

## Decisions

### D1. Bloqueo: `flock` sobre la carpeta de la base

Nuevo módulo `src/ingestion/lock.py` con un context manager
`data_dir_lock(folder)`: `os.open(folder, O_RDONLY)` +
`fcntl.flock(fd, LOCK_EX | LOCK_NB)`. Si está cogido lanza `IngestionBusy`
(nuevo `IngestionError`) sin esperar. Se libera al cerrar el descriptor o al
morir el proceso (también con `kill -9`), y no crea ningún archivo.

- La CLI crea la carpeta si no existe (como hasta ahora hacía el guardado) y
  coge el bloqueo **antes de la descarga**, así la segunda ingesta no hace
  ninguna petición. Para no cambiar lo que se ve hoy (lo fijan los tests de
  `test_cli_invalid.py` y `test_cli.py`), si la ingesta falla **antes** de
  guardar se quitan las carpetas que se crearon y siguen vacías; si falla el
  guardado, la carpeta queda, como antes (la creaba el guardado).
- Si `os.open` de la carpeta falla por otro motivo (p. ej. `EACCES`), es un
  `StorageError` controlado (código 1) con el texto "no se ha podido crear o
  escribir la base de datos", no una excepción sin capturar. Solo pasa con
  una carpeta sin permiso de lectura: el escenario "Carpeta sin permiso de
  escritura" de `ingestion-container` (carpeta legible) lo sigue cubriendo
  el error del guardado, como hasta ahora.
- Funciona entre contenedores que comparten `./data` porque todos corren en
  el mismo núcleo Linux (la máquina virtual de OrbStack o el VPS). Entre
  macOS y la máquina virtual no se comparte: de ahí la exclusión de `.venv`
  + contenedor (decisión 7).
- Alternativas descartadas (decisión del usuario): `fcntl` sobre `prices.db`
  (interfiere con los bloqueos de SQLite y el archivo no existe en la primera
  ejecución, y `os.replace` lo sustituye); archivo `.lock` en `./data`
  (rompe "en ./data solo queda prices.db" y puede quedar huérfano).

### D2. La comprobación y la ingesta en un único proceso

Se separa `__main__.main` en:
- `run_ingestion(db_path, url, deadline_s, now, accept_short) -> IngestionResult`:
  descarga, parseo y guardado; la comparación del 80 % se hace dentro del
  guardado (D4). **No** coge el bloqueo:
  lo exige al llamante (se documenta en el docstring).
- `main(argv)`: argumentos → carpeta → `data_dir_lock` → `run_ingestion` →
  imprime el resumen como hoy.

Nuevo módulo `src/ingestion/scheduled.py` (`python -m src.ingestion.scheduled`)
para una comprobación: valida la configuración, coge el bloqueo, lee la
última captura en solo lectura, decide y, si toca, llama a `run_ingestion`
dentro del mismo bloqueo. Cada comprobación es un proceso lanzado por
supercronic: si falla o se cuelga, el programador (supercronic) sigue vivo.

Alternativa descartada: que la comprobación lance `python -m src.ingestion`
como subproceso. Habría que pasarle el bloqueo heredando el descriptor y
evitar que lo vuelva a coger; es más frágil y no aporta aislamiento real.

### D3. Lectura de la última captura sin modificar nada

`storage.read_last_snapshot(db_path) -> LastSnapshot | None` (instante de
descarga y nº de estaciones con precio de la captura con mayor `id`). Solo
la usa la comprobación:
- Si `prices.db` no existe → `None`, sin abrir nada (abrir crearía el
  archivo).
- Abre con `db_path.resolve().as_uri() + "?mode=ro"` y `uri=True` (así no
  se rompe con `?`, `#` o `%` en la ruta), `timeout=1`. Comprueba `user_version`
  (0 o 1; otro → `StorageError` "versión no compatible"). Sin tabla de
  capturas o sin filas → `None`.
- Nº de estaciones: `COUNT(DISTINCT station_id) FROM prices WHERE snapshot_id = ?`.
- `sqlite3.DatabaseError` (archivo que no es una base, base ocupada) →
  `StorageError` "no se ha podido leer la base".
- **Diario pendiente** (escenario "Diario pendiente de una ingesta
  cortada", confirmado por el usuario): una conexión de solo lectura no
  puede deshacer un diario pendiente y falla con `SQLITE_READONLY_ROLLBACK`
  (código extendido 776, `exc.sqlite_errorcode`). Ese error, y no que exista
  el archivo `prices.db-journal`, lanza `InterruptedIngestion`, y la
  comprobación considera que **toca**: lo dice en el log y la ingesta, que
  abre en lectura-escritura, lo deshace como hoy. Mirar solo si existe el
  archivo haría que un diario vacío o no pendiente provocara una captura en
  cada hora. Alternativas descartadas: tratarlo como "base ilegible"
  (sin petición en cada comprobación hasta una ingesta manual) y abrir en
  lectura-escritura en la comprobación (modificaría `./data`).

La ingesta **no** usa esta función: lee la referencia del 80 % con su
conexión de escritura (D4), para seguir recuperándose sola tras un guardado
interrumpido.

### D4. Regla del 80 % con enteros

- Nuevas = nº de `station_id` distintos en `snapshot.prices` (las estaciones
  sin ningún precio válido no tienen filas).
- Sin referencia o referencia 0 → no se compara.
- Corta si `nuevas * 10 < referencia * 8` (sin `float`).
- Porcentaje truncado a décimas: `nuevas * 1000 // referencia` → `"79,9 %"`.
  Miles con punto: `f"{n:,}".replace(",", ".")`. Funciones en
  `src/ingestion/formatting.py`.
- La referencia (la captura de mayor `id`, como en D3) se lee en
  `storage._write`, con la conexión de escritura y dentro de la transacción
  `BEGIN IMMEDIATE` (que deshace un diario pendiente): **después de
  `_ensure_schema`** (comprobación de versión y creación de tablas) y
  **antes del `INSERT` de la captura**. Así una base de versión desconocida
  da siempre "versión de base de datos no compatible", y una base existente
  sin tablas (versión 0) se trata como sin referencia. Si la respuesta es
  corta y no se acepta, se lanza el error y la transacción hace ROLLBACK.
  Escenario "Ingesta tras un guardado interrumpido".
- `save_snapshot(snapshot, db_path, downloaded_at, accept_short=False)`:
  la regla se aplica dentro del guardado; si se acepta una respuesta corta,
  `SaveResult` lleva un campo nuevo `short_response: ShortResponse | None`
  (nuevas, referencia), con el que `run_ingestion` crea el aviso en
  `notices`.
- Corta sin `--accept-short-response` → `ShortResponseError` (nuevo
  `IngestionError`), código 4, sin guardar nada. Texto exacto:
  `Error: respuesta sospechosamente corta: 9.000 estaciones con precio frente a 12.000 de la última captura (75,0 %); no se ha guardado. Si es correcta, guárdala con --accept-short-response`.
- Con la opción → se guarda y se añade un aviso de respuesta aceptada que
  cuenta en "Avisos". `IngestionWarning` y `format_warning` están pensados
  para "campo con valor no válido"; en lugar de forzarlos, el resultado lleva
  una lista aparte `notices` y el resumen imprime
  `Avisos: <parser + notices>` y cada aviso con su propio texto. Texto exacto
  del aviso: `Aviso: respuesta corta aceptada con --accept-short-response: 9.000 estaciones con precio frente a 12.000 de la última captura (75,0 %)`.

### D5. Códigos de salida de la ingesta

0 correcto; 1 error (como hoy); 2 lo reservan argparse y el programa de
arranque; **3** otra ingesta en curso; **4** respuesta corta rechazada. La
spec solo exige "distinto de 0"; los códigos se documentan en el README para
quien quiera automatizar algo encima.

### D6. Decisión "¿toca?" (función pura)

`is_due(last, now, interval_h) -> Decision` en `scheduled.py`, sin E/S.
`last` es `LastSnapshot | None | INTERRUPTED` (centinela para el diario
pendiente de D3):
- `last is INTERRUPTED` → toca ("la última ingesta quedó a medias").
- `last is None` → toca ("no hay capturas").
- `last.at - now > 1 h` → toca, con aviso de fecha anómala.
- `last.at > now` (hasta 1 h) → no toca, "fecha posterior a la actual".
- `now - last.at >= interval - 15 min` → toca.
- Si no → no toca, con antigüedad e intervalo para el log.

`interval` sale de `parse_interval(text)`: `strip()`; vacío o ausente → 6;
`^\d+$` y 1..24 (así `06` vale y `6.5`, `seis`, `0`, `25` no) → error de
configuración con el valor recibido.

### D7. Mensajes del log

Cada comprobación escribe en stdout líneas que empiezan por la hora de Madrid,
calculada con `zoneinfo.ZoneInfo("Europe/Madrid")` (no depende de `TZ`, así
que los tests en el Mac dan lo mismo): `2026-10-12 14:17:03 CEST · …`. La
comprobación siempre tiene una línea de resultado (no toca / captura
guardada / otra ingesta en curso / respuesta corta / configuración no válida
/ base ilegible / error); en una captura le siguen el resumen y los avisos,
igual que en la ingesta manual. "Ingesta anterior a medias" y el aviso de
fecha anómala (más de 1 h en el futuro) son líneas adicionales que van antes
de la línea del resultado de la ingesta que provocan. En una respuesta corta, el texto incluye el comando
`docker compose run --rm ingest --accept-short-response`. `scheduled.py`
recibe el reloj (`now`) como parámetro y la CLI acepta un `--now` oculto,
solo para tests (como `--deadline`).

### D8. Contenedor: arranque del programador

Nuevo `container/scheduler.py`, entrypoint del servicio `scheduler`. Se
queda como **supervisor** de supercronic (no hace `exec`; ver D12):
1. Escribe el crontab en `/tmp/crontab` (fuera de `./data`):
   `17 * * * * python /app/container/check.py`.
2. Imprime una línea de arranque (intervalo recibido tal cual, minuto 17).
3. Lanza supercronic como hijo (`subprocess.Popen`, con
   `-passthrough-logs -quiet`: las líneas de la comprobación salen tal cual
   y sin los mensajes informativos de supercronic).
4. Lanza la comprobación de arranque como otro hijo, sin esperarla, para
   que, si dura más allá de las :17, supercronic ya esté en marcha y la
   comprobación de las :17 vea "otra ingesta en curso".
5. Bucle `os.wait()`: recoge a cualquier hijo que termine (la comprobación
   de arranque) y sale con el código de supercronic cuando este termina
   (si supercronic muere por su cuenta, Docker reinicia el servicio).
6. Al recibir SIGTERM o SIGINT: `os.kill(-1, SIGTERM)` (D12) y sigue en el
   bucle hasta que supercronic termine.

Nuevo `container/check.py`: la comprobación en el contenedor. Si el usuario o
el grupo es 0, escribe el motivo y termina sin coger el bloqueo ni leer la
base (por eso con `HOST_UID=0` el programador sigue vivo y lo repite cada
hora). Si no, llama a `src.ingestion.scheduled` con la base fija
`/app/data/prices.db`, el intervalo de `CAPTURE_INTERVAL_HOURS` y, si está,
la URL de `INGEST_API_URL`. La comprobación nunca crea `./data`: si falta,
es un error de log. Para que `python /app/container/check.py` encuentre el
paquete `src` (su `sys.path[0]` es `/app/container`), el `Dockerfile`
define `ENV PYTHONPATH=/app`, que vale también con `docker run` sin Compose.

`container/entrypoint.py` no cambia: el `ingest` manual sigue igual.

### D9. supercronic en la imagen

Etapa de construcción aparte (`FROM python:3.12-slim-bookworm AS supercronic`)
que descarga el binario de la release oficial de GitHub con `urllib` de
Python (la imagen base no trae `curl`; así no se instala nada), elige el
binario según `TARGETARCH` (`amd64`/`arm64`) y compara su SHA-256 con el
fijado en el Dockerfile (`ARG SUPERCRONIC_VERSION`,
`SUPERCRONIC_SHA256_AMD64`, `SUPERCRONIC_SHA256_ARM64`). Si no coincide, la
etapa falla y no hay imagen. La imagen final solo copia el binario a
`/usr/local/bin/supercronic` con `COPY --chmod=755` (se ejecuta como el
usuario del host). Versión: la última estable al implementar; los
SHA-256 se calculan una vez y se contrastan con el SHA-1 que publica el
proyecto en la release.

Fijado en la tarea 1.2 (2026-10-12): **v0.2.49** (publicada el 2026-08-14).

| Binario | SHA-256 (fijado) | SHA-1 (release) |
|---|---|---|
| `supercronic-linux-amd64` | `a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1` | `e63c11a9726b775a6a11801e81af4f3fb926aa68` |
| `supercronic-linux-arm64` | `02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5` | `0b6c5bb743e0b0dafed1132198c81807927ac413` |

Los SHA-1 coinciden con las instrucciones de la release y los SHA-256 con
los que publica GitHub para cada archivo. Flags confirmados con `-help`:
`-passthrough-logs`, `-test`, `-quiet`. Comprobado también: supercronic
lanza **cada trabajo en un grupo de procesos nuevo** y, al recibir SIGTERM,
**espera a que terminen** sin reenviarles la señal (ver D12).

Alternativa descartada: `ADD --checksum` de BuildKit. No admite elegir el
checksum por arquitectura sin varias etapas y exige una sintaxis de
Dockerfile reciente.

### D10. Zona horaria

`python:3.12-slim-bookworm` trae `tzdata` del sistema (Debian bookworm lo
marca como requerido). La tarea 1.1 lo verifica. Si no estuviera, la
alternativa (`apt-get install tzdata` o el paquete `tzdata` de PyPI) es una
dependencia nueva y se consulta al usuario antes de seguir. El servicio
`scheduler` define `TZ=Europe/Madrid`, que supercronic usa para interpretar
`17 * * * *` (cambios de hora incluidos). Los instantes guardados siguen en
UTC (`format_instant` no cambia).

### D11. Compose

```yaml
x-app: &app
  build: .
  image: precios-gasolineras-ingest
  user: "${HOST_UID:?…}:${HOST_GID:?…}"
  init: true
  volumes: [bind ./data → /app/data, create_host_path: false]

services:
  ingest:
    <<: *app
    profiles: ["manual"]      # `up -d` no lo arranca; `run ingest` sí
    restart: "no"
  scheduler:
    <<: *app
    entrypoint: ["python", "/app/container/scheduler.py"]
    restart: unless-stopped
    environment:
      TZ: Europe/Madrid
      CAPTURE_INTERVAL_HOURS: ${CAPTURE_INTERVAL_HOURS:-}
      INGEST_API_URL: ${INGEST_API_URL:-}
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
```

- `profiles` es la forma estándar de que `up` ignore un servicio;
  `docker compose run --rm ingest` lo activa solo. Con `ingest` en un
  profile, `docker compose build` construye la imagen una sola vez (a través
  de `scheduler`). `build` se mantiene en el ancla de los dos servicios: sin
  él, `run ingest` intentaría descargar la imagen de Docker Hub si faltara.
- Cambiar `CAPTURE_INTERVAL_HOURS` cambia la configuración del servicio, así
  que `docker compose up -d` recrea el contenedor.

### D12. Parada sin esperar a la ingesta

La tarea 1.2 comprobó que supercronic lanza cada trabajo en un grupo de
procesos nuevo y que, al recibir SIGTERM, espera a sus trabajos sin
reenviarles la señal. Por eso `TINI_KILL_PROCESS_GROUP` no serviría y se
descarta (decisión del usuario, opción 1):

- tini (PID 1) reenvía SIGTERM a `scheduler.py`, que hace
  `os.kill(-1, SIGTERM)`. En Linux eso llega a todos los procesos del
  contenedor salvo al init y al propio llamante, sea cual sea su grupo:
  supercronic, el `sh -c` de cada trabajo, las comprobaciones y las
  ingestas. Solo ve los procesos de su espacio de nombres (el contenedor).
- La ingesta y la comprobación tratan SIGTERM como Ctrl+C (D14): deshacen la
  transacción, borran sus temporales y terminan. supercronic ve terminar sus
  trabajos y sale; `scheduler.py` sale con él.
- Si algo ignorase la señal, Docker mata todo a los 10 s
  (`stop_grace_period` por defecto), por debajo de los 15 s de la spec. El
  test usa un límite de 5 s para comprobar de verdad el reenvío.

Alternativas descartadas: aceptar el SIGKILL de Docker a los 10 s (la
ingesta no limpia) y acortar `stop_grace_period` (igual, pero antes).

### D14. SIGTERM tratado como Ctrl+C en la ingesta

Hoy la ingesta no instala ningún manejador: con SIGTERM, Python termina sin
ejecutar los `except BaseException` de `storage.py` (ROLLBACK y borrado del
temporal), igual que con SIGKILL, y quedan un diario pendiente o un
`prices.db.tmp-*`. Se añade el context manager `sigterm_as_interrupt()` (en
`src/ingestion/lock.py`, junto al resto de la gestión de procesos), que
instala para SIGTERM el mismo comportamiento que SIGINT (lanzar
`KeyboardInterrupt` en el hilo principal) y restaura el manejador anterior
al salir (algunos tests llaman a `main()` dentro del proceso de pytest).
Lo usan `__main__.main` y `scheduled.main`. Así:
- durante la descarga, la espera `thread.join(timeout)` se interrumpe y el
  proceso sale enseguida (el hilo de descarga es *daemon*);
- durante el guardado, el `KeyboardInterrupt` llega cuando vuelve la llamada
  de SQLite en curso, pasa por el ROLLBACK y por el borrado del temporal;
- `main` captura `KeyboardInterrupt`, escribe `Error: ingesta interrumpida`
  y devuelve 130 (el mismo código que daba Ctrl+C sin capturar). Ctrl+C deja
  de mostrar una traza de Python. Si se interrumpe antes de guardar, se
  quitan las carpetas vacías que creó la propia ingesta (D1).
- Comprobado en la implementación: sin el manejador, un SIGTERM durante el
  guardado deja `prices.db-journal` (código -15); con él, código 130 y solo
  `prices.db`.

Requisito "Señal de parada tratada como Ctrl+C" de `price-ingestion`.

### D13. Tests

- Unitarios (sin Docker): `lock` (dos procesos, `kill -9`, carpetas
  distintas, sin archivos), `formatting`, `parse_interval`, `is_due`
  (todos los instantes de la spec, incluidos los cambios de hora con
  instantes UTC concretos), `read_last_snapshot` (sin archivo, sin capturas,
  versión 7, "hola", diario pendiente, sin crear nada) y la regla del 80 %.
- Funcionales (sin Docker, servidor local y fixtures): escenarios de
  `price-ingestion` nuevos con la CLI, y de `scheduled-collection` con
  `python -m src.ingestion.scheduled --now …` contra el servidor local.
- Fixtures nuevas generadas con `tests/fixtures/make_fixtures.py`: respuestas
  de N estaciones con precio (10, 7, 3 vacías…) para el 80 %.
- Docker (`tests/docker/`, se saltan sin Docker): `up -d` crea solo el
  programador; comprobación de arranque contra el servidor local (con
  `INGEST_API_URL` y `NO_PROXY` en un `docker-compose.override.yml` del
  proyecto temporal); comprobación horaria simulada con
  `docker compose exec scheduler python /app/container/check.py` (su salida
  va a la del `exec`, no a `docker compose logs`: el test suma ambas); ingesta
  manual mientras el programador captura (servidor lento); `stop` en < 15 s;
  root/grupo root; intervalo no válido; configuración de logs con
  `docker inspect`; supercronic y su versión en la imagen; `Europe/Madrid`;
  construcción para `linux/amd64`. Los helpers impiden arrancar el
  programador sin `INGEST_API_URL` (nunca contra la API real); el
  `docker run` sin Compose pasa `-e INGEST_API_URL=http://127.0.0.1:9/api`.
- Fixtures del 80 %: pequeñas (10 y 7 estaciones, 3 sin precio) o
  generadas al vuelo; los límites 9.600/9.599 de 12.000 se prueban con
  enteros en tests unitarios, sin guardar JSON de miles de estaciones.
- Cambios de hora, antes de archivar: tests con reloj inyectado del
  2026-10-25 (segunda 02:17 → no toca, ninguna captura más) y del 2027-03-28
  (comprobaciones de 00:17, 01:17, 03:17 y 04:17 con la hora de Madrid y el
  instante UTC correctos, sin capturas duplicadas). Con estos tests se
  verifica nuestra lógica. Que supercronic no dispare a las 02:17 en marzo
  y cómo se comporta con la hora repetida de octubre se comprueba en los
  logs reales de esos días, como verificación posterior al archivo anotada
  en `docs/container-checks.md` (fuera de tasks.md).
- Manual (en `docs/container-checks.md`): reinicio de OrbStack, parada y
  reinicio, y suspensión.
- Aislamiento del proyecto real (el programador real puede estar en marcha
  mientras se pasan los tests): los tests usan la imagen
  `precios-gasolineras-ingest-test`, construida desde una copia temporal, y
  proyectos de Compose `pgtest-…`. El helper `docker()` rechaza `compose`
  sin `-p pgtest-…`, el `docker-compose.yml` del repo, los contenedores
  `sdd-rastreador-…`, la imagen real y el `data/` real; `run_cli`,
  `start_cli`, `run_check` e `ingest` rechazan bases dentro del `data/` real.
  `scheduler.py` recibe el instalador de manejadores por parámetro (los
  tests nunca instalan el que hace `kill(-1)`) y se niega a arrancar fuera de
  Linux.
- Agentes de Claude Code (decisión del usuario): un hook `PreToolUse` en
  `.claude/settings.json` (`.claude/hooks/guard_real_project.py`, con tests en
  `tests/unit/test_guard_hook.py`) bloquea los comandos Bash que tocarían el
  proyecto real de Compose, sus contenedores, su imagen o `data/`.

## Risks / Trade-offs

- [`flock` sobre una carpeta compartida de OrbStack podría no bloquear entre
  contenedores] → Lo comprueba el test de Docker "Captura manual mientras el
  programador captura". Si fallara, se para y se consulta al usuario (la
  alternativa con archivo de bloqueo cambia la spec).
- [`flock` sobre un descriptor de carpeta en macOS (`.venv`)] → Test
  unitario en el Mac; si no funcionase, se consulta.
- [Tests existentes que preparan una captura previa y luego ingieren
  respuestas pequeñas chocarán con el 80 %] → La tarea 2.6 los localiza y
  los presenta al usuario **antes** de modificarlos (norma de CLAUDE.md),
  aunque la nota de la spec ya lo prevé.
- [Un diario pendiente hace que toque capturar antes del intervalo] →
  Captura de más, coherente con "prefiero capturas de más a perder datos".
  Pasa una sola vez, porque la ingesta deshace el diario.
- [Comportamiento de supercronic en los cambios de hora] → Nuestra lógica se
  prueba con reloj inyectado antes de archivar; la segunda 02:17 de octubre
  no capturaría aunque supercronic disparase dos veces. Los disparos reales
  se revisan en los logs del 2026-10-25 y del 2027-03-28 después de
  archivar (anotado en `docs/container-checks.md`).
- [Flags de supercronic distintos según la versión] → Se confirman con
  `-help` de la versión fijada en la tarea 1.2.
- [El reinicio en bucle por un fallo propio del programador haría una
  petición por arranque] → Las comprobaciones y la ingesta son procesos
  aparte; el proceso principal (supercronic) apenas hace nada. Riesgo
  aceptado (decisión 2 de la revisión).
- [Descargar supercronic necesita salir a GitHub al construir] → Solo en la
  construcción; la suma de comprobación evita un binario alterado.

## Migration Plan

1. `docker compose build` (imagen nueva con supercronic).
2. Opcional: `CAPTURE_INTERVAL_HOURS` en `.env`.
3. `docker compose up -d`. La comprobación de arranque captura si la última
   captura tiene ≥ 5 h 45 min.
4. Vuelta atrás: `docker compose down` y volver a la versión anterior del
   código; la base no cambia de estructura, así que no hay nada que deshacer.
