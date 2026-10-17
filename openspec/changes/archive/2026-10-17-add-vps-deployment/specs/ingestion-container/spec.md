# Spec Delta

## MODIFIED Requirements

### Requirement: Contexto de construcción sin archivos ajenos a la ingesta
La construcción de la imagen SHALL excluir del contexto que se envía a
Docker al menos `.venv/`, `data/`, `backups/`, `tests/`, `openspec/`, `.env` y cualquier
base de datos o temporal suyo (`*.db`, `*.db-journal`, `*.db.tmp-*`), de modo
que nunca se copien, ni siquiera de forma temporal, durante la construcción.

#### Scenario: Base de datos grande en ./data
- **WHEN** `./data/prices.db` ocupa 4,3 MB y se construye la imagen
- **THEN** la base de datos no forma parte del contexto de construcción ni de la imagen

#### Scenario: Configuración local fuera de la imagen
- **WHEN** existe `.env` con el usuario y grupo del host y se construye la imagen
- **THEN** la imagen no contiene ningún archivo `.env`

#### Scenario: Cambio solo en tests
- **WHEN** se modifica un archivo de `tests/` sin tocar `src/` y se reconstruye la imagen
- **THEN** los archivos de la carpeta de la aplicación en la imagen nueva y su contenido son idénticos a los de la anterior

#### Scenario: Copias de seguridad fuera de la imagen
- **WHEN** `./backups` contiene `prices-2026-10-17.db.gz` y se construye la imagen
- **THEN** ni el contexto de construcción ni la imagen contienen ningún archivo de `backups/`

### Requirement: Programador sin privilegios y con la base fijada
Lanzado sin Compose y sin indicar usuario, el programador SHALL ejecutarse
con usuario y grupo distintos de 0. Con usuario o grupo 0 configurado MUST
NOT lanzar ninguna ingesta y sigue en marcha ("Configuración no válida" de
`scheduled-collection`): diferencia intencionada con "Usuario del host
configurado y distinto de root", que sigue valiendo para `ingest`. Cada
ingesta usa siempre `/app/data/prices.db`.

#### Scenario: Programador lanzado sin Compose
- **WHEN** se lanza la imagen con `docker run --rm` en modo programador sin indicar usuario, y se consulta el usuario y el grupo de sus procesos
- **THEN** el número de usuario y el de grupo son distintos de 0

#### Scenario: Programador configurado como root
- **WHEN** `.env` indica `HOST_UID=0` y `COLLECTION_ENABLED=true`, y se lanza `docker compose up -d`
- **THEN** el programador no lanza ninguna ingesta ni hace ninguna petición a la API, y sigue en marcha mostrando el motivo en el log

#### Scenario: Base de datos de las ingestas programadas
- **WHEN** con `COLLECTION_ENABLED=true` el programador lanza una ingesta correcta
- **THEN** la captura se guarda en `./data/prices.db` del host (`/app/data/prices.db` en el contenedor) y no se crea ninguna otra base de datos

### Requirement: Construcción con un solo comando
`docker compose build` SHALL seguir construyendo la imagen que usan el
servicio `ingest`, el programador y la copia a mano de `database-backup`.

#### Scenario: Construcción
- **WHEN** se lanza `docker compose build` y después `docker compose up -d` y `docker compose run --rm ingest --help`
- **THEN** los dos servicios usan la imagen recién construida, sin construir ninguna otra

#### Scenario: Copia a mano con la misma imagen
- **WHEN** se lanza `docker compose build` y después el comando de copia a mano
- **THEN** la copia a mano usa la imagen recién construida, sin construir ninguna otra
