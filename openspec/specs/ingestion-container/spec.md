# ingestion-container Specification

## Purpose

Empaquetar la ingesta de precios en un contenedor para lanzarla de la misma
forma en local (macOS) y en el servidor (Linux), guardando las capturas en la
base de datos de la carpeta `./data` del host.

## Requirements

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
- **WHEN** dentro de la imagen se intenta importar `pytest`
- **THEN** la importación falla porque `pytest` no está instalado

#### Scenario: Sin tests, entorno, datos ni OpenSpec
- **WHEN** se construye la imagen con la carpeta del proyecto conteniendo `tests/`, `.venv/`, `openspec/` y `data/prices.db` (4,3 MB, con la primera captura real)
- **THEN** en todo el sistema de archivos de la imagen no existe ningún archivo llamado `prices.db`, y en la carpeta de la aplicación no existe ningún archivo terminado en `.db` ni las carpetas `tests/`, `.venv/`, `openspec/` o `data/`

### Requirement: Ejecución con un usuario sin privilegios
La imagen y el servicio de ingesta SHALL ejecutar el proceso con un usuario
distinto de root: número de usuario distinto de 0, también cuando la imagen
se lanza sin Compose. Lanzada sin Compose, el grupo también MUST ser
distinto de 0.

#### Scenario: Imagen lanzada sin Compose
- **WHEN** se lanza la imagen con `docker run --rm` sin indicar usuario y con un comando que solo muestra el usuario y el grupo del proceso, sin ejecutar la ingesta
- **THEN** el número de usuario y el de grupo son distintos de 0

#### Scenario: Servicio lanzado con Compose
- **WHEN** el usuario del host 501 (grupo 20) lanza `docker compose run --rm ingest`
- **THEN** el proceso de la ingesta se ejecuta con número de usuario 501 y grupo 20

### Requirement: Usuario del host configurado y distinto de root
El servicio SHALL ejecutarse con el número de usuario y de grupo del usuario
del host, tomados de la configuración local del proyecto (archivo `.env`, que
no se sube al repositorio). Si falta esa configuración o el número de usuario
o de grupo es 0, la ejecución MUST terminar con código distinto de 0 y un mensaje que
explique el problema, sin hacer ninguna petición a la API y sin tocar `./data`.

#### Scenario: Configuración del usuario ausente
- **WHEN** no existe `.env`, o existe sin el número de usuario o de grupo, y se lanza `docker compose run --rm ingest`
- **THEN** el comando termina con código distinto de 0, con un mensaje que indica qué valor falta, no se hace ninguna petición a la API y `./data` queda exactamente igual que antes

#### Scenario: Usuario root
- **WHEN** `.env` indica número de usuario 0 y se lanza `docker compose run --rm ingest`
- **THEN** el comando termina con código distinto de 0, con un mensaje que indica que no se permite ejecutar como root, no se hace ninguna petición a la API y `./data` queda exactamente igual que antes

#### Scenario: Grupo root
- **WHEN** `.env` indica número de usuario 1001 y número de grupo 0, y se lanza `docker compose run --rm ingest`
- **THEN** el comando termina con código distinto de 0, con un mensaje que indica que no se permite el grupo root, no se hace ninguna petición a la API y `./data` queda exactamente igual que antes

### Requirement: Lanzamiento único con el código de salida de la ingesta
El comando `docker compose run --rm ingest` SHALL ejecutar una única
ingesta (una sola petición a la API, como define `price-ingestion`),
terminar al acabar y devolver el mismo código de salida que la ingesta. El
contenedor MUST eliminarse al terminar y MUST NOT reintentarse ni
reiniciarse automáticamente si falla.

#### Scenario: Ingesta correcta
- **WHEN** se lanza `docker compose run --rm ingest` y la API responde con HTTP 200 y un JSON válido con 2 estaciones
- **THEN** se hace una única petición a la API, se muestra el resumen ("Captura guardada en …", estaciones procesadas, precios guardados, avisos), el comando termina con código 0 y no queda ningún contenedor de la ejecución

#### Scenario: Ingesta correcta con avisos
- **WHEN** la API devuelve 2 estaciones, una de ellas con `"Precio Gasoleo A": "1,4a9"`
- **THEN** la captura se guarda, se muestra el aviso y el comando termina con código 0

