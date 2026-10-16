# Spec Delta

## ADDED Requirements

### Requirement: Programador incluido en la imagen con versión fija y verificada
La imagen SHALL incluir la herramienta de programación (supercronic) en una
versión fija, descargada para la arquitectura de la máquina (arm64 en el
Mac, amd64 en el VPS) y comprobada con su suma de comprobación. Si la suma no
coincide, la construcción MUST fallar.

#### Scenario: Construcción en el Mac
- **WHEN** se construye la imagen en un Mac con Apple Silicon (arm64)
- **THEN** la construcción termina bien y dentro de la imagen la herramienta de programación muestra la versión fijada

#### Scenario: Construcción para amd64
- **WHEN** se construye la imagen para la plataforma `linux/amd64`
- **THEN** la construcción termina bien con la misma versión fijada, en su variante amd64

#### Scenario: Suma de comprobación que no coincide
- **WHEN** la suma de comprobación fijada no coincide con el archivo descargado
- **THEN** la construcción falla con un error y no se genera la imagen

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
- **WHEN** `.env` indica `HOST_UID=0` y se lanza `docker compose up -d`
- **THEN** el programador no lanza ninguna ingesta ni hace ninguna petición a la API, y sigue en marcha mostrando el motivo en el log

#### Scenario: Base de datos de las ingestas programadas
- **WHEN** el programador lanza una ingesta correcta
- **THEN** la captura se guarda en `./data/prices.db` del host (`/app/data/prices.db` en el contenedor) y no se crea ninguna otra base de datos

### Requirement: Zona horaria de Madrid disponible en la imagen
La imagen SHALL incluir los datos de zona horaria necesarios para usar
Europe/Madrid con sus cambios de horario.

#### Scenario: Hora de Madrid dentro del contenedor
- **WHEN** dentro de un contenedor de la imagen con zona Europe/Madrid se pide la hora local del instante 2026-07-15T12:17:00Z
- **THEN** se obtiene 2026-07-15 14:17:00 +02:00

### Requirement: Construcción con un solo comando
`docker compose build` SHALL seguir construyendo la imagen que usan tanto el
servicio `ingest` como el programador.

#### Scenario: Construcción
- **WHEN** se lanza `docker compose build` y después `docker compose up -d` y `docker compose run --rm ingest --help`
- **THEN** los dos servicios usan la imagen recién construida, sin construir ninguna otra
