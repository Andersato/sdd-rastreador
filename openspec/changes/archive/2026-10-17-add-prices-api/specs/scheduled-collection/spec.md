# Spec Delta

## MODIFIED Requirements

### Requirement: Servicio programador que se arranca una vez
`docker compose up -d` SHALL arrancar un servicio programador que se queda en
marcha y vuelve a arrancar solo cuando se reinicia Docker o el ordenador,
salvo que el usuario lo haya parado con `docker compose stop` o `down`.
`docker compose up -d` MUST NOT lanzar el servicio `ingest` ni el de la
copia a mano.

#### Scenario: Activación
- **WHEN** existen `.env` con `HOST_UID=501`, `HOST_GID=20` y `COLLECTION_ENABLED=true`, y las carpetas `./data` y `./backups`, y se lanza `docker compose up -d`
- **THEN** quedan en marcha exactamente dos contenedores, el del programador y el de la API de `prices-api`, los dos con usuario 501 y grupo 20, y no se crea ningún contenedor del servicio `ingest` ni del de la copia a mano

#### Scenario: Reinicio de Docker (verificación manual)
- **WHEN** el programador está en marcha, se reinicia el entorno de Docker (o el ordenador, con el entorno de Docker configurado para arrancar al iniciar sesión) y se espera a que Docker vuelva a estar disponible
- **THEN** `docker compose ps` muestra el programador en marcha sin que el usuario haya lanzado nada, y `docker compose logs` muestra la comprobación de arranque

#### Scenario: Reinicio del VPS (verificación manual)
- **WHEN** en el VPS el programador está en marcha con `COLLECTION_ENABLED=true` y se reinicia el servidor con `sudo reboot`
- **THEN** sin entrar a lanzar nada, `docker compose ps` muestra el programador en marcha y `docker compose logs` muestra la comprobación de arranque con la recogida activada

#### Scenario: Parado por el usuario (verificación manual)
- **WHEN** el usuario lanza `docker compose stop` y después reinicia el entorno de Docker
- **THEN** `docker compose ps` muestra el programador parado y `./data/prices.db` no tiene ninguna captura nueva
