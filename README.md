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

## Tests

```sh
.venv/bin/python -m pytest
```

Los tests nunca llaman a la API real: usan respuestas guardadas en
`tests/fixtures/` y un servidor HTTP local. Cualquier conexión a otra máquina
falla a propósito durante los tests.

## Fuente de los datos

Ministerio de Industria, Comercio y Turismo - Precios de carburantes en
estaciones de servicio.
