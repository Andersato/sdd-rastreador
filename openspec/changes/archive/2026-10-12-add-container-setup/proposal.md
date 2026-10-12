# Proposal

## Why

Hoy la ingesta solo se lanza con el Python y el `.venv` de cada máquina, así
que en el VPS habría que repetir a mano la instalación y podría comportarse
distinto que en local. Empaquetarla en un contenedor permite lanzarla igual
en el Mac y en un Linux, y es el paso previo a programarla
(`add-scheduled-collection`) y desplegarla (`add-vps-deployment`).

## What Changes

- Nueva imagen de la ingesta (Dockerfile) con Python 3.12 que no incluye
  `pytest`, los tests, el `.venv`, los datos ni los archivos de OpenSpec. El
  proceso nunca se ejecuta como root.
- Nuevo `docker-compose.yml` con un servicio `ingest` que se lanza una vez
  con `docker compose run --rm ingest`, hace una única ingesta (la misma
  petición única a la API que ya define `price-ingestion`) y termina con el
  mismo código de salida que la ingesta. Los argumentos que se añadan al
  comando (por ejemplo `--url` o `--help`) se pasan a la ingesta, salvo
  `--db`, que está fijado y se rechaza.
- La base de datos vive en la carpeta `./data` del host, montada en el
  contenedor, y se le pasa a la ingesta con `--db`. Se reutiliza la base
  existente `data/prices.db`, que ya contiene la primera captura real. Si
  `./data` no existe, la ejecución falla sin crear nada (en Linux Docker la
  crearía a nombre de root y luego no se podría escribir en ella).
- El usuario del contenedor es el mismo usuario (UID/GID) que lanza el
  servicio en el host, configurado en un archivo `.env` local. Si falta esa
  configuración o el usuario es root, la ejecución falla con un mensaje
  claro. Así la ingesta puede escribir en `./data` también en Linux, donde
  los permisos se aplican por número de usuario.
- Nuevo `.dockerignore` que excluye `.venv`, `data`, `tests`, `openspec`,
  `.env`, las bases de datos y sus temporales, y otros archivos locales
  (`.git`, `.claude`, `.idea`, cachés de Python, `CLAUDE.md`,
  `requirements-dev.txt`).
- README: cómo crear `.env` y `./data`, construir la imagen
  (`docker compose build`, que hay que repetir tras cada cambio del código,
  porque `docker compose run` no reconstruye la imagen por sí solo) y lanzar
  la ingesta.
- Lista de comprobación manual de los permisos en Linux, con los pasos para
  hacerla en una máquina Linux de OrbStack (`orb create ubuntu`).

No cambia el comportamiento de la ingesta en sí: se sigue lanzando igual sin
Docker y todos los requisitos de `price-ingestion` se mantienen. Dentro del
contenedor hay dos diferencias intencionadas con "Ubicación de la base de
datos" de `price-ingestion`:
- No se crea `./data` si no existe (allí se crea la carpeta de la base de
  datos), porque en Linux quedaría a nombre de root.
- No se acepta `--db` (allí permite usar otro archivo), porque la ruta está
  fijada a la carpeta montada y cualquier otra se perdería al eliminar el
  contenedor.

### Datos ya guardados

El cambio no modifica la estructura de la base de datos ni migra nada. El
contenedor abre el mismo archivo `data/prices.db` del host: la captura
existente, sus estaciones y precios se conservan y las nuevas capturas se
añaden a continuación. La imagen nunca incluye la base de datos, así que
reconstruirla o borrar el contenedor no afecta a los datos.

Las pruebas nunca usan `data/prices.db`: trabajan sobre una carpeta de datos
temporal.

### Verificación

- Tests automáticos con Docker para lo que se puede comprobar en el Mac:
  construyen la imagen y lanzan el servicio contra un servidor local con las
  respuestas guardadas en `tests/fixtures/`, sobre una carpeta de datos
  temporal. Si Docker no está disponible, se saltan.
- Comprobación manual de los escenarios de permisos en Linux en una máquina
  Linux de OrbStack (`orb create ubuntu`), porque Docker Desktop en macOS no
  aplica los permisos por número de usuario.
- Una única ejecución real, documentada, para comprobar que desde la imagen
  se conecta por HTTPS con la API del Ministerio (una sola petición).

### Fuera de alcance

- Ejecución periódica, `docker compose up` y zona horaria `Europe/Madrid`
  (programación y logs en hora de Madrid): `add-scheduled-collection`.
- Ejecuciones simultáneas de la ingesta (con o sin contenedor):
  `add-scheduled-collection`.
- Despliegue en el VPS y copias de seguridad de la base: `add-vps-deployment`.
- API web e interfaz.
- Ejecutar los tests dentro de un contenedor.
- Publicar la imagen en un registro (Docker Hub, GHCR…): se construye en
  cada máquina.

## Capabilities

### New Capabilities
- `ingestion-container`: cómo se empaqueta y se lanza la ingesta en un
  contenedor: contenido de la imagen, usuario sin privilegios, lanzamiento
  único con código de salida y argumentos, base de datos en `./data` del
  host y permisos de escritura en Linux.

### Modified Capabilities
<!-- Ninguna: la ingesta no cambia de comportamiento. -->

## Impact

- Archivos nuevos en la raíz: `Dockerfile`, `docker-compose.yml`,
  `.dockerignore`.
- `README.md`: nueva sección de Docker.
- Lista de comprobación manual de Linux (nuevo documento en el repo).
- Tests nuevos que necesitan Docker (se saltan si no está disponible).
- Código de `src/ingestion/`: sin cambios previstos en su comportamiento (ya
  acepta `--db` y `--url`).
- Dependencias: ninguna nueva de Python. Requiere Docker con Compose v2 en
  la máquina que lanza la ingesta (Docker Desktop u OrbStack en macOS,
  Docker Engine en Linux).
- `.env`: archivo local con el UID/GID del usuario del host; no se sube al
  repositorio.
- Base de datos: sin cambios de estructura; se reutiliza `data/prices.db`.