#### Scenario: API caída
- **WHEN** se lanza `docker compose run --rm ingest` y la API responde con HTTP 503
- **THEN** se muestra el error de la ingesta, el comando termina con el mismo código que la ingesta (distinto de 0), no se hace ninguna segunda petición, el contenedor no se reinicia, no queda ningún contenedor de la ejecución y la base de datos queda exactamente igual que antes

#### Scenario: Sin conexión
- **WHEN** el contenedor no puede conectar con la API (el servidor rechaza la conexión o no se resuelve el nombre)
- **THEN** el comando termina con el mismo código que la ingesta (distinto de 0) y la base de datos queda exactamente igual que antes

#### Scenario: Respuesta inválida
- **WHEN** la API responde con HTTP 200 y `"ListaEESSPrecio": []`
- **THEN** el comando termina con el mismo código que la ingesta (distinto de 0) y no se guarda nada

#### Scenario: Interrupción durante la descarga
- **WHEN** `./data/prices.db` contiene 1 captura, la API tarda en responder y la ejecución se interrumpe (Ctrl+C o `docker stop`) antes de que termine la descarga
- **THEN** el comando termina con código distinto de 0 y `./data/prices.db` contiene solo la primera captura, intacta

#### Scenario: Interrupción durante el guardado
- **WHEN** `./data/prices.db` contiene 1 captura y la ejecución se interrumpe (Ctrl+C o `docker stop`) mientras se guarda la segunda
- **THEN** `./data/prices.db` contiene o bien solo la primera captura, intacta, o bien las dos completas; nunca una captura con parte de sus precios

### Requirement: Argumentos adicionales del comando
Los argumentos añadidos tras `docker compose run --rm ingest` SHALL pasarse
a la ingesta. La ruta de la base de datos está fijada por el servicio: si se
añade `--db`, la ejecución MUST terminar con código distinto de 0 y un
mensaje que lo explique, sin hacer ninguna petición a la API ni crear ni
modificar ninguna base de datos. Es una diferencia intencionada con
"Ubicación de la base de datos" de `price-ingestion`.

#### Scenario: Otra URL de la API
- **WHEN** se lanza `docker compose run --rm ingest --url <URL de un servidor local>` y ese servidor responde con una respuesta guardada de 2 estaciones
- **THEN** se hace una única petición, a ese servidor y no a la API del Ministerio, la captura se guarda en `./data/prices.db` del host y el comando termina con código 0

#### Scenario: Ayuda
- **WHEN** `./data` existe y se lanza `docker compose run --rm ingest --help`
- **THEN** se muestra la ayuda de la ingesta, el comando termina con código 0, no se hace ninguna petición a la API y `./data` queda exactamente igual que antes

#### Scenario: Intento de cambiar la base de datos
- **WHEN** se lanza `docker compose run --rm ingest --db /tmp/otra.db`
- **THEN** el comando termina con código distinto de 0, con un mensaje que indica que la base de datos no se puede cambiar en el contenedor, no se hace ninguna petición a la API, no se crea ninguna base de datos y `./data` queda exactamente igual que antes

#### Scenario: Intento de cambiar la base de datos con la forma --db=
- **WHEN** se lanza `docker compose run --rm ingest --db=/tmp/otra.db`
- **THEN** el resultado es el mismo que con `--db /tmp/otra.db`: código distinto de 0, el mismo mensaje, ninguna petición a la API, ninguna base de datos creada y `./data` exactamente igual que antes

### Requirement: Base de datos en la carpeta ./data del host
El servicio SHALL montar la carpeta `./data` del host (relativa a la carpeta
del proyecto) en el contenedor y pasar a la ingesta, con `--db`, la ruta de
`prices.db` dentro de esa carpeta montada. Las capturas MUST quedar en
`./data/prices.db` del host y conservarse al eliminar el contenedor o
reconstruir la imagen.

#### Scenario: Reutiliza la base existente sin perder nada
- **WHEN** `./data/prices.db` ya contiene 1 captura con sus estaciones y precios, y se lanza `docker compose run --rm ingest` con una API que responde correctamente
- **THEN** `./data/prices.db` contiene 2 capturas; la primera, sus estaciones y sus precios siguen intactos

