# Design

## Context

Ver proposal.md (Why y decisiones confirmadas) y las specs delta. Estado
actual que condiciona el diseño:

- La base es SQLite en modo de diario `delete` (sin WAL), esquema versión 1
  (`stations`, `snapshots`, `prices`) y solo los índices automáticos de las
  claves primarias. `prices(snapshot_id, station_id, fuel)` permite leer una
  captura entera por prefijo: las consultas de la última captura tardan
  9–17 ms con la base local de 8 capturas.
- La ingesta guarda con `BEGIN IMMEDIATE` y `sqlite3.connect` sin `timeout`
  (5 s por defecto): al confirmar necesita el bloqueo exclusivo, que espera a
  que terminen los lectores. Una lectura de más de ~5 s le haría perder la
  captura.
- `src/ingestion/storage.py` ya sabe abrir en solo lectura y distinguir un
  diario pendiente (`SQLITE_READONLY_ROLLBACK`, 776).
- `src/ingestion/scheduled.parse_interval` ya implementa las reglas de
  `CAPTURE_INTERVAL_HOURS`.
- La imagen se construye con `python:3.12-slim-bookworm`, sin dependencias
  externas hasta ahora; `container/` tiene los programas de arranque (con la
  comprobación de root) y `docker-compose.yml` usa las anclas `x-app`,
  `x-data` y `x-backups`.

## Goals / Non-Goals

**Goals:**
- Una conexión nueva por petición, en solo lectura y con todas las lecturas
  de la petición en una única transacción de lectura de como mucho 2 s.
- Reutilizar de `src/ingestion` lo que fija reglas ya especificadas (versión
  del esquema, intervalo), sin que la ingesta importe nunca nada de `src/api`.
- Mensajes, códigos y formato de error controlados por el proyecto, también
  para los errores que genera FastAPI.

**Non-Goals:**
- Caché de respuestas o de conexiones entre peticiones.
- Índices, vistas o cualquier escritura en la base (van, si hacen falta, en
  `add-price-stats` desde la ingesta).
- `healthcheck` de Docker, varios procesos de uvicorn o HTTPS.

## Decisions

### D1. Estructura del código

`src/api/` con módulos pequeños y probables por separado:

| Módulo | Contenido |
|---|---|
| `app.py` | Crea la aplicación FastAPI, rutas y manejadores de error. |
| `db.py` | Abrir la base, transacción de lectura, límites de tiempo y traducción de errores de SQLite a `ApiError`. |
| `queries.py` | Las consultas SQL de cada ruta (sobre una conexión ya abierta). |
| `catalog.py` | Catálogo fijo de 21 combustibles (nombre, `slug`, unidad, tipo). |
| `geo.py` | Zonas de España y distancia (haversine, R = 6371 km). |
| `formatting.py` | Recorte de textos, redondeos y fecha de la fuente con desfase. |
| `health.py` | Estado de la salud a partir de la captura, el reloj y el intervalo. |
| `access_log.py` | Línea de log por petición, con coordenadas redondeadas. |
| `errors.py` | `ApiError(status, code, message, headers)`. |

`container/api.py` es el programa de arranque: comprueba usuario y grupo
distintos de 0 **antes de importar uvicorn o FastAPI** (mensaje y código 2,
como `entrypoint.py`) y después lanza uvicorn en proceso con
`host="0.0.0.0"`, `port=8000`, `access_log=False` (el log lo escribe
`access_log.py`) y `timeout_graceful_shutdown=5`.

`src/api` puede importar de `src/ingestion` (`SCHEMA_VERSION`,
`SQLITE_READONLY_ROLLBACK`, `parse_interval`); nunca al revés. Alternativa
descartada: copiar esas reglas en `src/api`, que podrían desincronizarse.

### D2. Conexión por petición, solo lectura y sin `immutable`

Cada petición de datos hace:

1. Si `data/prices.db` no existe → `sin_base` (abrirla con `mode=ro` no la
   crea, pero se comprueba antes para dar el mensaje correcto).
2. `sqlite3.connect("file:...?mode=ro", uri=True, timeout=2.0,
   isolation_level=None)`.
3. `BEGIN` y `PRAGMA user_version`: esta primera lectura toma el bloqueo
   compartido; si hay un bloqueo exclusivo, SQLite reintenta hasta 2 s
   (`base_ocupada`, 503, `Retry-After: 5`).
