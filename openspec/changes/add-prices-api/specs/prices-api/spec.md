# Spec Delta

## Purpose

Ofrecer una API web de solo lectura sobre la base de precios recogida por la
ingesta, para consultar gasolineras cercanas, la ficha de una estación, los
combustibles y los precios por provincia de la última captura, sin poder
modificar nunca el histórico.

## ADDED Requirements

### Requirement: Servicio api que se arranca con el programador
`docker compose up -d` SHALL arrancar, además del programador, un servicio
`api` con la misma imagen, que se queda en marcha y vuelve a arrancar solo al
reiniciarse Docker o la máquina, salvo que el usuario lo haya parado. Funciona
igual con `COLLECTION_ENABLED` a `true`, vacía, ausente o no válida.

#### Scenario: Arranque en el VPS
- **WHEN** existen `.env` con `HOST_UID=1000`, `HOST_GID=1000` y `COLLECTION_ENABLED=true`, y las carpetas `./data` y `./backups`, y se lanza `docker compose up -d`
- **THEN** quedan en marcha el programador y la API, los dos con usuario 1000 y grupo 1000, y `GET /api/health` responde a través de `127.0.0.1:8000` del host

#### Scenario: Arranque en el Mac sin recogida
- **WHEN** `.env` tiene `HOST_UID=501`, `HOST_GID=20` y no tiene `COLLECTION_ENABLED`, y se lanza `docker compose up -d`
- **THEN** la API está en marcha y responde con los datos de `./data/prices.db` del Mac, aunque el programador no recoja

#### Scenario: Reinicio del VPS (verificación manual)
- **WHEN** la API está en marcha en el VPS y se reinicia el servidor con `sudo reboot`
- **THEN** sin lanzar nada, `docker compose ps` muestra la API en marcha y `GET /api/health` responde a través del túnel

#### Scenario: Parada
- **WHEN** la API está en marcha y se lanza `docker compose stop`
- **THEN** la API se para en menos de 10 s y `./data` queda exactamente igual que antes

### Requirement: API sin usuario root
El servicio `api` SHALL ejecutarse con el usuario y el grupo de `.env`. Si
el número de usuario o de grupo es 0, la API MUST NOT empezar a escuchar
peticiones ni abrir la base: termina con código distinto de 0 y un mensaje
en su log. A diferencia del programador, no se queda en marcha: Docker la
reintenta con esperas cada vez más largas.

#### Scenario: Usuario root
- **WHEN** `.env` indica `HOST_UID=0` y se lanza `docker compose up -d`
- **THEN** el log de la API dice que no se permite ejecutar la API como root (usuario 0) y que se revise `HOST_UID` en `.env`, el puerto 8000 no responde y `./data` queda exactamente igual que antes

#### Scenario: Grupo root
- **WHEN** `.env` indica `HOST_UID=1000` y `HOST_GID=0`
- **THEN** el log de la API dice que no se permite el grupo root (grupo 0) y que se revise `HOST_GID` en `.env`, y el puerto 8000 no responde

### Requirement: Puerto solo en 127.0.0.1 del host
El servicio `api` SHALL publicar su puerto únicamente en `127.0.0.1:8000` del
host, nunca en todas las interfaces ni en una IP pública: Docker añade sus
propias reglas y se saltaría `ufw`. Este cambio MUST NOT abrir ningún puerto
en `ufw`.

#### Scenario: Configuración de Compose
- **WHEN** se lanza `docker compose config` con el `.env` del VPS
- **THEN** el único puerto publicado por el proyecto es el 8000 del servicio `api`, con `host_ip: 127.0.0.1`

#### Scenario: Puerto escuchando en el VPS (verificación manual)
- **WHEN** la API está en marcha en el VPS y se lanza `sudo ss -tlnp` filtrando por el puerto 8000
- **THEN** solo aparece `127.0.0.1:8000`; no aparecen `0.0.0.0:8000` ni `[::]:8000`

#### Scenario: Acceso desde fuera (verificación manual)
- **WHEN** desde el Mac, sin túnel, se pide `http://<IP_DEL_VPS>:8000/api/health` con un tiempo límite de 5 s
- **THEN** la conexión falla, y `sudo ufw status` en el VPS sigue mostrando solo OpenSSH

### Requirement: Carpeta ./data montada en solo lectura
El servicio `api` SHALL montar `./data` en modo solo lectura y MUST NOT
montar `./backups`. Si `./data` no existe, Docker MUST NOT crearla.

#### Scenario: Montajes de la API
- **WHEN** se lanza `docker compose config`
- **THEN** el servicio `api` tiene un único montaje, `./data`, con `read_only: true` y sin crear la carpeta si falta, y no tiene `./backups`

#### Scenario: Escritura imposible
- **WHEN** dentro del contenedor de la API se intenta crear un archivo en la carpeta de datos
- **THEN** la escritura falla por ser un sistema de archivos de solo lectura

### Requirement: Base abierta solo para leer y sin crear archivos
La API SHALL abrir `./data/prices.db` solo para lectura, respetando los
bloqueos de SQLite, y MUST NOT crear, modificar ni borrar ningún archivo en
`./data`, incluidos diarios (`-journal`, `-wal`, `-shm`). MUST NOT cambiar
el modo de diario (nunca WAL) ni aplicar migraciones.

