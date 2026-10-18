# Precios de Gasolineras

Recoge los precios de todas las gasolineras de España desde la API oficial del
Ministerio y los guarda como capturas con fecha y hora, para construir un
histórico propio (la API solo ofrece los precios actuales). Una API web de
solo lectura permite consultarlos (ver «API de consulta»).

## Requisitos

- Python 3.12 (la versión está fijada en `.python-version`).
  En macOS con Homebrew: `brew install python@3.12`.

## Preparar el entorno

Desde la carpeta del proyecto:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements.txt` fija FastAPI, uvicorn y todo lo que instalan, para la API
web; `requirements-dev.txt` lo incluye y añade `pytest` y `httpx` (este
último solo para los tests de la API). La ingesta y las copias no usan
ninguna dependencia externa.

## Recoger los precios

```sh
.venv/bin/python -m src.ingestion
```

Cada ejecución hace **una sola** petición a la API (sin reintentos, con un
tiempo límite de 120 s) y guarda una captura nueva. Al terminar muestra un
resumen: estaciones procesadas, precios guardados y avisos (datos sueltos que
se han descartado, como un precio mal escrito).

Código de salida:

| Código | Qué ha pasado |
|---|---|
| 0 | Captura guardada (aunque haya avisos). |
| 1 | Ha fallado (API caída, respuesta inválida, error al guardar…). |
| 3 | Ya hay otra ingesta o copia de seguridad en curso sobre la misma carpeta de datos. |
| 4 | Respuesta sospechosamente corta (ver abajo). |
| 130 | Interrumpida con Ctrl+C o `docker stop`. |

Salvo con 0, no se guarda nada y la base queda como estaba.

### Respuesta sospechosamente corta

Si la API devuelve menos del 80 % de las estaciones con precio de la última
captura (por ejemplo, 9.000 frente a 12.000), la captura **no se guarda**:
suele ser un fallo puntual de la API y guardarla dejaría un hueco en el
histórico. El mensaje indica las dos cifras y el porcentaje. Si de verdad
hay menos estaciones (y no es un fallo), se guarda a sabiendas con:

```sh
.venv/bin/python -m src.ingestion --accept-short-response
```

A partir de esa captura, las siguientes se comparan con ella.

### Una sola ingesta a la vez

Nunca se ejecutan dos ingestas a la vez sobre la misma carpeta de datos: la
segunda termina enseguida con código 3, sin llamar a la API. Esto vale entre
procesos del mismo sistema (dos ingestas con `.venv`, o dos contenedores),
pero **no** entre una ingesta con `.venv` en el Mac y otra dentro de Docker.
Por eso, **no lances la ingesta con `.venv` mientras el programador de Docker
está activo**: usa `docker compose run --rm ingest` (ver más abajo).

La base de datos va siempre a `data/prices.db` dentro de la carpeta del
proyecto, se lance desde donde se lance. Para lanzarla desde otra carpeta:

```sh
PYTHONPATH=/ruta/al/proyecto /ruta/al/proyecto/.venv/bin/python -m src.ingestion
```

Para usar otro archivo de base de datos:

```sh
.venv/bin/python -m src.ingestion --db /otra/ruta/precios.db
```

La base de datos no se sube al repositorio (`data/` está en `.gitignore`).

## Recoger los precios con Docker

Así la ingesta se lanza igual en el Mac y en un Linux, sin instalar Python.

### Requisitos

Docker con Compose v2: Colima en macOS, Docker Engine en Linux.

En macOS, Colima tiene que usar el montaje **virtiofs**, no sshfs. Con sshfs
los bloqueos de archivos no son fiables, y tanto SQLite como el bloqueo que
evita dos capturas a la vez dependen de ellos. Compruébalo con:

```sh
colima status        # debe mostrar «mountType: virtiofs»
```

Si muestra `sshfs`, pon `vmType: vz` y `mountType: virtiofs` en
`~/.colima/default/colima.yaml` y reinicia Colima (`colima restart`).

### Preparar (una vez por máquina)

Desde la carpeta del proyecto:

```sh
printf 'HOST_UID=%s\nHOST_GID=%s\n' "$(id -u)" "$(id -g)" > .env
mkdir -p data
```

- `.env` guarda tu número de usuario y de grupo. El contenedor se ejecuta con
  ellos, así que lo que escriba en `data/` queda a tu nombre, también en
  Linux. No se sube al repositorio. No se admite root (usuario o grupo 0).
- `data/` tiene que existir antes de lanzar: si falta, Docker no la crea
  (en Linux quedaría a nombre de root) y muestra
  `bind source path does not exist: …/data`.
- Si ya tienes `data/prices.db`, el contenedor la reutiliza y añade las
  capturas nuevas a continuación. Antes de la primera ejecución con Docker,
  haz una copia fuera de `data/` por si acaso:
  `cp data/prices.db ~/prices.db.copia-$(date +%Y%m%d)`.

### Construir la imagen

```sh
docker compose build
```

Repítelo **después de cada cambio del código**: `docker compose run` usa la
imagen que ya existe y no la reconstruye por sí solo. También necesita `.env`.

### Lanzar la ingesta

```sh
docker compose run --rm ingest
```

Hace lo mismo que sin Docker (una sola petición, mismo resumen) y termina con
el mismo código de salida: 0 si se ha guardado la captura y distinto de 0 si
ha fallado. El contenedor se borra al terminar; los datos se quedan en
`data/prices.db`.

- El resumen dice `Captura guardada en /app/data/prices.db`: es la ruta
  dentro del contenedor, que corresponde a `data/prices.db` de tu carpeta.
- Se pueden añadir argumentos de la ingesta, por ejemplo
  `docker compose run --rm ingest --help`. `--db` no se admite: la base de
  datos es siempre `data/prices.db` (cualquier otra se perdería al borrar el
  contenedor). La ayuda muestra `--db` igualmente; ignóralo.
- Si se corta a mitad (Ctrl+C o `docker stop`), la base queda como estaba o
  con la captura completa, nunca a medias, y no queda ningún archivo
  temporal. Solo si se mata a la fuerza (`docker kill`, un apagado brusco)
  pueden quedar en `data/` archivos `prices.db-journal` o `prices.db.tmp-…`:
  son inofensivos y la siguiente ejecución los resuelve o los ignora.
- Si la respuesta es sospechosamente corta (ver arriba) y quieres guardarla
  igualmente: `docker compose run --rm ingest --accept-short-response`.

## Recogida automática (programador)

El programador es un servicio que se queda en marcha y captura los precios
solo, cada 6 horas, aunque el ordenador se reinicie o se suspenda. Usa la
misma imagen y la misma `data/prices.db` que `docker compose run --rm ingest`.

### Una sola máquina recoge

Solo la máquina que tiene `COLLECTION_ENABLED=true` en su `.env` captura y
hace copias de seguridad. Hoy es **el VPS**. En cualquier otra (el Mac), sin
esa variable el programador arranca, dice en los logs que la recogida está
desactivada y **no hace nada**: así un `docker compose up -d` por costumbre
no parte el histórico en dos bases.

Por la misma razón, **no lances `docker compose run --rm ingest` contra la
API real en otra máquina**: esa captura iría a otra base distinta de la del
VPS. (Con `--url` hacia un servidor local, para pruebas, no hay problema.)

En `.env` de la máquina que recoge:

```sh
COLLECTION_ENABLED=true
```

Solo `true` la activa (sin distinguir mayúsculas). Vacía, ausente o `false`:
desactivada. Otro valor (`yes`, `1`…): configuración no válida, también
desactivada. Tras cambiarla, vuelve a lanzar `docker compose up -d`.

Cómo se preparó el VPS, cómo se migró el histórico y cómo se actualiza:
`docs/vps-deployment.md`.

### Activarlo

Con `.env`, `data/` y `backups/` preparados y la imagen construida (ver
arriba):

```sh
mkdir -p backups        # carpeta de las copias de seguridad; sin ella, up -d falla
docker compose up -d
```

Se hace **una vez**: Docker lo vuelve a arrancar solo al reiniciar el
ordenador o Docker (salvo que lo hayas parado tú). `docker compose up -d`
arranca solo el programador; no lanza una captura manual.

En macOS, Colima tiene que arrancar solo al iniciar sesión:

```sh
brew services start colima
```

`brew services list` debe mostrar `colima` como `started`. Si no, tras
reiniciar el Mac no habrá capturas hasta que lances `colima start`.

### Qué hace

- Comprueba nada más arrancar y después **cada hora en el minuto 17** (nunca
  a en punto, la hora punta de la API).
- En cada comprobación, si la última captura tiene 6 horas o más (con un
  margen de 15 minutos), o no hay ninguna, lanza una captura; si no, no hace
  nada y no llama a la API. Así, tras un reinicio o una suspensión recupera
  la captura en menos de una hora.
- Si la captura falla (API caída…), lo vuelve a intentar en la comprobación
  siguiente: como mucho una petición por hora.
- Las horas de los mensajes son de Madrid; las de la base, en UTC.

### Ver qué está haciendo

```sh
docker compose logs scheduler          # todo
docker compose logs -f scheduler       # en directo (Ctrl+C para salir)
```

Cada comprobación deja una línea con la hora y el resultado, por ejemplo:

```
2026-10-12 14:17:00 CEST · no toca capturar: última captura hace 2 h 10 min (intervalo 6 h)
2026-10-12 20:17:03 CEST · captura guardada (última captura hace 6 h 0 min, intervalo 6 h)
```

Los logs se rotan solos (como mucho 3 archivos de 10 MB).

**Respuesta corta.** Si una comprobación dice
`respuesta corta, no se ha guardado: 9.000 estaciones con precio frente a 12.000 …`,
la API ha devuelto muchas menos estaciones de lo normal y no se ha guardado
nada. Lo normal es que en la hora siguiente vuelva a ir bien. Si se repite y
crees que es real (hay menos estaciones), guárdala a sabiendas con:

```sh
docker compose run --rm ingest --accept-short-response
```

### Cambiar el intervalo

En `.env`, en horas enteras de 1 a 24 (por defecto, 6):

```sh
CAPTURE_INTERVAL_HOURS=4
```

Después vuelve a lanzar `docker compose up -d` para que se aplique. Con un
valor no válido, el programador no captura y lo dice en los logs.

### Pararlo y quitarlo

```sh
docker compose stop     # lo para (no vuelve a arrancar hasta `docker compose up -d`)
docker compose down     # lo para y borra el contenedor; los datos de data/ se quedan
```

Si estaba capturando, la captura se interrumpe sin dejar nada a medias.

### Ingesta manual con el programador activo

`docker compose run --rm ingest` sigue funcionando igual. Si en ese momento
el programador está capturando (o haciendo una copia de seguridad), la manual
termina enseguida con código 3 ("ya hay otra ingesta o copia en curso") sin
llamar a la API. **No uses la ingesta
con `.venv` mientras el programador está activo**: el bloqueo no funciona
entre el Mac y Docker y podrían coincidir dos capturas.

### Solo para pruebas: otra URL de la API

`INGEST_API_URL` (en `.env`) hace que el programador pida los precios a otra
URL en lugar de a la API del Ministerio. Es una herramienta de pruebas (los
tests la usan con un servidor local): no la pongas en el uso normal.

## Copias de seguridad

La máquina que recoge (la de `COLLECTION_ENABLED=true`, hoy el VPS) hace
también las copias de seguridad de `data/prices.db`. Van a la carpeta
`backups/`, fuera de `data/`, que tiene que existir antes de
`docker compose up -d` (`mkdir -p backups`). `backups/` no se sube al repo.

### Cuándo se hacen

- **Cada día a las 04:43** (hora de Madrid), la hace el programador.
- **Al arrancar el programador**, si no hay ninguna copia o la última tiene
  más de 26 horas (por ejemplo, tras tener el servidor apagado).
- Si a esa hora hay una captura en curso, espera como mucho 10 minutos; si
  no puede, la copia del día queda pendiente y se reintenta en cada
  comprobación horaria de ese día.
- **A mano**, cuando quieras (por ejemplo, antes de actualizar), también con
  el programador parado:

```sh
docker compose run --rm backup
```

Nunca se copia el archivo tal cual: se usa la copia segura de SQLite, se
comprueba con `PRAGMA integrity_check` y se comprime. La base de `data/` no
se modifica.

### Qué copias se guardan

Cada copia se llama `prices-AAAA-MM-DD.db.gz` (una por día; una segunda copia
el mismo día sustituye a la primera). Se conservan las **7 más recientes** y,
además, **4 semanales** (la última de cada una de las 4 semanas anteriores
con copia). Lo demás que haya en `backups/` con otro nombre no se toca.

### Cómo leer su línea en el log

En `docker compose logs scheduler` (o en la salida de la copia a mano):

```
2026-10-17 04:43:05 CEST · copia guardada: prices-2026-10-17.db.gz (912,4 MB, 1.204 capturas, integridad correcta); borradas: prices-2026-10-09.db.gz
2026-10-17 04:53:00 CEST · copia pendiente: otra ingesta o copia en curso; se reintenta en la próxima comprobación horaria
2026-10-17 04:43:00 CEST · copias desactivadas en esta máquina; se activan con COLLECTION_ENABLED=true en .env
```

Otras posibles: `copia no hecha: nada que copiar …` (no hay capturas),
`error en la copia: …` (con el motivo) y avisos al final de la línea
(`aviso: versión de estructura desconocida …`).

### Segunda copia en el Mac

El Mac se descarga las copias del VPS una vez al día y las verifica (el VPS
no puede borrar las del Mac):

```sh
.venv/bin/python -m src.backup.pull --host deploy@<IP_DEL_VPS>
```

Necesita **el `rsync` de Homebrew** (`brew install rsync`): es una
dependencia solo del Mac y solo de este script. El `rsync` de macOS
(`/usr/bin/rsync`) no funciona con el VPS, así que el script nunca lo usa y,
si no encuentra el de Homebrew, termina diciendo cómo instalarlo. La clave
SSH dedicada, la restricción en el VPS y cómo programarlo con `launchd`
están en `docs/offsite-backups.md`. Para restaurar una copia,
`docs/restore.md`.

## API de consulta

Una API web de **solo lectura** sobre `data/prices.db`: gasolineras cercanas,
ficha de una estación, combustibles y precio medio por provincia, siempre de
la última captura. Nunca modifica la base: monta `./data` en solo lectura y
abre la base solo para leer. Todas las respuestas llevan la atribución al
Ministerio y las de datos, la captura de la que salen.

### Arrancarla

Con el mismo `docker compose up -d` del programador (necesita `./data` y
`./backups`, como él). Arranca igual en el Mac (con la base local, aunque no
recoja) y en el VPS:

```sh
docker compose build
docker compose up -d
docker compose ps                         # scheduler y api en marcha
curl -s http://127.0.0.1:8000/api/health; echo
```

- URL: `http://127.0.0.1:8000/api/`. Documentación interactiva, con todas
  las rutas y sus parámetros: **`http://127.0.0.1:8000/api/docs`** (carga
  sus estilos de internet).
