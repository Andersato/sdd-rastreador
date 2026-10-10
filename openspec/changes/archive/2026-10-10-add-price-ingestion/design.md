# Design

## Context

Proyecto nuevo: no hay código, ni base de datos, ni dependencias declaradas.
El comportamiento está en `specs/price-ingestion/spec.md`; la motivación, en
proposal.md. El proyecto usa Python 3.12 en un entorno virtual propio (el 3.9
del sistema está sin soporte y no se usa). La ingesta vive en
`src/ingestion/` sin depender de `src/api/` ni de `web/`.

La respuesta de la API pesa varios MB (unas 12.000 estaciones) y tiene esta
forma (resumida):

```json
{
  "Fecha": "10/10/2026 19:05:23",
  "ListaEESSPrecio": [
    {
      "IDEESS": "4375", "Rótulo": "REPSOL", "Dirección": "CALLE MAYOR, 1",
      "Municipio": "Madrid", "Provincia": "MADRID", "Horario": "L-D: 24H",
      "Latitud": "40,416775", "Longitud (WGS84)": "-3,703790",
      "Precio Gasoleo A": "1,459", "Precio Hidrogeno": "", "...": "..."
    }
  ],
  "Nota": "...",
  "ResultadoConsulta": "OK"
}
```

## Goals / Non-Goals

**Goals:**
- Ingesta en piezas separadas y testeables por separado: descarga,
  normalización (sin E/S) y guardado.
- Todo el guardado de una ejecución en una única transacción SQLite, incluida
  la creación del esquema.
- Tests deterministas: URL, ruta de la base de datos, plazo y reloj
  inyectables; ningún test puede salir a la red.
- Ninguna dependencia nueva en producción.

**Non-Goals:**
- Rendimiento más allá de lo necesario (una ejecución manual de segundos).
- Modelo de datos pensado para consultas web; se ajustará cuando llegue la API.
- Concurrencia entre ejecuciones (fuera de alcance en la proposal).

## Decisions

### D0. Versión de Python y entorno

- Python **3.12**, fijado en `.python-version` (`3.12`) y declarado en
  `pyproject.toml` (`requires-python = ">=3.12"`).
- Entorno virtual en `.venv/` (ignorado por git), creado con
  `python3.12 -m venv .venv`; las dependencias de desarrollo se instalan con
  `pip install -r requirements-dev.txt`. El README lo explica paso a paso.
- Tipos modernos (`X | None`, `list[str]`) sin `from __future__`.
- La configuración de pytest va en `pyproject.toml` (`[tool.pytest.ini_options]`
  con `testpaths = ["tests"]` y `pythonpath = ["."]`, para importar `src.*`).
  No hay `pytest.ini`.

*Alternativa descartada:* el Python 3.9 del sistema, sin soporte de seguridad.

### D1. Estructura del código

```
src/__init__.py
src/ingestion/
  __init__.py
  __main__.py     # CLI: python -m src.ingestion [--db RUTA] [--url URL]
  client.py       # descarga: una petición, plazo total, sin reintentos
  parser.py       # JSON → estaciones, precios, fecha y avisos (función pura)
  number_parsing.py  # conversión "1,459" → número y validación (no se llama
                     # numbers.py para no tapar el módulo estándar `numbers`)
  storage.py      # esquema SQLite y guardado transaccional
  models.py       # dataclasses: Station, PriceRecord, ParsedSnapshot, IngestionWarning
  errors.py       # DownloadError, DownloadTimeout(DownloadError), InvalidResponseError, StorageError
```

`parser.py` no hace E/S: recibe el JSON ya decodificado y devuelve un
`ParsedSnapshot` o lanza `InvalidResponseError`. Así casi toda la spec se
prueba con tests unitarios sin red ni base de datos.

*Alternativa descartada:* un único módulo. Más simple al principio, pero
mezcla red, reglas de limpieza y SQL, y obliga a tests de integración para
todo.

### D2. Cliente HTTP con la librería estándar (`urllib.request`)