4. A partir de ahí, todas las consultas de la petición dentro de la misma
   transacción (D3) y `COMMIT` + `close()` antes de construir la respuesta.

Errores traducidos: `SQLITE_BUSY` → `base_ocupada`; 776 →
`recogida_a_medias`; `SQLITE_NOTADB` o cualquier otro error al abrir/leer la
cabecera → `base_ilegible`; versión 0 sin tabla `snapshots` o sin filas →
`sin_capturas`; versión distinta de 0 y 1 → `base_no_compatible`.

Una conexión nueva por petición cuesta menos de 1 ms y garantiza que una
base creada o restaurada con la API en marcha se ve en la siguiente petición.
**Nunca `immutable=1`** (ignora los bloqueos y podría leer una captura a
medias) ni `PRAGMA journal_mode`, `query_only` u otros que escriban.
Alternativas descartadas: conexión única compartida (seguiría leyendo el
archivo apartado tras una restauración) y `nolock=1` (mismo riesgo que
`immutable`).

### D3. Una sola transacción y límite de 2 s de lectura

Todas las lecturas de una petición van en la transacción de D2, así salen de
la misma captura aunque se guarde otra a la vez. El límite de 2 s empieza
cuando se obtiene el bloqueo compartido (después de la espera de D2, que no
cuenta). Se aplica con `set_progress_handler` (cada 1.000 instrucciones de
SQLite comprueba un plazo de `time.monotonic()`) y, entre sentencias, con la
misma comprobación en Python. Si se supera, el manejador devuelve un valor
distinto de 0 (SQLite corta la sentencia); después se quita el manejador, se
hace `ROLLBACK` tolerando «no transaction is active» (SQLite puede haberla
cerrado ya), se cierra la conexión (que libera el bloqueo en cualquier caso)
y se responde `consulta_demasiado_larga` (503).

El plazo es un parámetro de `db.py` (2 s por defecto) para que los tests
usen uno muy pequeño con una consulta lenta inyectada (CTE recursiva) sin
esperar segundos. El procesado en Python (distancias, orden, redondeos) se
hace después de cerrar la transacción.

Con este límite, el peor caso para la ingesta es: espera hasta 2 s a que
terminen los lectores en curso; mientras espera tiene el bloqueo pendiente y
los lectores nuevos no entran. Margen de 3 s sobre sus 5 s.

### D4. Validación y errores en español

Los parámetros se declaran con tipos y límites en FastAPI (`ge`, `le`, `gt`,
`allow_inf_nan=False`) para que `/api/openapi.json` los describa. Los
errores de FastAPI se traducen en manejadores propios:

- `RequestValidationError` → 422 `parametro_no_valido`, con un mensaje fijo
  por parámetro (tabla en `app.py`: `lat`, `lon`, `radius_km`, `limit`,
  `fuel`), sin incluir el valor recibido. Se usa el primer parámetro con
  error.
- `StarletteHTTPException` 404 → `no_encontrado`; 405 → `metodo_no_permitido`
  conservando `Allow: GET`.
- `ApiError` → su estado, código y cabeceras.
- `Exception` → 500 `error_interno`, con la traza solo en el log.

Orden dentro de cada ruta: validación de FastAPI → `fuel` en el catálogo
(`combustible_desconocido`) → punto en las zonas (`fuera_de_espana`) → base.
Así los 422 nunca esperan a la base. La salud envuelve cualquier `ApiError`
añadiendo `"status": "error"` en la raíz.

Alternativa descartada: recibir todos los parámetros como texto y validarlos
a mano; daría el mismo control de mensajes pero una documentación OpenAPI
sin tipos ni límites.

### D5. Catálogo explícito

Los 21 combustibles se escriben a mano en `catalog.py` con su `slug`, unidad
y tipo, tal como los fija la spec. Un test comprueba que cada `slug` cumple
la regla (minúsculas, sin tildes, espacios → guion). Alternativa descartada:
calcular el `slug` al vuelo, que haría depender el contrato de la API de una
regla que no cubre todos los signos posibles.

### D6. Cercanas en Python sobre la captura

La consulta trae, de la última captura y del combustible pedido, identificador,
precio y datos de la estación (unas 11.300 filas como mucho, ~17 ms). En
Python: se descartan coordenadas nulas o fuera de zonas, se calcula la
distancia, se filtra por radio, se ordena por `(precio, distancia exacta,
id)`, se cuenta `total` y se corta en `limit`. Alternativa descartada: filtro
por rectángulo en SQL; sin índice sobre coordenadas no ahorra lectura y
complica el código. Si `add-price-stats` o el tamaño lo exigen, se revisa.