#### Scenario: Muchas consultas no cambian ./data
- **WHEN** con `./data/prices.db` de 8 capturas se hacen 100 peticiones variadas a todas las rutas de la API
- **THEN** la lista de archivos de `./data`, sus tamaños, fechas de modificación y contenido son exactamente los de antes, y `PRAGMA journal_mode` de la base sigue siendo `delete`

#### Scenario: Estructura desconocida
- **WHEN** `./data/prices.db` tiene `PRAGMA user_version` 2 y se pide `GET /api/fuels`
- **THEN** la respuesta es 503 con el código `base_no_compatible` y un mensaje que dice que la estructura de la base (versión 2) no es la que conoce la API (versión 1), y la base no se modifica

### Requirement: Base inexistente, vacía o ilegible
Si `./data/prices.db` no existe, la API SHALL responder 503 `sin_base` sin
crearla. Una base sin capturas, también con versión 0 y sin tablas, MUST dar
503 `sin_capturas`, y un archivo que no se puede leer como base, 503
`base_ilegible`. Cada petición vuelve a mirar la base: cuando el problema se
arregla, responde sin reiniciar la API.

#### Scenario: Sin base de datos
- **WHEN** `./data` está vacía y se pide `GET /api/stations/4375`
- **THEN** la respuesta es 503 con el código `sin_base` y el mensaje «todavía no hay base de datos: lanza la primera recogida», y `./data` sigue vacía

#### Scenario: Base sin capturas
- **WHEN** `./data/prices.db` tiene la estructura de la versión 1 pero ninguna captura, o es un archivo de 0 bytes, y se pide `GET /api/fuels`
- **THEN** la respuesta es 503 con el código `sin_capturas` y un mensaje que dice que la base aún no tiene capturas, y el archivo no cambia

#### Scenario: Archivo que no es una base
- **WHEN** `./data/prices.db` contiene el texto «hola»
- **THEN** la respuesta es 503 con el código `base_ilegible` y el mensaje «no se ha podido leer la base de datos»

#### Scenario: Primera captura con la API en marcha
- **WHEN** la API arrancó sin `./data/prices.db`, `GET /api/fuels` ha dado 503 `sin_base` y después la ingesta guarda la primera captura
- **THEN** la siguiente petición `GET /api/fuels` da 200 con esa captura, sin reiniciar la API

#### Scenario: Base restaurada desde una copia
- **WHEN** con la API en marcha se aparta `./data/prices.db` y se pone en su lugar una copia restaurada con 12 capturas, siguiendo el procedimiento de `database-backup`
- **THEN** la siguiente petición responde con la última captura de la base restaurada

### Requirement: Base ocupada por una recogida
Si la base tiene el bloqueo exclusivo que toma la ingesta al guardar, la API
SHALL esperar como mucho 2 s; si sigue bloqueada, MUST responder 503 con un
mensaje claro y `Retry-After: 5`. Un bloqueo de escritura reservado
(`BEGIN IMMEDIATE`), sin el exclusivo, no impide leer.

#### Scenario: Guardado más largo que la espera
- **WHEN** otro proceso mantiene la base con un bloqueo exclusivo de escritura durante 4 s y en ese momento se pide `GET /api/fuels`
- **THEN** a los 2 s (con un margen de 0,5 s) la respuesta es 503 con el código `base_ocupada`, el mensaje «la base de datos está ocupada guardando una captura; inténtalo de nuevo en unos segundos» y `Retry-After: 5`

#### Scenario: Guardado corto
- **WHEN** otro proceso mantiene la base con un bloqueo exclusivo de escritura durante 0,5 s y en ese momento se pide `GET /api/fuels`
- **THEN** la respuesta es 200 tras esperar como mucho 0,5 s (con un margen de 0,5 s), con los datos de la última captura terminada

#### Scenario: Recogida preparando la captura
- **WHEN** otro proceso ha empezado una escritura (`BEGIN IMMEDIATE`) sin llegar a guardar y se pide `GET /api/fuels`
- **THEN** la respuesta es 200 enseguida, con la última captura terminada

#### Scenario: Entre dos contenedores (Docker)
- **WHEN** en Docker, un contenedor de la imagen con `./data` montada mantiene un bloqueo exclusivo de escritura durante 4 s y se pide `GET /api/fuels` a la API
- **THEN** la respuesta es 503 `base_ocupada`, igual que sin Docker

#### Scenario: Recogida que quedó a medias
- **WHEN** existe `prices.db-journal` de una recogida cortada a mitad de guardar y se pide `GET /api/fuels`
- **THEN** la respuesta es 503 con el código `recogida_a_medias` y el mensaje «una recogida quedó a medias; se arreglará en la siguiente recogida de la máquina que recoge», y ni la base ni el diario se modifican

### Requirement: La API no impide guardar capturas
Todas las lecturas de la base de una misma petición SHALL caber en 2 s: si
una petición llega a ese límite, se corta y MUST responder 503 con el código
`consulta_demasiado_larga`. La espera por base ocupada no cuenta en ese
límite. Así la recogida, que espera hasta 5 s para guardar, nunca falla por
culpa de la API.