- **Una sola llamada** a `urlopen` con `Accept: application/json`. En Python
  3.12, `urllib` sigue 301, 302, 303, 307 y 308 dentro de esa llamada (la
  redirección cuenta como la misma petición). No hay bucle de reintentos en
  ningún sitio.
- **Estado final:** cualquier estado final distinto de 200 es un error.
  `urlopen` lanza `HTTPError` para ≥ 400 y para 3xx que no sigue (304, 300 sin
  `Location`, más de 10 saltos); los 2xx distintos de 200 (204, 206…) se
  comprueban a mano. Todos acaban en `DownloadError`.
- **Plazo total de 120 s** (constante `DOWNLOAD_DEADLINE_S = 120`, parámetro
  opcional para los tests):
  - Toda la descarga (resolución DNS, conexión, cabeceras, redirecciones y
    lectura del cuerpo) se ejecuta en un `threading.Thread(daemon=True)` que
    deja su resultado o su excepción en una `queue.Queue`. El hilo principal
    espera con `thread.join(timeout=plazo)`; si el hilo sigue vivo, se lanza
    `DownloadTimeout("se agotó el tiempo de descarga (120 s)")`, la CLI
    termina y el intérprete sale sin esperar al hilo (es *daemon*). El hilo
    abandonado no puede escribir nada porque la descarga no toca la base de
    datos.
  - No se usa `concurrent.futures.ThreadPoolExecutor`: desde Python 3.9 sus
    hilos no son *daemon* y el intérprete los espera al salir, así que el
    proceso no terminaría hasta acabar la descarga.
  - Dentro del hilo, `urlopen(..., timeout=plazo)` limita además cada
    operación de red, para que el hilo no quede colgado indefinidamente.
  - Cualquier `TimeoutError` (en 3.12 `socket.timeout` es un alias) y
    `URLError` cuyo `reason` sea un `TimeoutError` se convierten también en
    `DownloadTimeout`, con el mismo mensaje. Así "Tiempo agotado" da siempre
    el mismo error, sea por cabeceras lentas o por envío lento.
  - Esto cubre también la resolución DNS, que no tiene límite propio.
- **Cuerpo:** se lee entero como bytes y se decodifica con `json.loads(bytes)`
  (detecta UTF-8 con o sin BOM; no se decodifica antes como texto). Cuerpo
  vacío o JSON inválido o truncado → `InvalidResponseError`.
- **Excepciones que se capturan y traducen, en este orden** (importa porque
  `HTTPError` hereda de `URLError`, y `URLError` y `TimeoutError` de
  `OSError`):
  1. `HTTPError` → `DownloadError` con el código (p. ej. "HTTP 503").
  2. `URLError` → `DownloadTimeout` si `reason` es un `TimeoutError`; si no,
     `DownloadError`.
  3. `TimeoutError` → `DownloadTimeout`.
  4. `http.client.HTTPException` (incluida `IncompleteRead`, cuando el cuerpo
     es más corto que su `Content-Length`) → `DownloadError`.
  5. `OSError` (incluido `socket.gaierror`) → `DownloadError`.
  `ValueError` (incluye `json.JSONDecodeError`, `UnicodeDecodeError` y los
  enteros JSON demasiado largos) y `RecursionError` (anidamiento excesivo) al
  decodificar → `InvalidResponseError`. Una URL mal formada (`ValueError` al
  construir la petición, o `http.client.InvalidURL`, que se captura antes que
  `HTTPException`) → `DownloadError("URL no válida")`. La respuesta de un `HTTPError` se
  cierra antes de relanzar.
  Ninguna otra excepción de red llega a la CLI sin traducir.
- `urllib` corta los bucles de redirección (máximo 10 saltos) con `HTTPError`,
  que acaba en `DownloadError`.
- **Instante de descarga:** el reloj (`now()`, UTC) se lee justo después de
  recibir el cuerpo completo.

*Alternativa descartada:* comprobar el plazo con `time.monotonic()` entre
bloques de lectura. Una lectura bloqueada o una resolución DNS lenta podían
superar el plazo sin que se comprobara.
*Alternativa descartada:* `requests` o `httpx`. Son una dependencia nueva y no
aportan nada imprescindible para una única petición.

### D3. Normalización