### D7. Redondeos con `Decimal`

Precios y distancias se convierten con `Decimal(repr(x))`. La media de
provincia es la suma exacta en `Decimal` dividida entre el número de
estaciones y cuantizada a `0.001` con `ROUND_HALF_UP`; la distancia, a
`0.01`. Se devuelven como números JSON. Así 1.404 y 1.405 dan 1.405, cosa
que `round()` sobre `float` no garantiza.

### D8. Fecha de la fuente con desfase

Con `zoneinfo.ZoneInfo("Europe/Madrid")`: se construye la hora con `fold=0`
y `fold=1`. Si las dos dan el mismo desfase, se usa. Si dan distinto (hora
repetida), se elige la que, pasada a UTC, queda más cerca de `downloaded_at`.
Si la hora no existe (pasar a UTC y volver no devuelve la misma hora local),
`null`. Los datos de zona vienen del sistema de la imagen (ya exigido en
`ingestion-container`).

### D9. Salud

`health.py` recibe la captura, el reloj (inyectable en tests) y el texto de
`CAPTURE_INTERVAL_HOURS`, y usa `parse_interval`. Umbral = 2 × intervalo +
1 h; `desactualizada` solo si la antigüedad es mayor que el umbral (una
captura en el futuro tiene antigüedad negativa → `ok`). Con `InvalidInterval`:
`configuracion_no_valida`, `stale_after_hours: null` y el mensaje de
`parse_interval`. Primero se lee la base: sus 503 ganan. `unexposed_fuels`
sale de un `GROUP BY fuel` de la última captura menos el catálogo.

### D10. Log por petición

Un middleware escribe en la salida estándar una línea por petición al
terminarla:

`2026-10-16 11:30:02 CEST · GET /api/stations/nearby lat=40.42 lon=-3.70 fuel=gasoleo-a → 200 (14 ms)`

`lat` y `lon` se redondean a 2 decimales si son números finitos y, si no, se
escriben como `(no válido)`; otros parámetros se escriben tal cual, cortados
a 40 caracteres. La duración sirve para la medición en el VPS (D13). El log
de acceso de uvicorn está desactivado para que nunca escriba la consulta
original. La rotación (3 × 10 MB) la hace Docker.

En Starlette el manejador de `Exception` queda por fuera de los middlewares
de usuario, así que una excepción no prevista atraviesa el middleware: este
la captura, escribe su línea con código 500 y la vuelve a lanzar para que el
manejador construya la respuesta y escriba la traza.

### D11. Servicio en Compose

```yaml
api:
  <<: *app
  entrypoint: ["python", "/app/container/api.py"]
  restart: unless-stopped
  volumes:
    - <<: *data
      read_only: true
  ports:
    - "127.0.0.1:8000:8000"
  environment:
    TZ: Europe/Madrid
    CAPTURE_INTERVAL_HOURS: ${CAPTURE_INTERVAL_HOURS:-}
  logging: (igual que scheduler)
```

Uvicorn escucha en `0.0.0.0` *dentro* del contenedor (necesario para que
Docker reenvíe el puerto); solo se publica en `127.0.0.1` del host. Con root,
`container/api.py` sale con código 2 y Docker la reintenta con su espera
creciente (hasta 1 min).

### D12. Dependencias fijadas e instalación

- `requirements.txt` (nuevo): `fastapi` y `uvicorn` sin extras y todas sus
  dependencias con `==`, obtenidas con `pip freeze` en un entorno virtual
  limpio creado en una carpeta temporal.
- `requirements-dev.txt`: `-r requirements.txt`, `pytest` y `httpx` fijados.
- `Dockerfile`: `COPY requirements.txt` y `pip install --no-cache-dir
  --no-deps -r requirements.txt` antes de copiar `src/` (caché de capas) y
  `pip check` en la construcción. `--no-deps` impide que entre nada no
  listado. `requirements.txt` no está en `.dockerignore`.

Alternativa descartada: `--require-hashes`; obligaría a mantener a mano los
hashes de las ruedas de cada arquitectura (pydantic-core es binaria) sin
herramienta para generarlos, que sería otra dependencia.

### D13. Medición de tiempos

`tools/perf/` (fuera de `src/` y de la imagen) con dos programas sin
dependencias nuevas:

- `make_year_db.py DESTINO COPIA.db`: exige que `DESTINO` no exista y que ni
  `DESTINO` ni `COPIA.db` estén bajo `./data`; abre la copia en solo lectura,
  la copia y repite su última captura
  hasta 1.460 capturas con `INSERT … SELECT` (fechas desplazadas 6 h). Avisa
  de que ocupará unos 4–5 GB.
- `measure.py URL`: lanza 20 veces cada ruta con parámetros representativos
  (Madrid, `gasoleo-a`, radio 50, una estación real) y muestra el tiempo
  máximo de cada una.

En el VPS se mide a través del túnel y la duración sin red se lee en el log
de la API (D10). Los resultados se apuntan en este design.md.

### D14. Tests

- Unitarios: catálogo, `geo`, redondeos, fecha de la fuente, salud, recorte
  de textos, línea de log, programa de arranque.
- De API con `fastapi.testclient` (usa httpx) contra bases creadas en
  `tmp_path` con la ingesta real (`tests/storage_helpers.ingest`) o con SQL
  directo cuando hay que preparar datos imposibles para la ingesta
  (coordenadas (0, 0), textos con espacios, Metanol, versión 2).
- Bloqueos: un proceso auxiliar con `BEGIN EXCLUSIVE` (en modo `delete` un
  bloqueo exclusivo impide leer) durante el tiempo del escenario;
  `make_pending_journal` ya existente para el diario pendiente.
- Funcionales: uvicorn real en un puerto local libre con 4 clientes mientras
  la ingesta guarda contra el servidor de pruebas (`tests/http_server.py`).
- Docker: `compose config` (puerto, montajes, logging), servicio arrancado,
  root, escritura imposible, bloqueo entre dos contenedores e importaciones.
  Para las importaciones se usa la variable `PYTHONPROFILEIMPORTTIME=1`, que
  heredan el `os.execv` de `entrypoint.py` y los procesos que lanza
  supercronic (`-X importtime` no pasa a los procesos hijos), y se comprueba
  que la salida no menciona `fastapi` ni `uvicorn`.
- Puerto en los tests Docker: `make_project` (`tests/docker/helpers.py`)
  sustituye `127.0.0.1:8000:8000` por `127.0.0.1:<puerto libre>:8000`,
  comprobando que la línea aparece una sola vez, como ya hace con la imagen.
  Así ningún test, tampoco los existentes que lanzan `up -d`, toca el puerto
  8000 real del Mac ni la API que lee el `./data` real, y dos tests no chocan.
  Los tests de `docker compose config` del puerto y los montajes se pasan
  sobre el `docker-compose.yml` sin tocar. `requirements.txt` se añade a
  `BUILD_FILES` para que la imagen de los tests se construya.

Ningún test usa `./data`, `~/Backups` ni la API del Ministerio.

## Risks / Trade-offs

- [Bloqueos de SQLite entre contenedores en Colima/virtiofs no probados] →
  test Docker de D14 con dos contenedores; si fallara, se para y se consulta
  (no se cambia a `immutable`).
- [Una consulta lenta en el futuro corta a 2 s y da 503] → el límite protege
  la recogida; `add-price-stats` se diseñará con él.
- [Swagger UI carga recursos de una CDN] → aceptado en la spec; la API
  funciona sin `/api/docs`.
- [`--no-deps` con una lista incompleta rompe la construcción] → `pip check`
  en el `Dockerfile` y el test de versiones de la imagen.
- [Volver a la versión anterior deja el contenedor `api` huérfano] → el
  runbook indica `docker compose up -d --remove-orphans` al volver atrás.
- [Puerto 8000 ocupado en el Mac] → `up -d` falla con el mensaje de Docker;
  el README lo explica.
- [Estaciones de Portugal o Francia dentro de los rectángulos] → aceptado.

## Migration Plan

Sin migración de datos: la base no cambia. Despliegue en el VPS (lo lanza el
usuario, siguiendo el runbook): copia a mano, `git pull`, `docker compose
build`, `docker compose up -d`, comprobaciones de `server-deployment`
(`ps`, `curl` de la salud, `ss -tlnp`, `ufw status`) y túnel desde el Mac.
Vuelta atrás: `git checkout <versión anterior>`, `docker compose build` y
`docker compose up -d --remove-orphans`; la base no se ha tocado.

## Mediciones

Se completará durante la implementación (D13): Mac con base sintética de un
año y VPS con la base real.