#### Scenario: Recogida mientras se consulta
- **WHEN** 4 clientes a la vez piden `GET /api/stations/nearby` sin parar durante 30 s y en ese tiempo se guarda una captura desde la ingesta
- **THEN** la captura se guarda correctamente y las respuestas pedidas después de guardarla salen de la captura nueva

#### Scenario: Consulta cortada
- **WHEN** las lecturas de una petición tardan más de 2 s (en los tests, simulado con una base preparada para ello)
- **THEN** se cortan, la respuesta es 503 con el código `consulta_demasiado_larga` y la base queda libre para escribir inmediatamente después

### Requirement: Lecturas de la base de una en una
La API SHALL hacer las lecturas de la base de una sola petición cada vez
dentro de su proceso, para que la recogida pueda guardar aunque lleguen
muchas peticiones a la vez. Una petición que lleva 2 s esperando su turno
MUST responder 503 con el código `api_ocupada` y `Retry-After: 5`. Esa espera
no cuenta en el límite de 2 s de lectura.

#### Scenario: Muchas peticiones a la vez
- **WHEN** 8 clientes piden sin parar `GET /api/stations/nearby` con radio 50 km sobre una base de 2.000 estaciones y la ingesta guarda una captura
- **THEN** la captura se guarda en menos de 1 s y las respuestas son 200

#### Scenario: Turno que no llega
- **WHEN** una petición tiene el turno de lectura durante más de 2 s y llega otra
- **THEN** la segunda responde, a los 2 s (con un margen de 0,5 s), 503 con el código `api_ocupada`, el mensaje «la API está atendiendo demasiadas consultas; inténtalo de nuevo en unos segundos» y `Retry-After: 5`, sin abrir la base

### Requirement: Datos siempre de capturas terminadas
Las consultas SHALL usar solo capturas completas, y todos los datos de una
respuesta MUST salir de la misma captura, la que indica `capture`. «La
última captura» es la guardada más recientemente, aunque su `Fecha` de la
API coincida con la de una captura anterior.

#### Scenario: Captura guardándose
- **WHEN** la última captura terminada es la del 2026-10-16T07:26:37Z y una recogida está en mitad de guardar otra
- **THEN** cada respuesta es 200 con la captura del 2026-10-16T07:26:37Z o 503 `base_ocupada`, nunca con una parte de la nueva

#### Scenario: Misma Fecha de la API
- **WHEN** las dos últimas capturas tienen la misma fecha de la fuente 2026-10-16T09:26:34 y se descargaron a las 07:26:37Z y 07:31:02Z
- **THEN** las consultas usan la descargada a las 07:31:02Z

### Requirement: Formato común de las respuestas correctas
Toda respuesta correcta de las rutas de datos SHALL ser JSON con
`attribution` (texto exacto «Ministerio de Industria, Comercio y Turismo -
Precios de carburantes en estaciones de servicio»), `capture` (`downloaded_at`
en UTC y `source_date` en hora de Madrid con su desfase, o `null`) y `data`.
La documentación es la única excepción.

#### Scenario: Captura de origen
- **WHEN** la última captura se descargó el 2026-10-16T07:26:37Z con fecha de la fuente 2026-10-16T09:26:34 (Madrid) y se pide `GET /api/fuels`
- **THEN** la respuesta incluye `"capture": {"downloaded_at": "2026-10-16T07:26:37Z", "source_date": "2026-10-16T09:26:34+02:00"}` y la atribución exacta

#### Scenario: Captura sin fecha de la fuente
- **WHEN** la última captura se descargó el 2026-11-02T05:17:03Z sin fecha de la fuente
- **THEN** la respuesta incluye `"source_date": null`

#### Scenario: Fecha de la fuente en horario de invierno
- **WHEN** la fecha de la fuente guardada es 2026-11-02T06:16:58
- **THEN** la respuesta la da como `2026-11-02T06:16:58+01:00`

### Requirement: Desfase de la fecha de la fuente en el cambio de hora
Cuando la fecha de la fuente cae en la hora que se repite al pasar al horario
de invierno, la API SHALL usar el desfase que deja ese instante más cerca de
`downloaded_at` de la misma captura. Cuando cae en la hora que no existe al
pasar al horario de verano, `source_date` MUST ser `null`.

#### Scenario: Hora repetida
- **WHEN** una captura tiene fecha de la fuente 2026-10-25T02:30:00 y se descargó el 2026-10-25T01:31:00Z
- **THEN** `source_date` es `2026-10-25T02:30:00+01:00` (01:30Z, a 1 min de la descarga; con +02:00 serían 00:30Z, a 61 min)

#### Scenario: Hora repetida, primera vez
- **WHEN** una captura tiene fecha de la fuente 2026-10-25T02:30:00 y se descargó el 2026-10-25T00:31:00Z
- **THEN** `source_date` es `2026-10-25T02:30:00+02:00`