- Solo escucha en `127.0.0.1` de la máquina: nunca en la red. Si el puerto
  8000 ya está ocupado, `docker compose up -d` falla con el mensaje de
  Docker; hay que liberarlo.
- Su log, una línea por petición (las coordenadas de las búsquedas van
  redondeadas a 2 decimales): `docker compose logs api`.

### Usarla desde el Mac contra el VPS

En el VPS la API tampoco se publica hacia fuera: se usa con un **túnel SSH**
desde el Mac, abierto mientras se consulta:

```sh
ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>
```

Mientras está abierto, `http://127.0.0.1:8000/api/docs` del Mac es la API
del VPS. Se cierra con Ctrl+C. Si en el Mac está en marcha la API local (que
ya usa el 8000), se usa otro puerto: `-L 8001:127.0.0.1:8000` y
`http://127.0.0.1:8001/api/docs`. Más detalles en el runbook
([docs/vps-deployment.md](docs/vps-deployment.md)).

### Qué dice la salud

`GET /api/health` responde con `status`:

- `ok`: la base se lee y la última captura es reciente.
- `desactualizada`: la última captura tiene más de **dos veces
  `CAPTURE_INTERVAL_HOURS` más 1 hora** (13 h con el intervalo por defecto
  de 6 h). En el Mac, que no recoge, es lo normal.