`number_parsing.parse_decimal(value)`:
1. Si `value` no es `str`, es formato inválido.
2. `str.strip()` sin argumentos: quita cualquier espacio en blanco Unicode
   (espacio, tabulador, salto de línea, U+00A0…).
3. Debe cumplir `re.fullmatch(r"-?[0-9]+(,[0-9]+)?", s)`; si no, es formato
   inválido (incluye `"1.459"`, `"1,4a9"` y `""`). Se usa `[0-9]` y no `\d`,
   que aceptaría dígitos de otros alfabetos.
4. Se sustituye la coma por punto y se convierte con `Decimal` y luego a
   `float` para guardarlo. Si el resultado no es finito (un número de cientos
   de dígitos daría infinito), es formato inválido.

Reglas del parser encima de esa función:
- **Estructura:** la raíz debe ser un objeto, `ResultadoConsulta` debe ser
  `"OK"`, `ListaEESSPrecio` debe ser una lista no vacía y cada elemento un
  objeto. Si no, `InvalidResponseError`.
- **`IDEESS`:** debe ser `str`; se le aplica `strip()`. Ausente,
  vacío o con solo espacios → `InvalidResponseError`. Duplicado (tras quitar
  espacios) → `InvalidResponseError` con el identificador en el mensaje.
- **Textos fijos:** `null` o ausente → `''`; `str` → tal cual; `int` o `float`
  (no `bool`) → `str(valor)` (`123` → `"123"`), sin aviso.
- **Precio** (cada clave que empieza por `Precio `): `null`, ausente, vacío o
  solo espacios → sin precio y sin aviso. Inválido (incluido un tipo que no es
  `str`), `<= 0` → aviso y se descarta.
- **Coordenadas:** se validan juntas. Si latitud o longitud está ausente,
  `null`, no es `str`, está vacía, es inválida o está fuera de rango
  (lat −90..90, lon −180..180, extremos incluidos), se descartan las dos y se emite un aviso por
  cada campo problemático; en un campo ausente, el valor del aviso es
  `(ausente)`. Invariante: la estación sale del parser siempre con
  las dos coordenadas o con ninguna.
- **`Fecha`:** debe ser `str` y pasar
  `datetime.strptime(s, "%d/%m/%Y %H:%M:%S")`, que rechaza fechas imposibles
  como `31/02/2026`. `strptime` acepta día, mes y hora de un dígito
  (`1/2/2026 9:05:23`); la spec lo admite expresamente. Ausente, `null` o
  inválida → `source_date = None` y aviso.

Precios y coordenadas se guardan como `REAL`. Con 3 decimales en precios y 6
en coordenadas, la precisión de `float` sobra.

*Alternativa descartada:* guardar precios como enteros en milésimas de euro.
Evita los decimales binarios, pero la spec acepta cualquier número de
decimales y se perderían.

### D4. Modelo de datos (esquema inicial)

```sql
CREATE TABLE stations (
    id            TEXT PRIMARY KEY,   -- IDEESS sin espacios alrededor
    brand         TEXT NOT NULL,      -- Rótulo ('' si vacío)
    address       TEXT NOT NULL,
    municipality  TEXT NOT NULL,
    province      TEXT NOT NULL,
    schedule      TEXT NOT NULL,      -- Horario
    latitude      REAL,               -- NULL = sin coordenadas
    longitude     REAL
);

CREATE TABLE snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    downloaded_at  TEXT NOT NULL,     -- instante UTC ISO 8601: 2026-10-10T17:05:30Z
    source_date    TEXT               -- Fecha de la API, hora de Madrid sin desfase:
                                      -- 2026-10-10T19:05:23; NULL si faltaba o era inválida
);

CREATE TABLE prices (
    snapshot_id  INTEGER NOT NULL REFERENCES snapshots(id),
    station_id   TEXT    NOT NULL REFERENCES stations(id),
    fuel         TEXT    NOT NULL,    -- "Gasoleo A", tal cual tras quitar "Precio "
    price        REAL    NOT NULL CHECK (price > 0),
    PRIMARY KEY (snapshot_id, station_id, fuel)
);
```