#### Scenario: Hora que no existe
- **WHEN** una captura tiene fecha de la fuente 2027-03-28T02:30:00
- **THEN** `source_date` es `null` y `downloaded_at` se da como siempre

### Requirement: Formato común de los errores
Toda respuesta de error SHALL ser JSON con `attribution` y `error`, con un
`code` estable y un `message` en español. Parámetros no válidos: 422 con un
mensaje que nombra el parámetro; rutas inexistentes: 404; otro método que no
sea GET: 405; error inesperado: 500 sin detalles internos (rutas, SQL o trazas).

#### Scenario: Parámetro no válido
- **WHEN** se pide `GET /api/stations/nearby?lat=40,4168&lon=-3.7038&fuel=gasoleo-a`
- **THEN** la respuesta es 422 con el código `parametro_no_valido` y un mensaje que nombra `lat` y dice que se espera un número con punto decimal

#### Scenario: Ruta inexistente
- **WHEN** se pide `GET /api/precios` o `GET /`
- **THEN** la respuesta es 404 con el código `no_encontrado` y la atribución

#### Scenario: Método no permitido
- **WHEN** se pide `POST /api/fuels` o `DELETE /api/stations/4375`
- **THEN** la respuesta es 405 con el código `metodo_no_permitido`, la cabecera `Allow: GET` y la atribución, y la base no cambia

#### Scenario: Error inesperado
- **WHEN** una consulta falla por un error no previsto
- **THEN** la respuesta es 500 con el código `error_interno` y el mensaje «error interno de la API; revisa el log del servicio», sin rutas, SQL ni trazas, y el detalle queda en el log de la API

### Requirement: Parámetros antes que la base
La API SHALL comprobar los parámetros antes de abrir la base: con parámetros
no válidos MUST responder 422 aunque la base no exista, esté ocupada o no
tenga capturas.

#### Scenario: Parámetro no válido sin base
- **WHEN** `./data` está vacía y se pide `GET /api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=gasoleo-a&radius_km=51`
- **THEN** la respuesta es 422 `parametro_no_valido`, no 503

#### Scenario: Combustible desconocido con la base ocupada
- **WHEN** la base tiene un bloqueo exclusivo de escritura y se pide `GET /api/provinces/prices?fuel=diesel`
- **THEN** la respuesta es 422 `combustible_desconocido` enseguida, sin esperar a la base

### Requirement: Documentación interactiva
La API SHALL servir su documentación interactiva en `/api/docs` y la
descripción de sus rutas en `/api/openapi.json`, con parámetros, valores por
defecto y límites, y con la atribución al Ministerio en su descripción. La
raíz y las rutas fuera de `/api/` quedan libres para la futura interfaz.

#### Scenario: Documentación
- **WHEN** se pide `GET /api/openapi.json`
- **THEN** describe exactamente las rutas `/api/health`, `/api/fuels`, `/api/stations/nearby`, `/api/stations/{station_id}` y `/api/provinces/prices`, su descripción incluye la atribución, y `GET /api/docs` responde 200 con una página HTML

#### Scenario: Sin documentación en la raíz
- **WHEN** se pide `GET /docs` o `GET /openapi.json`
- **THEN** la respuesta es 404 `no_encontrado`

#### Scenario: Documentación desde el Mac (verificación manual)
- **WHEN** con el túnel SSH abierto y el Mac con acceso a internet (la página carga sus estilos y scripts de una CDN) se abre `http://127.0.0.1:8000/api/docs`
- **THEN** se ven las cinco rutas y se puede lanzar `GET /api/health` desde la página

### Requirement: Salud del servicio
`GET /api/health` SHALL responder 200 con `status` `ok` y la última captura
si puede leer la base y tiene capturas, o `desactualizada` si la última
captura se descargó hace más de dos veces el intervalo más 1 hora. Incluye
el umbral (`stale_after_hours`) y `unexposed_fuels`: combustibles con
precios en la última captura que no están en el catálogo. `status` va en la
raíz de la respuesta, también en los 503; el resto, en `data`.

#### Scenario: Todo correcto
- **WHEN** `.env` no tiene `CAPTURE_INTERVAL_HOURS`, son las 2026-10-16T10:00:00Z y la última captura se descargó a las 07:26:37Z
- **THEN** la respuesta es 200 con `status` `ok`, `stale_after_hours` 13, la captura de las 07:26:37Z y `unexposed_fuels` vacía

#### Scenario: Captura antigua
- **WHEN** el intervalo es el de por defecto, son las 2026-10-16T20:27:00Z y la última captura se descargó a las 07:26:37Z (hace 13 h 0 min 23 s)
- **THEN** la respuesta es 200 con `status` `desactualizada` y la captura de las 07:26:37Z

#### Scenario: Justo en el umbral
- **WHEN** el intervalo es el de por defecto y la última captura se descargó hace exactamente 13 horas
- **THEN** `status` es `ok`