- `configuracion_no_valida`: `CAPTURE_INTERVAL_HOURS` no es válido (el
  programador tampoco recoge).
- `error`, con código 503: no hay base, no se puede leer, está ocupada
  guardando una captura (se repite en unos segundos) o la última recogida
  quedó a medias.

## Web del mapa

Una página con un mapa para ver las gasolineras más baratas cerca de un
punto. La sirve la propia API, en el mismo puerto: no hay que arrancar nada
más que la API.

- En el Mac: **`http://127.0.0.1:8000/`**. En el Mac hay que arrancar solo
  la API, porque el servicio `scheduler` exige la carpeta `./backups` y no
  arranca sin ella (y en el Mac no recoge):

  ```sh
  docker compose up -d api
  ```
- Desde el Mac contra el VPS, con el túnel SSH abierto:

  ```sh
  ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>
  ```

  y `http://127.0.0.1:8000/`. Si el puerto 8000 del Mac ya está ocupado por
  la API local, se usa otro puerto: `-L 8001:127.0.0.1:8000` y
  `http://127.0.0.1:8001/`.

Al abrirla pide la ubicación; si no se concede, se elige el punto pinchando
en el mapa. Está pensada primero para el móvil: el mapa ocupa la pantalla y
la lista va en una hoja abajo («Ver lista»); en una pantalla ancha, la lista
va en un panel a la izquierda.