- El esquema se crea con `CREATE TABLE IF NOT EXISTS` y `PRAGMA
  user_version = 1` **dentro de la transacción del guardado** (D5), así que
  también se deshace si algo falla. Si la base existe con un `user_version`
  distinto de 0 o 1, se hace `ROLLBACK` sin haber escrito nada y la ingesta
  termina con `StorageError("versión de base de datos no compatible: 7")`
  (requisito "Base de datos con estructura desconocida").
- `fuel` como texto, sin tabla de combustibles: la spec guarda el nombre que
  da la API y no hay consultas que lo justifiquen todavía.
- `downloaded_at` en UTC: es un instante inequívoco, independiente de la zona
  de la máquina (escenario "Registro de la captura").
- `source_date` se guarda como hora local de Madrid sin convertir. Así no hay
  que decidir nada en la hora repetida del cambio de hora de octubre; se
  guarda exactamente lo que dice la API.
- **Ruta por defecto independiente de la carpeta de trabajo:**
  `PROJECT_ROOT = Path(__file__).resolve().parents[2]` (de
  `src/ingestion/storage.py` a la raíz del repo) y
  `DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "prices.db"`. Así cron o launchd
  (`add-scheduled-collection`) escriben siempre en la misma base, se lancen
  desde donde se lancen. `--db` acepta otra ruta; si es relativa, se resuelve
  respecto a la carpeta actual (es lo que espera quien la escribe).
- La carpeta del archivo (`data/` u otra) se crea con
  `mkdir(parents=True, exist_ok=True)` solo después de descargar y parsear
  (D5). `.gitignore` incluye `data/` y `*.db`.
- Al arrancar `storage` se comprueba `sqlite3.sqlite_version_info >= (3, 24)`
  (necesario para el upsert); si no, error claro.

**Migración e histórico:** es el primer esquema y no hay datos que preservar.
Las tablas solo reciben `INSERT` (snapshots, prices) o `UPSERT` sobre los
datos fijos (stations); nunca se borran capturas ni precios.

### D5. Guardado todo o nada

1. Descargar y parsear **todo** en memoria antes de tocar la base de datos.
   Los errores de descarga (D2) y de estructura (D3) se detectan aquí; si se
   produce alguno, no se abre ni se crea ningún archivo.
2. **Archivo de destino:**
   - Si la base ya existe, se abre directamente.
   - Si no existe, se trabaja sobre un archivo temporal en el mismo
     directorio, con sufijo aleatorio y creado en exclusiva (`O_EXCL`), así
     que nunca se reutiliza un temporal huérfano (`prices.db.tmp-<hex>`) y, solo tras el `COMMIT` y el cierre
     de la conexión, se renombra al nombre definitivo con `os.replace`. Si
     algo falla, el temporal (creado por esta ejecución, sin datos de nadie)
     se elimina y no queda ningún archivo de base de datos.
3. **Conexión:** `sqlite3.connect(ruta, isolation_level=None)` (modo
   autocommit de SQLite, transacciones explícitas). Justo después de conectar
   y **antes** de `BEGIN`: `PRAGMA foreign_keys = ON` (dentro de una
   transacción SQLite lo ignora sin avisar).
4. **Una única transacción** (`BEGIN IMMEDIATE` … `COMMIT`; `ROLLBACK` ante
   cualquier excepción):
   - Creación del esquema si hace falta y comprobación de `user_version`.
   - `INSERT` en `snapshots`.
   - Por estación, se comprueba si el `id` existía (para contar nuevas y
     actualizadas) y se hace un upsert:
     ```sql
     INSERT INTO stations (...) VALUES (...)
     ON CONFLICT(id) DO UPDATE SET
       brand = excluded.brand, address = excluded.address, ...,
       latitude  = COALESCE(excluded.latitude,  stations.latitude),
       longitude = COALESCE(excluded.longitude, stations.longitude)
     ```
     Los textos se sobrescriben siempre (también con `''`). Las coordenadas
     solo si las nuevas son válidas. Como el parser garantiza "las dos o
     ninguna" (D3), nunca se mezcla una latitud nueva con una longitud
     antigua. Consecuencia aceptada: con este cambio no hay forma de vaciar
     unas coordenadas que ya existían; si algún día hace falta, será un cambio
     explícito.
   - Inserción de los precios mediante una función interna
     `_insert_prices(conn, ...)` (con `executemany`).
