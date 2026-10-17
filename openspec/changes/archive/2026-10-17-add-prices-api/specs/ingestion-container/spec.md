# Spec Delta

## MODIFIED Requirements

### Requirement: Imagen con Python 3.12 sin archivos de desarrollo
La imagen de la ingesta SHALL usar Python 3.12 y poder ejecutar la ingesta.
MUST NOT incluir, al menos, dependencias de desarrollo (`pytest`), la carpeta
`tests/`, el entorno `.venv`, la carpeta `data/`, ninguna base de datos ni los
archivos de OpenSpec (`openspec/`), aunque existan en la carpeta del proyecto
al construirla.

#### Scenario: Versión de Python
- **WHEN** se construye la imagen y se consulta la versión de Python dentro de ella
- **THEN** la versión es 3.12.x

#### Scenario: Sin dependencias de desarrollo
- **WHEN** dentro de la imagen se intenta importar `pytest` o `httpx`
- **THEN** la importación falla porque no están instalados

#### Scenario: Dependencias de la API con versión fija
- **WHEN** dentro de la imagen se listan los paquetes instalados con sus versiones
- **THEN** aparte de `pip`, que trae la imagen base de Python, coinciden exactamente con `requirements.txt`, que fija FastAPI, uvicorn y todo lo que instalan con ellos (por ejemplo starlette, pydantic, pydantic-core, anyio, h11 y click), y FastAPI está instalado sin el extra `[standard]`

#### Scenario: Sin tests, entorno, datos ni OpenSpec
- **WHEN** se construye la imagen con la carpeta del proyecto conteniendo `tests/`, `.venv/`, `openspec/` y `data/prices.db` (4,3 MB, con la primera captura real)
- **THEN** en todo el sistema de archivos de la imagen no existe ningún archivo llamado `prices.db`, y en la carpeta de la aplicación no existe ningún archivo terminado en `.db` ni las carpetas `tests/`, `.venv/`, `openspec/` o `data/`

### Requirement: Construcción con un solo comando
`docker compose build` SHALL seguir construyendo la imagen que usan el
servicio `ingest`, el programador, la copia a mano de `database-backup` y el
servicio `api` de `prices-api`.

#### Scenario: Construcción
- **WHEN** se lanza `docker compose build` y después `docker compose up -d` y `docker compose run --rm ingest --help`
- **THEN** el programador, la API y la ingesta a mano usan la imagen recién construida, sin construir ninguna otra

#### Scenario: Copia a mano con la misma imagen
- **WHEN** se lanza `docker compose build` y después el comando de copia a mano
- **THEN** la copia a mano usa la imagen recién construida, sin construir ninguna otra

## ADDED Requirements

### Requirement: Ingesta, programador y copias sin depender de la API
La ingesta, el programador y las copias de seguridad SHALL funcionar sin
cargar FastAPI ni uvicorn: lanzarlos MUST NOT importar ninguna de las dos,
aunque estén instaladas en la imagen.

#### Scenario: Ingesta a mano
- **WHEN** dentro de la imagen se ejecuta la ingesta contra un servidor de pruebas con la respuesta guardada `valid_two_stations.json`
- **THEN** la captura se guarda y durante la ejecución no se ha cargado ningún módulo de `fastapi` ni de `uvicorn`

#### Scenario: Copia a mano
- **WHEN** dentro de la imagen se hace una copia a mano de una base de pruebas
- **THEN** la copia se guarda y durante la ejecución no se ha cargado ningún módulo de `fastapi` ni de `uvicorn`

#### Scenario: Comprobación del programador
- **WHEN** dentro de la imagen se lanza una comprobación del programador con la recogida desactivada
- **THEN** la comprobación termina como siempre y durante la ejecución no se ha cargado ningún módulo de `fastapi` ni de `uvicorn`