- **Internet:** el mapa necesita conexión para las teselas (las imágenes del
  mapa), que vienen de OpenStreetMap. Lo demás sale de la propia API.
- **Privacidad:** la ubicación y el punto pinchado solo se envían a la
  propia API, redondeados a 3 decimales (unos 100 m), y no se guardan en
  ningún sitio (tampoco en el navegador ni en la dirección de la página).
  OpenStreetMap recibe, como en cualquier mapa, las peticiones de las
  teselas de la zona que se ve. El navegador solo recuerda el combustible y
  el radio elegidos.

### Probar la web en un móvil real (antes de publicarla)

Para abrir la página del VPS desde un móvil sin publicarla, el Mac comparte
su túnel con la red local:

1. El móvil y el Mac deben estar en la misma Wi-Fi.
2. Averiguar la IP del Mac en la red local:

   ```sh
   ipconfig getifaddr en0      # si no devuelve nada, probar con en1
   ```

3. Abrir en el Mac un túnel compartido hacia el VPS y dejarlo abierto
   (`vps-gasolineras` es el alias de `deploy@<IP_DEL_VPS>` en
   `~/.ssh/config`):

   ```sh
   ssh -N -L 0.0.0.0:8001:127.0.0.1:8000 vps-gasolineras
   ```

   El `0.0.0.0` permite que otros dispositivos de la red usen el túnel; el
   puerto 8001 evita chocar con la API local del Mac. Si macOS pregunta por
   conexiones entrantes, hay que permitirlas.