5. **Errores fuera y dentro de la transacción:** cualquier `sqlite3.Error` u
   `OSError` desde la creación de la carpeta y `connect` hasta `os.replace`
   (incluidos `PRAGMA`, `BEGIN IMMEDIATE` sobre un archivo que no es SQLite y
   el propio renombrado) se convierte en `StorageError` → código 1. Si se
   estaba usando un temporal, se cierran la conexión y se eliminan el temporal
   y su `-journal`. Nunca se borra ni se renombra un archivo que ya existía.

### D6. Avisos y CLI

- El parser devuelve una lista de `IngestionWarning(station_id, field, value,
  reason)`: precio inválido, cero o negativo, coordenada problemática y
  `Fecha` inválida (con `station_id = None`).
- Salida correcta (stdout): resumen con estaciones procesadas, nuevas,
  actualizadas, precios guardados y avisos, seguido de un aviso por línea.
  Código 0, haya avisos o no.
- Salida con error (stderr): motivo (p. ej. `Error: la descarga ha fallado con
  HTTP 503`, `Error: se agotó el tiempo de descarga (120 s)`,
  `Error: IDEESS duplicado: 4375`). Código 1.
- **Opción oculta `--deadline <segundos>`** (no aparece en `--help`,
  `help=argparse.SUPPRESS`; por defecto 120): permite a los tests funcionales
  reducir el plazo en el subproceso. No cambia ningún comportamiento de la
  spec, solo el valor del tiempo límite.
- Formato de un aviso: `Aviso: estación 4375, Latitud: valor "abc" no válido
  (formato no válido)`. El valor va entre comillas solo si llegó como texto;
  si no, en JSON sin comillas (`valor null`, `valor 40.5`), y para un campo
  ausente, `valor (ausente)`.
- `main(argv, now=..., deadline_s=...)` acepta reloj y plazo inyectables para
  los tests en proceso. El reloj es un callable sin argumentos que devuelve un `datetime`
  con zona horaria; por defecto, `lambda: datetime.now(timezone.utc)`. Antes de
  guardar se convierte a UTC y se formatea como `AAAA-MM-DDTHH:MM:SSZ`.

### D7. Estrategia de tests

- **Estructura:** `tests/unit/`, `tests/functional/`, `tests/fixtures/` y
  utilidades compartidas en `tests/conftest.py`, `tests/http_server.py`,
  `tests/helpers.py` (`run_cli`, `db_dump`, `closed_port_url`),
  `tests/builders.py`, `tests/storage_helpers.py` y `tests/scenario_helpers.py`.
- **Red bloqueada:** `tests/conftest.py` tiene un fixture `autouse` que, con
  `monkeypatch`, sustituye `socket.socket.connect` y `socket.getaddrinfo` para
  que cualquier destino que no sea `127.0.0.1`/`localhost` lance un error. Sin
  dependencias nuevas. Para los subprocesos de los tests funcionales (a los
  que no llega el `monkeypatch`), un helper `run_cli(...)` es la única forma
  de lanzar la CLI: usa `sys.executable` con `cwd` en la raíz del repo por
  defecto (admite `cwd=` y `project_root=` para lanzar una copia), pasa
  siempre `--url http://127.0.0.1:<puerto>/` y `--db` en `tmp_path`, falla si
  se le pide otra URL, y elimina `http_proxy`/`https_proxy` del entorno y fija
  `no_proxy=127.0.0.1,localhost` (urllib respeta los proxies del sistema). Los
  tests en proceso hacen lo mismo con `monkeypatch.delenv`/`setenv`.
