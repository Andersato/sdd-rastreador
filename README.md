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
se han descartado, como un precio mal escrito). Termina con código 0 si la
captura se ha guardado y con código 1 si ha fallado; en ese caso no se guarda
nada.

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

Docker con Compose v2 (Docker Desktop u OrbStack en macOS, Docker Engine en
Linux).

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
  con la captura completa, nunca a medias. Pueden quedar en `data/` archivos
  `prices.db-journal` o `prices.db.tmp-…`: son inofensivos y la siguiente
  ejecución los resuelve o los ignora.

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