4. En el móvil, abrir `http://<IP del Mac>:8001/`.

Limitaciones y avisos:

- **Sin ubicación automática:** los navegadores solo la dan con HTTPS o en
  `127.0.0.1`. En el móvil hay que pinchar en el mapa.
- **Cualquiera en esa Wi-Fi puede abrir la página** mientras el túnel
  compartido está abierto. Usarlo solo en redes de confianza, nunca en una
  Wi-Fi pública, y cerrarlo con Ctrl+C al terminar.
- Para el túnel normal (solo el Mac) sigue valiendo
  `ssh -N -L 8000:127.0.0.1:8000 vps-gasolineras`.

### Probarla en el Simulador de iOS (opcional)

Para ver la página en el Safari de un iPhone, con su muesca y su barra
inferior, sin publicarla: es una comprobación opcional, que no bloquea nada.

1. Con la API en marcha en el Mac (o el túnel al VPS abierto), abrir el
   Simulador: Xcode → Open Developer Tool → Simulator, y elegir un iPhone con
   muesca (File → Open Simulator).
2. En el Simulador, abrir Safari en `http://127.0.0.1:8000/`. El Simulador
   comparte la red del Mac, así que llega a su `127.0.0.1` y, por él, al
   túnel.
3. Darle una ubicación: Features → Location → Custom Location (por ejemplo,
   40.4168 y -3.7038) y aceptar el permiso en Safari.