- **Unitarios (pytest):**
  - `number_parsing` y `parser`, con diccionarios pequeños escritos en el test o en
    `tests/fixtures/`.
  - `storage`, contra un SQLite temporal (`tmp_path`).
  - `client`, contra un servidor HTTP local (`http.server` en un hilo) que
    sirve fixtures, responde 301/204/206/500/503, devuelve cuerpos vacíos o
    truncados (con `Content-Length` mayor que el cuerpo, o cerrando la
    conexión), no responde, o envía muy despacio. Cuenta las peticiones por
    ruta: una redirección se ve como exactamente una petición a la URL de
    origen y una a la de destino, y ninguna más.
- **Funcionales:** ejecutan la CLI de principio a fin con `run_cli` contra el
  servidor local, y comprueban el código de salida, el resumen y el contenido
  de la base de datos. Playwright no aplica: este cambio no tiene interfaz.
- **Base de datos intacta:** helper `db_dump(ruta)` que devuelve el contenido
  completo de las tres tablas (o "no existe"), para comparar antes y después.
- **Fallo de escritura:**
  - Base existente: se crea en la base de pruebas un trigger
    `BEFORE INSERT ON prices BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END`.
  - Primera ejecución (no hay base donde poner el trigger): `monkeypatch` de
    la función Python `storage._insert_prices` para que lance
    `sqlite3.OperationalError`. (Los métodos de `sqlite3.Connection` están en
    C y no se pueden sustituir.)
- **Plazo a nivel de proceso:** test funcional con `run_cli(..., deadline=1)`
  (que pasa `--deadline 1`) contra un servidor que envía muy despacio: el
  subproceso debe terminar con código ≠ 0 y mensaje de tiempo agotado en
  menos de 1 + 3 s (margen para máquinas cargadas, muy por debajo de lo que
  tardaría el servidor lento).
- **Ruta por defecto** (ningún test escribe en el `data/` real): se copia
  `src/` a una carpeta temporal que hace de proyecto y se lanza la CLI real
  sin `--db` con `run_cli(..., project_root=<copia>)`, desde otra carpeta y
  desde la propia copia: las dos ejecuciones usan `<copia>/data/prices.db` y
  la otra carpeta queda vacía. `run_cli` solo permite omitir `--db` sobre una
  copia, nunca sobre el repo real.
- **Zona horaria:** el escenario "Registro de la captura" se prueba con
  relojes inyectados en varias zonas (UTC, Madrid, Nueva York) y con el reloj
  por defecto en un subproceso con `TZ=Asia/Tokyo`, comprobando que
  `downloaded_at` termina en `Z` y queda entre los instantes UTC medidos
  antes y después.
- **Fixtures:** `tests/fixtures/` contiene un recorte de una respuesta real y
  variantes escritas a mano para cada caso de error. El recorte real incluye
  al menos una estación con precios vacíos, una de Canarias (latitud ~28) y
  alguna con precio de GNC o GLP. La respuesta real la proporciona el usuario;
  hasta entonces todo avanza con fixtures escritas a mano.
- **Dependencias:** solo `pytest`, que ya forma parte del stack, en
  `requirements-dev.txt` (confirmado por el usuario), con la versión exacta
  que se instale (`pytest==X.Y.Z`) para que el entorno sea reproducible.

## Risks / Trade-offs

- [La API cambia nombres de campos fijos (p. ej. `Rótulo`)] → se guardarían
  vacíos sin aviso, por la decisión 7 de la proposal. Mitigación: los tests
  con el recorte real detectan el cambio cuando se actualice el fixture; una
  alerta automática queda fuera de alcance.
- [Respuestas sospechosamente cortas se guardan como captura válida] →
  aceptado; candidato para `add-scheduled-collection`.
- [Una respuesta de 12.000 estaciones en memoria] → unos pocos MB; aceptable.
- [El plazo de 120 s no basta un día de API lenta] → la ejecución falla sin
  guardar nada y se vuelve a lanzar a mano; es una constante fácil de cambiar.
- [Hilo de descarga abandonado tras agotar el plazo] → es un
  `threading.Thread(daemon=True)`: el proceso termina sin esperarlo. No toca la
  base de datos, así que no puede dejar nada a medias. Un test funcional
  comprueba que el proceso termina a tiempo (tarea 7.x).
- [`float` para precios] → errores de redondeo en la última cifra binaria;
  irrelevante para 3 decimales y para mostrar y comparar precios.