#### Scenario: Otro intervalo
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS=12` y la última captura se descargó hace 24 h 30 min
- **THEN** `stale_after_hours` es 25 y `status` es `ok`

#### Scenario: Captura con fecha en el futuro
- **WHEN** la última captura tiene `downloaded_at` 2 horas por delante del reloj
- **THEN** `status` es `ok`

#### Scenario: Combustible fuera del catálogo
- **WHEN** la última captura tiene precios de «Metanol» en 2 estaciones
- **THEN** `unexposed_fuels` es `[{"name": "Metanol", "stations": 2}]` y `status` sigue siendo `ok`

#### Scenario: Errores de la salud
- **WHEN** `GET /api/health` responde 503 por cualquier motivo (`sin_base`, `sin_capturas`, `base_ilegible`, `base_no_compatible`, `base_ocupada`, `recogida_a_medias`, `consulta_demasiado_larga` o `api_ocupada`)
- **THEN** la respuesta lleva, además de `attribution` y `error`, `"status": "error"`

### Requirement: Intervalo no válido en la salud
La API SHALL leer `CAPTURE_INTERVAL_HOURS` con las mismas reglas que el
programador (horas enteras de 1 a 24; vacía o ausente, 6). Con un valor no
válido, `GET /api/health` MUST responder 200 con `status`
`configuracion_no_valida` y un mensaje con el valor recibido, salvo que
haya un problema de la base, que gana (503); el resto de rutas funcionan igual.

#### Scenario: Intervalo imposible
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS=25`
- **THEN** `GET /api/health` responde 200 con `status` `configuracion_no_valida`, `stale_after_hours` `null`, la última captura y un mensaje que dice que se recibió «25» y se admiten horas enteras de 1 a 24, y `GET /api/fuels` responde 200 normalmente

#### Scenario: Intervalo no válido y sin base
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS=25` y `./data` está vacía
- **THEN** `GET /api/health` responde 503 `sin_base` con `"status": "error"`

#### Scenario: Formas admitidas
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS= 3 `
- **THEN** `stale_after_hours` es 7

### Requirement: Catálogo de combustibles
La API SHALL exponer solo los combustibles de un catálogo fijo, cada uno con
nombre tal como lo guarda la ingesta, identificador corto, unidad y tipo
(`combustible` o `aditivo`). Un combustible fuera del catálogo MUST NOT
aparecer en ninguna respuesta salvo en la salud. Los combustibles nunca se
mezclan: cada cifra corresponde a un solo combustible.

#### Scenario: Contenido del catálogo
- **WHEN** se consulta el catálogo
- **THEN** tiene exactamente estos 21 nombres e identificadores: Adblue (`adblue`), Biodiesel (`biodiesel`), Bioetanol (`bioetanol`), Biogas Natural Comprimido (`biogas-natural-comprimido`), Biogas Natural Licuado (`biogas-natural-licuado`), Diésel Renovable (`diesel-renovable`), Gas Natural Comprimido (`gas-natural-comprimido`), Gas Natural Licuado (`gas-natural-licuado`), Gases licuados del petróleo (`gases-licuados-del-petroleo`), Gasoleo A (`gasoleo-a`), Gasoleo B (`gasoleo-b`), Gasoleo Premium (`gasoleo-premium`), Gasolina 95 E10 (`gasolina-95-e10`), Gasolina 95 E25 (`gasolina-95-e25`), Gasolina 95 E5 (`gasolina-95-e5`), Gasolina 95 E5 Premium (`gasolina-95-e5-premium`), Gasolina 95 E85 (`gasolina-95-e85`), Gasolina 98 E10 (`gasolina-98-e10`), Gasolina 98 E5 (`gasolina-98-e5`), Gasolina Renovable (`gasolina-renovable`) e Hidrogeno (`hidrogeno`); no incluye Amoniaco ni Metanol

#### Scenario: Unidades
- **WHEN** se consultan las unidades del catálogo
- **THEN** Gas Natural Comprimido, Gas Natural Licuado, Biogas Natural Comprimido, Biogas Natural Licuado e Hidrogeno están en `€/kg`, y los otros 16 en `€/l`

#### Scenario: AdBlue
- **WHEN** se consulta el tipo de Adblue
- **THEN** es `aditivo`, con unidad `€/l`; los otros 20 son `combustible`, y `adblue` se admite como `fuel` en todas las consultas

#### Scenario: Combustible fuera del catálogo en una estación
- **WHEN** la estación "4375" tiene en la última captura precios de Gasoleo A (1.459) y Metanol (1.200)
- **THEN** su ficha solo muestra Gasoleo A

### Requirement: Combustible obligatorio por su identificador
Las consultas que trabajan con un combustible SHALL exigir el parámetro
`fuel`, sin valor por defecto, con uno de los identificadores del catálogo
escrito exactamente igual (en minúsculas). Un `fuel` ausente MUST dar 422
`parametro_no_valido` y uno desconocido, 422 `combustible_desconocido`.

#### Scenario: Nombre en lugar del identificador
- **WHEN** se pide `GET /api/provinces/prices?fuel=Gasoleo%20A` o `fuel=GASOLEO-A`
- **THEN** la respuesta es 422 con el código `combustible_desconocido` y un mensaje que remite a `/api/fuels`

#### Scenario: Combustible fuera del catálogo pedido por identificador
- **WHEN** se pide `GET /api/provinces/prices?fuel=metanol`
- **THEN** la respuesta es 422 con el código `combustible_desconocido`