4. Comprobar, en vertical y en horizontal (Device → Rotate Left): la hoja de
   la lista y «Ver lista», la ficha al tocar un precio, que los controles
   quedan abajo y que ni la muesca ni la barra inferior tapan nada.

## Protección del proyecto real frente a los agentes de Claude Code

Con el programador en marcha, ningún agente de Claude Code (la sesión
principal, el test-writer, el code-reviewer…) puede tocar el proyecto real.
Lo impide un hook `PreToolUse` configurado en `.claude/settings.json`, que
revisa cada comando Bash antes de ejecutarlo con
`.claude/hooks/guard_real_project.py`. Bloquea los comandos que:

- usan `docker compose` sobre el proyecto real, es decir, sin
  `-p pgtest-…`. Solo se permiten `docker compose logs` y
  `docker compose ps`, que son de solo lectura;
- paran, borran, matan o reinician contenedores que no sean de los tests
  (`pgtest-…`), incluido el del programador (`sdd-rastreador-scheduler-1`),
  o hacen limpiezas (`docker … prune`);
- reconstruyen, sustituyen o borran la imagen `precios-gasolineras-ingest`;
- borran, mueven o escriben en `data/`: `rm`, `mv`, `cp` hacia `data/`,
  redirecciones `>`, `sed -i`, `git clean -x`, la ingesta sin `--db` o con
  `--db` en `data/`… `sqlite3` solo se permite con `-readonly`.

El hook también mira dentro de `bash -c "…"`, `$(…)`, `xargs` y los comandos
encadenados, y tiene en cuenta los `cd`. Si no puede analizar un comando, o
falla él mismo, bloquea.

El agente recibe el mensaje de que **esas acciones las haces tú**: te dará el
comando exacto para que lo lances tú (en la terminal, o con `!` delante en
Claude Code, que no pasa por el hook). Los tests sí pueden usar Docker,
siempre con proyectos `pgtest-…` y la imagen `precios-gasolineras-ingest-test`,
porque se lanzan dentro de `pytest` y no como comandos sueltos.

Para revisarlo o desactivarlo temporalmente: `/hooks` en Claude Code. Sus
tests están en `tests/unit/test_guard_hook.py`.

## Tests

```sh
.venv/bin/python -m pytest
```

Los tests nunca llaman a la API real: usan respuestas guardadas en
`tests/fixtures/` y un servidor HTTP local. Cualquier conexión a otra máquina
falla a propósito durante los tests.

Los tests de la web (marca `browser`) usan los navegadores de Playwright: el
iPhone se emula con WebKit (el motor de Safari) y el Android y el escritorio,
con Chromium. Se descargan una vez:

```sh
.venv/bin/playwright install chromium
.venv/bin/playwright install webkit
```

Si falta alguno, sus tests se saltan con un aviso. Tampoco ellos salen del
equipo: las teselas del mapa se sustituyen por una imagen local.

Los tests de `tests/docker/` construyen la imagen y lanzan contenedores
(siempre contra el servidor local y con una carpeta de datos temporal). Se
saltan solos si Docker no está disponible, y se pueden excluir con:

```sh
.venv/bin/python -m pytest -m "not docker"
```

Al ejecutarlos se reconstruye la imagen local `precios-gasolineras-ingest`
con el código actual. Las comprobaciones que no se pueden automatizar en el
Mac están en [docs/container-checks.md](docs/container-checks.md).

## Fuente de los datos

Ministerio de Industria, Comercio y Turismo - Precios de carburantes en
estaciones de servicio.
