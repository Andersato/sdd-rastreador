# Precios de Gasolineras

Recoge los precios de todas las gasolineras de España desde la API oficial del
Ministerio y los guarda como capturas con fecha y hora, para construir un
histórico propio (la API solo ofrece los precios actuales).

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

`requirements-dev.txt` solo contiene `pytest`, para los tests. La ingesta no
necesita ninguna dependencia externa.

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
| 3 | Ya hay otra ingesta en curso sobre la misma carpeta de datos. |
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

### Activarlo

Con `.env` y `data/` preparados y la imagen construida (ver arriba):

```sh
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
el programador está capturando, la manual termina enseguida con código 3
("ya hay otra ingesta en curso") sin llamar a la API. **No uses la ingesta
con `.venv` mientras el programador está activo**: el bloqueo no funciona
entre el Mac y Docker y podrían coincidir dos capturas.

### Solo para pruebas: otra URL de la API

`INGEST_API_URL` (en `.env`) hace que el programador pida los precios a otra
URL en lugar de a la API del Ministerio. Es una herramienta de pruebas (los
tests la usan con un servidor local): no la pongas en el uso normal.

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