#### Scenario: Falta el combustible
- **WHEN** se pide `GET /api/stations/nearby?lat=40.4168&lon=-3.7038` o `GET /api/provinces/prices`
- **THEN** la respuesta es 422 con el código `parametro_no_valido` y un mensaje que nombra `fuel` y remite a `/api/fuels`

### Requirement: Lista de combustibles
`GET /api/fuels` SHALL devolver en `data` los 21 combustibles del catálogo,
cada uno con `name`, `slug`, `unit`, `kind` y `stations` (estaciones que lo
venden en la última captura, 0 si ninguna), ordenados por `stations` de
mayor a menor y, a igualdad, por `slug`.

#### Scenario: Datos de prueba
- **WHEN** la última captura de una base de prueba tiene Gasoleo A en 3 estaciones, Gasolina 95 E5 en 2, Hidrogeno en 1 y Adblue en 1
- **THEN** `data` empieza por `{"name": "Gasoleo A", "slug": "gasoleo-a", "unit": "€/l", "kind": "combustible", "stations": 3}`, sigue `gasolina-95-e5` (2), después `adblue` (1, `aditivo`) y `hidrogeno` (1, `€/kg`), y luego los otros 17 con 0, ordenados por `slug`

#### Scenario: Datos reales (verificación manual)
- **WHEN** se descomprime la copia `~/Backups/precios-gasolineras/prices-2026-10-17.db.gz` en una carpeta temporal nueva y se lanza la API contra ella
- **THEN** `GET /api/fuels` da el mismo número de estaciones por combustible que una consulta directa a esa copia sobre su última captura (el 16/10/2026 eran, por ejemplo, 11270 para `gasoleo-a`), y la copia no se modifica

### Requirement: Limpieza de textos al responder
La API SHALL devolver los textos de las estaciones (rótulo, dirección,
municipio, provincia y horario) sin espacios en blanco al principio ni al
final (también tabuladores y espacios no separables), dejando tal cual los
del interior, y un texto que queda vacío como `null`. La base MUST NOT
modificarse.

#### Scenario: Texto con espacios
- **WHEN** la estación "5120" tiene guardado el rótulo " GALP "
- **THEN** la API devuelve `"brand": "GALP"` y en la base sigue " GALP "

#### Scenario: Tabuladores y espacios interiores
- **WHEN** la estación "5120" tiene guardada la dirección "\tCALLE  MAYOR, 1 "
- **THEN** la API devuelve `"address": "CALLE  MAYOR, 1"`, con los dos espacios interiores

#### Scenario: Texto vacío
- **WHEN** la estación "5120" tiene el horario vacío o solo con espacios
- **THEN** la API devuelve `"schedule": null`

### Requirement: Coordenadas fuera de España
La API SHALL tratar como desconocidas las coordenadas de una estación que no
caen en ninguna zona de España: Península (35,9 a 43,9 de latitud y -9,4 a
3,4 de longitud), Baleares (38,6 a 40,1 y 1,1 a 4,4), Canarias (27,6 a 29,5 y
-18,2 a -13,3), Ceuta (35,86 a 35,93 y -5,39 a -5,27) y Melilla (35,26 a 35,32
y -2,98 a -2,92), extremos incluidos.

#### Scenario: Coordenadas (0, 0)
- **WHEN** la estación "11988" de Barcelona tiene latitud 0.0 y longitud 0.0
- **THEN** su ficha devuelve `"latitude": null` y `"longitude": null`

#### Scenario: Latitud y longitud intercambiadas
- **WHEN** la estación "16268" de Tui tiene latitud -8.659472 y longitud 42.037472
- **THEN** se trata igual que unas coordenadas desconocidas; la API no intenta corregirlas

#### Scenario: Estación justo fuera de una zona
- **WHEN** la última captura tiene Gasoleo A en "2001" en (42.0, -9.45), al oeste del rectángulo de la Península, y en "2002" en (42.0, -9.30), y se buscan cercanas en (42.0, -9.35) con `radius_km=10`
- **THEN** solo aparece "2002" (4.13 km); "2001", a 8.26 km, no aparece aunque está dentro del radio

#### Scenario: Estación de Canarias
- **WHEN** una estación tiene latitud 28.1235 y longitud -15.4363 (Las Palmas de Gran Canaria)
- **THEN** sus coordenadas se devuelven tal cual

#### Scenario: Estación sin coordenadas en la media por provincia
- **WHEN** la estación "11988" vende Gasoleo A a 1.499 en la última captura
- **THEN** su precio cuenta en la media de BARCELONA

### Requirement: Gasolineras cercanas
`GET /api/stations/nearby` SHALL recibir `lat`, `lon`, `fuel`, `radius_km`
(por defecto 5) y `limit` (por defecto 20), y devolver las estaciones con ese
combustible en la última captura a una distancia en línea recta (esfera de
6371 km de radio) menor o igual que el radio, ordenadas por precio, luego por
distancia sin redondear y luego por identificador.