#### Scenario: Primera ejecución con ./data vacía
- **WHEN** `./data` existe, está vacía y el usuario del host puede escribir en ella, y se lanza el servicio con una API que responde correctamente con 2 estaciones
- **THEN** se crea `./data/prices.db` con 1 captura y 2 estaciones, y en `./data` no queda ningún otro archivo

#### Scenario: Los datos sobreviven al contenedor y a la imagen
- **WHEN** se lanza una ingesta correcta, se reconstruye la imagen y se lanza otra ingesta correcta
- **THEN** `./data/prices.db` contiene las capturas de las dos ejecuciones

#### Scenario: Funciona igual en macOS
- **WHEN** en macOS `./data/prices.db` contiene 1 captura y se lanza el servicio con una API que responde correctamente
- **THEN** `./data/prices.db` pasa a tener 2 capturas, con la primera intacta, y en `./data` no queda ningún otro archivo

#### Scenario: Base de datos con versión de estructura desconocida
- **WHEN** `./data/prices.db` tiene la versión de estructura 7 y se lanza el servicio
- **THEN** el comando termina con un código distinto de 0 y `./data/prices.db` queda exactamente igual que antes

#### Scenario: Lanzado desde otra carpeta
- **WHEN** el proyecto está en `/Users/ana/sdd-rastreador` y se lanza `docker compose -f /Users/ana/sdd-rastreador/docker-compose.yml run --rm ingest` desde `/tmp`
- **THEN** la captura se guarda en `/Users/ana/sdd-rastreador/data/prices.db` y no se crea nada en `/tmp`

### Requirement: Carpeta ./data inexistente
Si la carpeta `./data` del host no existe, la ejecución SHALL terminar con
código distinto de 0 sin crearla, ni en macOS ni en Linux. Es una diferencia
intencionada con "Ubicación de la base de datos" de `price-ingestion`: en
Linux, la carpeta creada por Docker quedaría a nombre de root.

#### Scenario: ./data no existe
- **WHEN** el proyecto no tiene carpeta `./data` y se lanza `docker compose run --rm ingest`
- **THEN** el comando termina con código distinto de 0, con un mensaje que indica que falta la carpeta, no se hace ninguna petición a la API y `./data` sigue sin existir

### Requirement: Escritura en ./data en un host Linux
En un host Linux, el usuario del contenedor SHALL poder crear y modificar en
`./data` la base de datos y cualquier archivo que la ingesta cree allí,
cuando esa carpeta pertenece al usuario del host que lanza el servicio. Los
archivos creados MUST quedar a nombre de ese usuario del host, no de root.

#### Scenario: Usuario del host con número distinto de 1000
- **WHEN** en un Linux el usuario `deploy` (número de usuario 1001, grupo 1001) es dueño de `./data`, que está vacía, y lanza el servicio con una API que responde correctamente con 2 estaciones
- **THEN** se crea `./data/prices.db` con 1 captura, a nombre de 1001:1001

#### Scenario: Base existente en Linux
- **WHEN** en un Linux `./data/prices.db` pertenece al usuario 1001, que es quien lanza el servicio, y la API responde correctamente
- **THEN** la nueva captura se añade, el archivo sigue perteneciendo a 1001 y en `./data` no queda ningún otro archivo

#### Scenario: Carpeta sin permiso de escritura
- **WHEN** en un Linux `./data` existe, está vacía y pertenece a root sin permiso de escritura para otros, el usuario 1001 lanza el servicio y la API responde correctamente con 2 estaciones
- **THEN** el comando termina con código distinto de 0 mostrando que no se ha podido crear o escribir la base de datos, y `./data` sigue vacía

#### Scenario: Base de datos a nombre de otro usuario
- **WHEN** en un Linux `./data/prices.db` pertenece a root (por una ejecución anterior mal lanzada) sin permiso de escritura para otros, el usuario 1001 lanza el servicio y la API responde correctamente con 2 estaciones
- **THEN** el comando termina con código distinto de 0 mostrando que no se ha podido escribir en la base de datos, y `./data/prices.db` queda exactamente igual que antes

### Requirement: Contexto de construcción sin archivos ajenos a la ingesta
La construcción de la imagen SHALL excluir del contexto que se envía a
Docker al menos `.venv/`, `data/`, `tests/`, `openspec/`, `.env` y cualquier
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