- [`--url` permite apuntar a otro servidor] → solo se usa en tests; el valor
  por defecto es siempre la URL oficial.
- [Temporal huérfano si el proceso muere de golpe (p. ej. `kill -9`) en la
  primera ejecución] → quedaría un `prices.db.tmp-<hex>`; no afecta a ninguna
  base existente y se puede borrar a mano.
- [Las coordenadas de una estación nunca se pueden vaciar] → consecuencia
  aceptada de la decisión de conservarlas (ver D5).

## Pendientes menores

Puntos que no causan fallos ni contradicciones; se resuelven durante la
implementación o en un cambio posterior sin otra ronda de revisión.

- Textos fijos que llegan como booleano, lista u objeto JSON: no decidido; la
  implementación los tratará como vacío y lo anotará aquí si aparece en la
  respuesta real.
- El mensaje de `DownloadTimeout` usa el plazo configurado (`se agotó el
  tiempo de descarga ({plazo} s)`), no un "120 s" fijo, para que siga siendo
  cierto con `--deadline`.
- El "por defecto `data/prices.db`" de la tarea 6.1 es
  `storage.DEFAULT_DB_PATH` (ruta absoluta), nunca una ruta relativa en el
  `default` de argparse.
- `__main__` lee `storage.DEFAULT_DB_PATH` en el momento de la llamada (no con
  `from .storage import DEFAULT_DB_PATH` a nivel de módulo), para que el
  `monkeypatch` del test en proceso de 7.4 surta efecto.
- En el test de 7.4 que imprime `DEFAULT_DB_PATH`, comparar rutas pasadas por
  `.resolve()`: en macOS `/tmp` y `/var` son enlaces simbólicos.
- Formato del aviso de `Fecha` (sin estación): `Aviso: Fecha: valor
  "2026-10-10 19:05" no válido`. Un valor que no es texto se muestra con
  `repr` (`40.416775`, `null`).
- En los avisos de precio, el campo es el nombre del combustible sin el
  prefijo (`Gasoleo A`), como en la spec.
- La fixture `with_warnings.json` lleva una `Fecha` válida y la otra
  coordenada válida, para que salgan exactamente 2 avisos.
- El bloqueo de red de `conftest.py` lanza `socket.gaierror`/`OSError`, para
  que un futuro test de "no se resuelve el nombre" acabe en `DownloadError`.
- `tests/http_server.py` usa `daemon_threads = True`, para que cerrar el
  servidor no espere a un manejador lento tras un test de plazo.
- `pyproject.toml`: `requires-python` va en `[project]`, que exige `name` y
  `version` (p. ej. `name = "precios-gasolineras"`, `version = "0.1.0"`).
- El README explica cómo lanzar la ingesta desde otra carpeta:
  `PYTHONPATH=<raíz> .venv/bin/python -m src.ingestion`, o con `cd` a la raíz.
  Así la usará la futura recogida programada.
- En la tarea 4.4, a nivel de `storage` se pasa el instante
  (`downloaded_at`); el reloj se inyecta en `main`.
- Redacción: en proposal.md, "`Fecha` de la API inválida" está bajo "Dato
  inválido en una estación", aunque es un dato de la respuesta.
- Una `Fecha` con espacios alrededor (`" 10/10/2026 19:05:23"`) se trata como
  inválida con aviso (`strptime` no los quita). Revisar si aparece en la
  respuesta real.

### Observado en la respuesta real (10/10/2026, 11.512 estaciones)

Con la spec actual el parser no da ningún aviso. Hay datos dudosos que sí se
aceptan y que podrían merecer un cambio de spec:

- 3 estaciones con coordenadas `0,000000 / 0,000000` (11988 Barcelona, 16499
  Cantabria, 12883 Madrid) y 1 con latitud y longitud intercambiadas (16268
  Pontevedra: `-8,659472 / 42,037472`). Están dentro del rango mundial, así que
  se guardan como válidas y saldrían en un mapa fuera de España.