#### Scenario: Búsqueda en Madrid
- **WHEN** la última captura tiene Gasoleo A en "1001" a 1.459 en (40.4250, -3.7038), "1002" a 1.459 en (40.4168, -3.6800), "1003" a 1.399 en (40.4400, -3.7300), "1004" a 1.299 en (40.4630, -3.7038), "1006" a 1.199 en (0, 0), y "1005" en (40.416775, -3.703790) solo vende Gasolina 95 E5, y se pide `lat=40.416775&lon=-3.703790&fuel=gasoleo-a`
- **THEN** `data.stations` tiene, en este orden, "1003" (1.399, 3.4 km), "1001" (1.459, 0.91 km) y "1002" (1.459, 2.01 km); "1004" queda fuera por estar a 5.14 km, "1006" por no tener coordenadas válidas y "1005" por no vender Gasoleo A

#### Scenario: Forma de la respuesta
- **WHEN** se hace la búsqueda anterior
- **THEN** `data` tiene `fuel` (`name`, `slug`, `unit`, `kind`), `center` (`lat` 40.416775, `lon` -3.70379), `radius_km` 5, `limit` 20, `total` 3 y `stations`; cada estación tiene `id`, `brand`, `address`, `municipality`, `province`, `latitude`, `longitude`, `price`, `unit` y `distance_km` redondeada a 2 decimales, con la mitad hacia arriba (3.4 para "1003")

#### Scenario: Radio mayor
- **WHEN** se repite la búsqueda con `radius_km=10`
- **THEN** el primero es "1004" (1.299, 5.14 km) y después "1003", "1001" y "1002"

#### Scenario: Mismo precio y distancias que se redondean igual
- **WHEN** "3001" y "3002" venden a 1.459 y están a 2.0141 km y 2.0112 km
- **THEN** sale primero "3002" y las dos muestran `distance_km` 2.01

#### Scenario: Límite de resultados
- **WHEN** hay 30 estaciones con Gasoleo A dentro del radio y se pide sin `limit`
- **THEN** `stations` tiene las 20 primeras según el orden y `total` es 30

#### Scenario: Sin resultados
- **WHEN** ninguna estación con Gasoleo A está dentro del radio
- **THEN** la respuesta es 200 con `total` 0 y `stations` vacía

### Requirement: Límites de la búsqueda de cercanas
`lat` y `lon` SHALL ser números finitos de -90 a 90 y de -180 a 180;
`radius_km`, mayor que 0 y como mucho 50; `limit`, entero de 1 a 100. Fuera
de eso MUST dar 422 `parametro_no_valido`, sin recortar valores. Un punto
válido fuera de las zonas de España da 422 `fuera_de_espana`.

#### Scenario: Radio demasiado grande
- **WHEN** se pide `radius_km=51`
- **THEN** la respuesta es 422 con el código `parametro_no_valido` y un mensaje que dice que el radio máximo es 50 km

#### Scenario: Radio cero o negativo
- **WHEN** se pide `radius_km=0` o `radius_km=-3`
- **THEN** la respuesta es 422 con el código `parametro_no_valido`

#### Scenario: Límite fuera de rango
- **WHEN** se pide `limit=0`, `limit=101` o `limit=2.5`
- **THEN** la respuesta es 422 con el código `parametro_no_valido` y un mensaje que dice que el límite es un entero de 1 a 100

#### Scenario: Coordenadas imposibles
- **WHEN** se pide `lat=91`, `lon=200`, `lat=nan` o `lat=inf`
- **THEN** la respuesta es 422 con el código `parametro_no_valido` y un mensaje que nombra el parámetro

#### Scenario: Punto fuera de España
- **WHEN** se pide `lat=48.8566&lon=2.3522` (París)
- **THEN** la respuesta es 422 con el código `fuera_de_espana`

#### Scenario: Punto en Portugal dentro del rectángulo
- **WHEN** se pide `lat=38.7223&lon=-9.1393` (Lisboa, dentro del rectángulo de la Península)
- **THEN** la respuesta es 200 con las estaciones españolas que haya en el radio (ninguna, en este caso)

### Requirement: Ficha de una estación
`GET /api/stations/{station_id}` SHALL devolver en `data` los datos fijos de
la estación (`id`, `brand`, `address`, `municipality`, `province`,
`schedule`, `latitude`, `longitude`) y `prices` con sus precios de la última
captura de combustibles del catálogo (`slug`, `name`, `unit`, `kind`,
`price`), ordenados por `slug`.

#### Scenario: Estación con precios
- **WHEN** la estación "4375" (REPSOL, CALLE MAYOR, 1, Madrid, MADRID, 40.416775, -3.70379, «L-D: 24H») tiene en la última captura Gasolina 95 E5 a 1.529 y Gasoleo A a 1.459
- **THEN** la respuesta es 200 con esos datos y `prices` con `gasoleo-a` (1.459 €/l) y después `gasolina-95-e5` (1.529 €/l)

#### Scenario: Estación sin precios en la última captura
- **WHEN** la estación "5120" está guardada pero no aparece en la última captura
- **THEN** la respuesta es 200 con sus datos fijos y `"prices": []`

#### Scenario: Estación inexistente
- **WHEN** se pide `GET /api/stations/99999` y no existe esa estación
- **THEN** la respuesta es 404 con el código `estacion_no_encontrada` y un mensaje que incluye «99999»

### Requirement: Precio medio por provincia
`GET /api/provinces/prices?fuel=` SHALL devolver en `data` el combustible
(`fuel` con `name`, `slug`, `unit`, `kind`) y `provinces`: por cada provincia
con estaciones que lo venden en la última captura, `province`, `average`,
`min`, `max` y `stations`. Se agrupa por el nombre recortado; las estaciones
sin provincia no cuentan.

#### Scenario: Media de Madrid
- **WHEN** en MADRID venden Gasoleo A en la última captura "1001" a 1.459, "1002" a 1.459, "1003" a 1.399 y "1004" a 1.299
- **THEN** MADRID aparece con `average` 1.404, `min` 1.299, `max` 1.459 y `stations` 4, y `fuel.unit` es `€/l`

#### Scenario: Mismo nombre con espacios
- **WHEN** "1001" tiene guardada la provincia «MADRID» y "1002" «MADRID »
- **THEN** las dos cuentan en una sola provincia «MADRID»

#### Scenario: Provincia vacía
- **WHEN** "1007" vende Gasoleo A y su provincia está vacía o solo tiene espacios
- **THEN** no aparece en ninguna provincia ni en ningún recuento

#### Scenario: Provincia sin ese combustible
- **WHEN** en SORIA ninguna estación vende Hidrogeno
- **THEN** SORIA no aparece en `GET /api/provinces/prices?fuel=hidrogeno`

### Requirement: Redondeo y orden de las provincias
La media SHALL redondearse a 3 decimales con la mitad hacia arriba. Las
provincias MUST ordenarse por media de menor a mayor y, a igualdad, por su
nombre comparado carácter a carácter tal como está guardado (así «ÁVILA» va
después de «ZAMORA»).

#### Scenario: Media con mitad
- **WHEN** en LUGO venden Gasoleo A dos estaciones, a 1.404 y a 1.405
- **THEN** `average` es 1.405

#### Scenario: Empate de media
- **WHEN** ÁVILA y ZAMORA tienen media 1.450 y CORUÑA (A) 1.449
- **THEN** el orden es CORUÑA (A), ZAMORA, ÁVILA

### Requirement: Log de la API limitado y sin ubicaciones exactas
El log del servicio `api` SHALL tener una línea por petición (hora de Madrid,
método, ruta, parámetros y código de respuesta), con las coordenadas de las
búsquedas redondeadas a 2 decimales, y MUST quedarse como mucho en 3
archivos de 10 MB, como el del programador.

#### Scenario: Búsqueda en el log
- **WHEN** se pide `GET /api/stations/nearby?lat=40.416775&lon=-3.703790&fuel=gasoleo-a` y responde 200
- **THEN** el log tiene una línea con `lat=40.42`, `lon=-3.70`, `fuel=gasoleo-a` y el código 200, y en ningún sitio del log aparecen `40.416775` ni `-3.703790`

#### Scenario: Coordenadas no válidas en el log
- **WHEN** se pide `GET /api/stations/nearby?lat=40,416775&lon=-3.703790&fuel=gasoleo-a` y responde 422
- **THEN** la línea del log no contiene el valor recibido de `lat` ni `-3.703790`

#### Scenario: Rotación
- **WHEN** se lanza `docker compose config`
- **THEN** el servicio `api` tiene el registro `json-file` con `max-size` 10m y `max-file` 3

### Requirement: Tiempo de respuesta con un año de datos
Con una base de un año de capturas cada 6 horas (1.460 capturas de unas
11.500 estaciones), cada consulta de la API SHALL responder en menos de 1 s,
medido en el servidor sin contar la red.

#### Scenario: Base sintética de un año (medición manual en el Mac)
- **WHEN** se genera, en una carpeta temporal fuera de `./data` (ocupará unos 4-5 GB y se borra al terminar), una base de la versión 1 con 1.460 capturas como la del 2026-10-16, y se lanza 20 veces cada ruta con parámetros representativos
- **THEN** el tiempo más lento de cada ruta es menor de 1 s, y las mediciones se apuntan en design.md

#### Scenario: Base real en el VPS (medición manual)
- **WHEN** a través del túnel se mide cada ruta 20 veces contra la base real del VPS
- **THEN** el tiempo más lento de cada ruta, descontando la red, es menor de 1 s

### Requirement: Documentación de la API en el README
El README SHALL explicar cómo arrancar la API en el Mac y en el VPS, su URL
(`http://127.0.0.1:8000/api/`) y la documentación en `/api/docs`, que
necesita `./data` y `./backups` para `docker compose up -d`, el túnel SSH y
qué significan los estados de la salud y su umbral.

#### Scenario: Lectura del README
- **WHEN** se lee la sección de la API del README
- **THEN** incluye `docker compose up -d`, `http://127.0.0.1:8000/api/docs`, el comando del túnel con `<IP_DEL_VPS>`, el umbral de «desactualizada» (dos veces `CAPTURE_INTERVAL_HOURS` más 1 h; 13 h por defecto) y que la API solo lee la base y nunca la modifica