- La API trae campos `Precio ...` que no son carburantes en sentido estricto
  (`Adblue`, en 2.954 estaciones; también `Amoniaco` y `Metanol`, vacíos hoy).
  Se guardan como un combustible más, según la decisión 3 de la proposal.
- 240 rótulos y 184 direcciones llevan espacios alrededor; se guardan tal cual,
  según la spec.
- `Fecha` llega con dos dígitos y sin espacios alrededor, sin BOM, y todos los
  valores son texto: los pendientes sobre formatos raros no se dan hoy.

**Decisión del usuario (10/10/2026):** la spec no cambia. Criterio: la ingesta
guarda lo que da la fuente; la limpieza para mostrar va en las capas de
consulta y mapa.

- Coordenadas sospechosas (0,0 e intercambiadas): se guardan tal cual.
  Candidato para `add-prices-api` / `add-map-view`: excluir del mapa las
  coordenadas fuera de España.
- `Adblue`, `Amoniaco` y `Metanol`: se guardan; la interfaz decidirá qué
  combustibles muestra.
- Espacios alrededor de los textos: se guardan tal cual; se recortarán al
  mostrarlos.

### Ejecución futura en Docker (con `--db` en un volumen)

Nada impide usarlo así; conviene tenerlo en cuenta al escribir ese cambio:

- Sin `--db`, la ruta por defecto sale de la ubicación del código
  (`/app/data/prices.db` si el código está en `/app`), que estaría dentro del
  contenedor y se perdería al recrearlo. En Docker hay que pasar siempre
  `--db` o montar el volumen justo en `<código>/data`.
- Montar una **carpeta** como volumen, no el archivo `prices.db` suelto: en la
  primera ejecución se crea `prices.db.tmp-<hex>` en la misma carpeta y se
  renombra con `os.replace`, lo que no funciona sobre un archivo montado
  directamente (y el `-journal` de SQLite también necesita la carpeta).
- SQLite necesita bloqueos de archivo fiables: volumen con nombre o carpeta
  local en la VPS, no una carpeta de red. En Docker Desktop (macOS), las
  carpetas del anfitrión montadas pueden tener bloqueos poco fiables; mejor un
  volumen con nombre en local.
- El usuario del contenedor necesita permiso de escritura en la carpeta del
  volumen (se crean el temporal, el `-journal` y, si falta, la carpeta).
- `docker stop` envía SIGTERM y Python termina sin limpiar: si ocurre durante
  la primera ejecución, puede quedar un `prices.db.tmp-<hex>` huérfano (la
  base existente nunca queda a medias, por la transacción).
- La CLI se lanza con `python -m src.ingestion`, así que la imagen necesita
  `WORKDIR` en la raíz del código o `PYTHONPATH` apuntando a ella.
- Zona horaria del contenedor: no afecta; `downloaded_at` se guarda siempre en
  UTC.
- Dos ejecuciones a la vez sobre el mismo volumen (p. ej. cron y una manual)
  quedan fuera de alcance; `BEGIN IMMEDIATE` serializa las escrituras sobre una
  base existente, pero dos primeras ejecuciones simultáneas podrían pisarse al
  renombrar el temporal.

### Tras la revisión de código (ronda 2)

- `Fecha`: `strptime` admite más de lo que dice la spec: minutos y segundos de
  una cifra (`9:5:3`) y varios espacios o un tabulador entre fecha y hora. Es
  inofensivo; si hiciera falta ajustarse a la spec, se añadiría una expresión
  regular estricta antes de `strptime`.
- Los avisos añaden el motivo entre paréntesis (`(formato no válido)`,
  `(fuera de rango)`…), algo que el formato original de D6 no recogía; D6 ya
  está actualizado.
- `tests/fixtures/make_fixtures.py` genera las respuestas escritas a mano: si
  se vuelve a ejecutar, sobrescribe esos archivos (no toca `real_sample.json`).
  Cualquier cambio en esas fixtures debe hacerse en el script, no a mano.

## Migration Plan

No hay despliegue ni datos previos. Pasos: crear `.gitignore`, ejecutar la
ingesta a mano por primera vez (crea `data/prices.db`). Para deshacer basta con
borrar el código; la base de datos local es del usuario y no se toca.
