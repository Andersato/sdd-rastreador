# scheduled-collection Specification

## Purpose

Recoger capturas de precios de forma automática y periódica con un servicio
programador que se arranca una vez y sobrevive a reinicios y suspensiones
del ordenador, sin pedir a la API más de lo necesario.

## Requirements

### Requirement: Servicio programador que se arranca una vez
`docker compose up -d` SHALL arrancar un servicio programador que se queda en
marcha y vuelve a arrancar solo cuando se reinicia Docker o el ordenador,
salvo que el usuario lo haya parado con `docker compose stop` o `down`.
`docker compose up -d` MUST NOT lanzar el servicio `ingest` ni el de la
copia a mano.

#### Scenario: Activación
- **WHEN** existen `.env` con `HOST_UID=501`, `HOST_GID=20` y `COLLECTION_ENABLED=true`, y las carpetas `./data` y `./backups`, y se lanza `docker compose up -d`
- **THEN** queda en marcha un único contenedor, el del programador, ejecutándose con usuario 501 y grupo 20, y no se crea ningún contenedor del servicio `ingest` ni del de la copia a mano

#### Scenario: Reinicio de Docker (verificación manual)
- **WHEN** el programador está en marcha, se reinicia el entorno de Docker (o el ordenador, con el entorno de Docker configurado para arrancar al iniciar sesión) y se espera a que Docker vuelva a estar disponible
- **THEN** `docker compose ps` muestra el programador en marcha sin que el usuario haya lanzado nada, y `docker compose logs` muestra la comprobación de arranque

#### Scenario: Reinicio del VPS (verificación manual)
- **WHEN** en el VPS el programador está en marcha con `COLLECTION_ENABLED=true` y se reinicia el servidor con `sudo reboot`
- **THEN** sin entrar a lanzar nada, `docker compose ps` muestra el programador en marcha y `docker compose logs` muestra la comprobación de arranque con la recogida activada

#### Scenario: Parado por el usuario (verificación manual)
- **WHEN** el usuario lanza `docker compose stop` y después reinicia el entorno de Docker
- **THEN** `docker compose ps` muestra el programador parado y `./data/prices.db` no tiene ninguna captura nueva

### Requirement: Configuración no válida
Si falta `HOST_UID` o `HOST_GID` en `.env`, `docker compose up -d` SHALL
fallar sin crear el contenedor, con el mensaje que indica qué falta. Si
`./data` no existe, MUST fallar sin crearla. Si el usuario o el grupo es 0, o
el intervalo no es válido, el programador MUST quedarse en marcha sin hacer
ninguna petición a la API, mostrando el motivo en el log al arrancar y en
cada comprobación horaria.

#### Scenario: Falta HOST_UID
- **WHEN** `.env` no tiene `HOST_UID` y se lanza `docker compose up -d`
- **THEN** el comando termina con código distinto de 0 y un mensaje que indica que falta `HOST_UID`, no se crea ningún contenedor y `./data` queda exactamente igual que antes

#### Scenario: Carpeta ./data inexistente
- **WHEN** no existe `./data` y se lanza `docker compose up -d`
- **THEN** el comando termina con código distinto de 0, `./data` sigue sin existir y no se hace ninguna petición a la API

#### Scenario: Usuario root
- **WHEN** `.env` indica `HOST_UID=0` y `HOST_GID=20`, se lanza `docker compose up -d` y pasan 2 comprobaciones horarias
- **THEN** el programador sigue en marcha sin reiniciarse, el log muestra 3 veces (al arrancar y en cada comprobación) que no se permite ejecutar como root, no se hace ninguna petición a la API y `./data` queda exactamente igual que antes

#### Scenario: Grupo root
- **WHEN** `.env` indica `HOST_UID=501` y `HOST_GID=0` y se lanza `docker compose up -d`
- **THEN** el programador sigue en marcha, el log muestra que no se permite el grupo root, no se hace ninguna petición a la API y `./data` queda exactamente igual que antes

### Requirement: Ingesta manual con el programador en marcha
Con el programador en marcha o parado, `docker compose run --rm ingest` SHALL
seguir comportándose como define `ingestion-container`, salvo cuando haya
otra ingesta en curso, en cuyo caso se aplica "Una sola ingesta a la vez por
base de datos" de `price-ingestion`.

#### Scenario: Captura manual sin ingesta en curso
- **WHEN** el programador está en marcha esperando a la siguiente comprobación y se lanza `docker compose run --rm ingest --url <servidor local>` con una respuesta guardada válida
- **THEN** se guarda una captura, se muestra el resumen y el comando termina con código 0

#### Scenario: Captura manual mientras el programador captura
- **WHEN** el programador, configurado con la URL de un servidor local, está esperando su respuesta en una ingesta y se lanza `docker compose run --rm ingest --url <servidor local>`
- **THEN** el comando manual termina con código distinto de 0 y el mensaje de que ya hay otra ingesta en curso, sin hacer ninguna petición a la API; la ingesta del programador guarda su captura con normalidad y en `./data` solo queda `prices.db`

### Requirement: Comprobación al arrancar y cada hora
El programador SHALL hacer una comprobación nada más arrancar y después una
cada hora en el minuto 17 (nunca en el :00). Con la recogida activada, cada
comprobación decide si toca capturar y, solo si toca, lanza una única
ingesta; con la recogida desactivada nunca toca. Una comprobación que no
toca MUST NOT hacer ninguna petición a la API.

#### Scenario: Comprobaciones horarias (verificación manual)
- **WHEN** el programador arranca a las 09:40 (hora de Madrid) y sigue en marcha hasta las 12:30
- **THEN** se hacen comprobaciones a las 09:40, 10:17, 11:17 y 12:17, y ninguna a las :00

#### Scenario: Arranque justo antes del minuto 17
- **WHEN** no hay ninguna captura, el programador arranca a las 10:16:50 con la URL de un servidor local que responde correctamente tras 20 segundos, de modo que la comprobación de arranque aún no ha terminado a las 10:17
- **THEN** se hace una sola ingesta y una sola petición a la API; la comprobación de las 10:17 deja en el log "otra ingesta o copia en curso" (o "no toca", si la primera ya terminó)

#### Scenario: Recuperación tras un reinicio
- **WHEN** la última captura es de las 02:17 (hora de Madrid), el ordenador estuvo apagado y el programador arranca a las 11:05
- **THEN** a las 11:05 se lanza una ingesta, sin esperar a las 11:17

#### Scenario: Vuelta de una suspensión (verificación manual)
- **WHEN** la última captura es de las 08:17, el ordenador se suspende a las 09:00 y se despierta a las 18:40 sin reiniciar Docker
- **THEN** como tarde en la comprobación de las 19:17 se guarda una captura, y solo una

#### Scenario: Comprobaciones con la recogida desactivada
- **WHEN** `.env` no tiene `COLLECTION_ENABLED`, no hay ninguna captura y el programador está en marcha de 09:40 a 11:30
- **THEN** se hacen comprobaciones a las 09:40, 10:17 y 11:17, ninguna lanza una ingesta ni hace peticiones a la API, y cada una deja en el log que la recogida está desactivada

### Requirement: Un fallo de la ingesta no detiene el programador
Cada ingesta que lanza el programador SHALL ejecutarse como un proceso
aparte. Su fallo (error, respuesta corta, interrupción) MUST quedar solo en
el log: el programador no termina ni se reinicia, y la siguiente comprobación
horaria se hace con normalidad. Mientras la captura siga pendiente, se
reintenta como mucho una vez por hora, en las comprobaciones horarias.

#### Scenario: API caída
- **WHEN** toca capturar a las 10:17 y la API responde con HTTP 503
- **THEN** no se guarda nada, el log muestra el error, el contenedor del programador no se reinicia, y en la comprobación de las 11:17 vuelve a tocar capturar y se hace una nueva petición

#### Scenario: Reintento tras una respuesta corta
- **WHEN** a las 10:17 toca capturar y la respuesta se rechaza por corta, y a las 11:17 la API devuelve una respuesta que no es corta
- **THEN** a las 11:17 vuelve a tocar capturar, se hace una nueva petición y se guarda la captura

#### Scenario: Varios fallos seguidos
- **WHEN** toca capturar desde antes de las 10:00, la API está caída de 10:00 a 13:30 y el programador está en marcha todo ese tiempo sin reiniciarse
- **THEN** entre las 10:00 y las 13:30 se hacen exactamente 4 peticiones, una en cada comprobación (10:17, 11:17, 12:17 y 13:17), y ninguna entre ellas

### Requirement: Cuándo toca capturar
Toca capturar si no hay ninguna captura (o no existe la base), si desde el
instante de descarga de la última captura guardada (la más reciente en orden
de guardado) han pasado al menos el intervalo menos 15 minutos, si ese
instante está más de 1 hora en el futuro (con un aviso en el log), o si una
ingesta anterior quedó a medias. La decisión y la ingesta MUST
hacerse con el mismo bloqueo de "Una sola ingesta a la vez por base de
datos" de `price-ingestion`.

#### Scenario: Intervalo cumplido
- **WHEN** el intervalo es 6 horas, la última captura se descargó a las 2026-10-12T08:17:40Z y la comprobación es a las 2026-10-12T14:17:00Z
- **THEN** toca capturar (faltan 40 segundos, menos de 15 minutos) y se lanza la ingesta

#### Scenario: Intervalo no cumplido
- **WHEN** el intervalo es 6 horas, la última captura se descargó a las 2026-10-12T10:05:00Z y la comprobación es a las 2026-10-12T14:17:00Z
- **THEN** no toca capturar, no se hace ninguna petición a la API y la base de datos queda exactamente igual que antes

#### Scenario: Justo en el margen
- **WHEN** el intervalo es 6 horas, la última captura se descargó a las 2026-10-12T08:32:00Z y la comprobación es a las 2026-10-12T14:17:00Z (han pasado 5 h 45 min)
- **THEN** toca capturar

#### Scenario: Sin capturas
- **WHEN** `./data/prices.db` no existe, o existe sin ninguna captura
- **THEN** toca capturar y se lanza la ingesta

#### Scenario: Captura manual reciente
- **WHEN** el intervalo es 6 horas, se hizo una captura manual a las 13:20 (hora de Madrid) y las comprobaciones siguen su curso
- **THEN** a las 14:17 no toca capturar; a las 19:17 (han pasado 5 h 57 min) toca y se guarda una captura

#### Scenario: Captura manual durante la comprobación
- **WHEN** el intervalo es 6 horas, la última captura es de hace 7 horas, una ingesta manual contra un servidor local que responde correctamente tiene cogido el bloqueo cuando llega la comprobación
- **THEN** la comprobación no hace ninguna petición y deja en el log "otra ingesta o copia en curso"; en la comprobación siguiente ya no toca, porque la captura manual es reciente

#### Scenario: Diario pendiente de una ingesta cortada
- **WHEN** el intervalo es 6 horas, la última captura completa es de hace 1 hora y en `./data` hay un `prices.db-journal` de una ingesta que se cortó mientras guardaba
- **THEN** toca capturar, el log indica que la última ingesta quedó a medias, se lanza la ingesta y, si es correcta, `./data/prices.db` contiene las capturas anteriores intactas más la nueva y en `./data` solo queda `prices.db`

#### Scenario: Última captura poco en el futuro
- **WHEN** la última captura guardada se descargó a las 2026-10-12T14:50:00Z y la comprobación es a las 2026-10-12T14:17:00Z (33 minutos en el futuro, por ejemplo por un ajuste del reloj)
- **THEN** no toca capturar, no se hace ninguna petición a la API y el log indica que la última captura tiene una fecha posterior a la actual

#### Scenario: Última captura muy en el futuro
- **WHEN** la última captura guardada se descargó a las 2030-01-01T00:00:00Z y la comprobación es a las 2026-10-12T14:17:00Z
- **THEN** toca capturar, se lanza la ingesta y el log muestra un aviso con la fecha anómala 2030-01-01T00:00:00Z

#### Scenario: Justo 1 hora en el futuro
- **WHEN** la última captura guardada se descargó a las 2026-10-12T15:17:00Z y la comprobación es a las 2026-10-12T14:17:00Z
- **THEN** no toca capturar (hace falta más de 1 hora)

### Requirement: La comprobación no modifica ./data
Una comprobación SHALL limitarse a leer la base de datos: MUST NOT crearla,
modificarla ni dejar ningún otro archivo en `./data`, exista o no la base.
Si la base no se puede leer (versión de estructura desconocida, archivo
dañado o que no es una base de datos, base ocupada), la comprobación MUST
terminar sin pedir nada a la API y dejar el motivo en el log. Una ingesta
anterior a medias no cuenta como base ilegible ("Cuándo toca capturar").

#### Scenario: Comprobación con la base inexistente y sin poder capturar
- **WHEN** `./data` está vacía, toca capturar y la API responde con HTTP 503
- **THEN** `./data` sigue vacía: la comprobación no ha creado ningún archivo

#### Scenario: Solo queda prices.db
- **WHEN** `./data` contiene solo `prices.db` y se hacen una comprobación que no toca, una que falla por HTTP 503 y una que guarda una captura
- **THEN** después de cada una, `./data` contiene solo `prices.db`

#### Scenario: Base de datos con versión de estructura desconocida
- **WHEN** `./data/prices.db` tiene la versión de estructura 7
- **THEN** no se hace ninguna petición a la API, la base queda exactamente igual que antes, el log indica que la versión no es compatible y el programador sigue en marcha

#### Scenario: Archivo que no es una base de datos
- **WHEN** `./data/prices.db` contiene el texto "hola"
- **THEN** no se hace ninguna petición a la API, el archivo queda exactamente igual, el log indica que no se ha podido leer la base y el programador sigue en marcha

### Requirement: Intervalo configurable
El intervalo SHALL leerse de la variable `CAPTURE_INTERVAL_HOURS` de `.env`:
horas enteras de 1 a 24, ignorando espacios alrededor. Si no está o está
vacía, vale 6. Un cambio de intervalo se aplica al volver a lanzar
`docker compose up -d`.

#### Scenario: Intervalo por defecto
- **WHEN** `.env` no tiene `CAPTURE_INTERVAL_HOURS`, o tiene `CAPTURE_INTERVAL_HOURS=`, y la última captura tiene 5 horas
- **THEN** no toca capturar (el intervalo es 6 horas)

#### Scenario: Intervalo configurado
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS=3` y la última captura tiene 3 horas
- **THEN** toca capturar

#### Scenario: Formas admitidas
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS= 6 ` o `CAPTURE_INTERVAL_HOURS=06`
- **THEN** el intervalo es 6 horas

#### Scenario: Intervalo no válido
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS` con `0`, `25`, `6.5` o `seis`
- **THEN** se aplica "Configuración no válida": el programador sigue en marcha, no se hace ninguna petición a la API, `./data` queda exactamente igual que antes y el log indica el valor recibido y que se admiten horas enteras de 1 a 24

### Requirement: URL de la API para pruebas
El programador SHALL aceptar en su configuración otra URL de la API, que pasa
a cada ingesta como `--url`, para poder probarlo contra un servidor local. Sin
ella, usa la API del Ministerio. El README la presenta solo como herramienta
de pruebas.

#### Scenario: Programador contra un servidor local
- **WHEN** el programador se arranca con la URL de un servidor local que sirve una respuesta guardada de 2 estaciones, y `./data` está vacía
- **THEN** en la comprobación de arranque se hace una única petición, a ese servidor, y se crea `./data/prices.db` con 1 captura y 2 estaciones

### Requirement: Zona horaria de Madrid
Las horas de las comprobaciones y de los mensajes del programador SHALL
expresarse en hora de Madrid (Europe/Madrid), con su cambio de horario de
verano. Los instantes guardados en la base de datos MUST seguir en UTC.

#### Scenario: Horario de verano
- **WHEN** el programador hace la comprobación de las 14:17 de Madrid del 2026-07-15 y guarda una captura
- **THEN** el mensaje del log muestra 14:17 y la captura tiene un instante de descarga entre 2026-07-15T12:17:00Z y 2026-07-15T12:19:00Z

#### Scenario: Horario de invierno
- **WHEN** el programador hace la comprobación de las 14:17 de Madrid del 2026-12-15 y guarda una captura
- **THEN** el mensaje del log muestra 14:17 y la captura tiene un instante de descarga entre 2026-12-15T13:17:00Z y 2026-12-15T13:19:00Z

#### Scenario: Cambio de hora de octubre
- **WHEN** el 2026-10-25 las 02:17 de Madrid se repiten por el cambio de hora y en la primera de ellas se guarda una captura
- **THEN** si se hace una segunda comprobación a las 02:17, no toca capturar; en cualquier caso no se guarda ninguna otra captura esa hora

#### Scenario: Cambio de hora de marzo (lógica con reloj inyectado; disparos reales tras archivar)
- **WHEN** el 2027-03-28 el programador está en marcha de 00:00 a 05:00 de Madrid (las 02:17 no existen)
- **THEN** se hacen comprobaciones a las 00:17, 01:17, 03:17 y 04:17, y ninguna se repite

### Requirement: Una línea de log por comprobación
Cada comprobación SHALL dejar en `docker compose logs` al menos una línea con
la fecha y hora de Madrid y su resultado: captura guardada (con el resumen
de la ingesta), no toca (con la antigüedad de la última captura y el
intervalo), otra ingesta o copia en curso, ingesta anterior a medias, respuesta
corta, configuración no válida, recogida desactivada, base ilegible, o
error (con el motivo).

#### Scenario: Captura guardada
- **WHEN** toca capturar y la ingesta guarda 12.000 estaciones y 45.000 precios con 2 avisos
- **THEN** el log muestra la hora, que se ha guardado la captura y el resumen (estaciones, precios y los 2 avisos)

#### Scenario: No toca
- **WHEN** a las 14:17 la última captura tiene 2 h 10 min y el intervalo es 6 horas
- **THEN** el log muestra una línea con la hora 14:17, que no toca capturar, la antigüedad de 2 h 10 min y el intervalo de 6 h

#### Scenario: Respuesta corta
- **WHEN** toca capturar, la última captura tiene precios de 12.000 estaciones y la respuesta trae 9.000
- **THEN** el log muestra la hora, que no se ha guardado, las cifras 9.000 y 12.000, el porcentaje "75,0 %" y el comando exacto para guardarla a sabiendas: `docker compose run --rm ingest --accept-short-response`

#### Scenario: Error
- **WHEN** toca capturar y no se puede conectar con la API
- **THEN** el log muestra la hora y el motivo del error de la ingesta

#### Scenario: Recogida desactivada
- **WHEN** a las 14:17 `.env` no tiene `COLLECTION_ENABLED`
- **THEN** el log muestra una línea con la hora 14:17, que la recogida está desactivada en esta máquina y que se activa con `COLLECTION_ENABLED=true` en `.env`

### Requirement: Tamaño de los logs limitado
Los logs del programador SHALL rotarse para no ocupar más de 30 MB en total
(como mucho 3 archivos de 10 MB), aunque el servicio esté en marcha
indefinidamente.

#### Scenario: Rotación
- **WHEN** se consulta la configuración de logs del contenedor del programador en marcha
- **THEN** el tamaño máximo por archivo es 10 MB y se conservan como mucho 3 archivos

### Requirement: Parada del programador
`docker compose stop` y `docker compose down` SHALL parar el programador sin
esperar a que termine una ingesta en curso: esta se interrumpe con las
mismas garantías que define `ingestion-container` para una interrupción.

#### Scenario: Parada sin ingesta en curso
- **WHEN** el programador está esperando a la siguiente comprobación y se lanza `docker compose down`
- **THEN** el contenedor del programador se elimina, no se hace ninguna petición a la API y `./data/prices.db` queda exactamente igual que antes

#### Scenario: Parada durante una ingesta
- **WHEN** `./data/prices.db` contiene 3 capturas y se lanza `docker compose stop` mientras el programador está guardando la cuarta
- **THEN** `./data/prices.db` contiene o bien las 3 capturas intactas, o bien las 4 completas; nunca una captura con parte de sus precios

#### Scenario: La parada no espera a la ingesta
- **WHEN** el programador tiene en curso una ingesta contra un servidor local que tarda 60 segundos en responder y se lanza `docker compose stop`
- **THEN** el comando termina en menos de 15 segundos y no se guarda ninguna captura nueva

### Requirement: Documentación del programador
El README SHALL explicar cómo activar el programador, ver sus logs, cambiar
el intervalo, pararlo y quitarlo; que el entorno de Docker debe estar
configurado para arrancar al iniciar sesión; cómo reconocer y aceptar una respuesta corta; que no se debe
lanzar la ingesta con `.venv` mientras el programador está activo; y que
solo una máquina recoge, la que tiene `COLLECTION_ENABLED=true`.

#### Scenario: Instrucciones en el README
- **WHEN** se lee la sección del programador del README
- **THEN** incluye `docker compose up -d`, `docker compose logs`, `docker compose stop`, `docker compose down`, `CAPTURE_INTERVAL_HOURS` (y que tras cambiarlo hay que volver a lanzar `docker compose up -d`), cómo configurar el entorno de Docker para que arranque al iniciar sesión, `docker compose run --rm ingest --accept-short-response`, el aviso de no usar `.venv` con el programador activo y la URL de la API para pruebas, presentada solo como herramienta de pruebas

#### Scenario: Una sola máquina recoge
- **WHEN** se lee la sección del programador del README
- **THEN** explica que solo la máquina con `COLLECTION_ENABLED=true` en `.env` captura y hace copias (hoy, el VPS), que sin ella el programador no hace nada, que hace falta la carpeta `./backups`, y avisa de no lanzar `docker compose run --rm ingest` contra la API real en otra máquina, porque partiría el histórico en dos bases

### Requirement: Recogida habilitada explícitamente en una sola máquina
El programador SHALL capturar solo si `.env` tiene `COLLECTION_ENABLED=true`.
Ausente, vacía o `false`: desactivada (`true` y `false`, sin distinguir
mayúsculas ni espacios). Otro valor: configuración no válida, también
desactivada. Desactivada, el programador MUST seguir en marcha sin pedir
nada a la API ni tocar `./data`, y decirlo en el log al arrancar y en cada
comprobación. Los escenarios en que captura suponen `COLLECTION_ENABLED=true`
salvo que digan otra cosa.

#### Scenario: Habilitada
- **WHEN** `.env` tiene `COLLECTION_ENABLED=true`, `./data` está vacía y el programador arranca con la URL de un servidor local que sirve una respuesta guardada de 2 estaciones
- **THEN** la línea de arranque indica que la recogida está activada, se hace una única petición y se crea `./data/prices.db` con 1 captura

#### Scenario: Formas admitidas
- **WHEN** `.env` tiene `COLLECTION_ENABLED=TRUE`, `COLLECTION_ENABLED= true ` o `COLLECTION_ENABLED=True`
- **THEN** la línea de arranque del log indica que la recogida está activada

#### Scenario: Sin la variable (el Mac por costumbre)
- **WHEN** `.env` solo tiene `HOST_UID=501` y `HOST_GID=20`, existen `./data` y `./backups`, `./data/prices.db` tiene 8 capturas, la última de hace 7 horas, se lanza `docker compose up -d` y pasan 2 comprobaciones horarias
- **THEN** el programador sigue en marcha sin reiniciarse, el log muestra 3 veces (al arrancar y en cada comprobación) que la recogida está desactivada en esta máquina y cómo activarla (`COLLECTION_ENABLED=true` en `.env`), no se hace ninguna petición a la API y `./data` queda exactamente igual que antes

#### Scenario: Variable vacía o false
- **WHEN** `.env` tiene `COLLECTION_ENABLED=`, `COLLECTION_ENABLED=false`, `COLLECTION_ENABLED=FALSE` o `COLLECTION_ENABLED= false ` y no hay ninguna captura
- **THEN** no se hace ninguna petición a la API, `./data` sigue vacía y el log indica que la recogida está desactivada

#### Scenario: Valor no válido
- **WHEN** `.env` tiene `COLLECTION_ENABLED=yes`, `COLLECTION_ENABLED=1` o `COLLECTION_ENABLED=si`
- **THEN** el programador sigue en marcha, no se hace ninguna petición a la API, `./data` queda exactamente igual que antes y el log indica el valor recibido y que solo `true` activa la recogida

#### Scenario: La ingesta manual no depende de la variable
- **WHEN** `.env` no tiene `COLLECTION_ENABLED` y se lanza `docker compose run --rm ingest --url <servidor local>` con una respuesta guardada válida
- **THEN** se guarda una captura y el comando termina con código 0, como define `ingestion-container`

### Requirement: Configuración no válida antes que recogida desactivada
Si coinciden una configuración no válida (usuario o grupo root, intervalo no
válido o valor no válido de `COLLECTION_ENABLED`) y la recogida desactivada,
el log SHALL mostrar la configuración no válida, en ese orden de
comprobación, en lugar de "recogida desactivada". En ningún caso se hace
una petición a la API.

#### Scenario: Root sin la variable
- **WHEN** `.env` indica `HOST_UID=0` y `HOST_GID=20` y no tiene `COLLECTION_ENABLED`
- **THEN** el log muestra al arrancar y en cada comprobación que no se permite ejecutar como root, no dice "recogida desactivada" y no se hace ninguna petición a la API

#### Scenario: Intervalo no válido con la recogida desactivada
- **WHEN** `.env` tiene `CAPTURE_INTERVAL_HOURS=seis` y `COLLECTION_ENABLED=false`
- **THEN** el log muestra que el intervalo no es válido y no se hace ninguna petición a la API

#### Scenario: Valor no válido de la variable con root
- **WHEN** `.env` indica `HOST_UID=0` y `COLLECTION_ENABLED=yes`
- **THEN** el log muestra que no se permite ejecutar como root (la primera comprobación)

### Requirement: Cambio de la variable de recogida
Un cambio de `COLLECTION_ENABLED` en `.env` SHALL aplicarse al volver a
lanzar `docker compose up -d`, igual que el intervalo; hasta entonces, el
programador sigue con el valor con el que arrancó.

#### Scenario: Activarla después
- **WHEN** el programador está en marcha con la recogida desactivada, se añade `COLLECTION_ENABLED=true` a `.env` y se vuelve a lanzar `docker compose up -d` sin capturas previas
- **THEN** en la comprobación de arranque se lanza la ingesta

#### Scenario: Desactivarla después
- **WHEN** el programador está en marcha con `COLLECTION_ENABLED=true`, la última captura tiene 7 horas, se cambia a `COLLECTION_ENABLED=false` y se vuelve a lanzar `docker compose up -d`
- **THEN** ni la comprobación de arranque ni las siguientes hacen peticiones a la API, y el log indica que la recogida está desactivada

#### Scenario: Cambio sin volver a lanzar
- **WHEN** el programador está en marcha con `COLLECTION_ENABLED=true` y se borra la variable de `.env` sin volver a lanzar `docker compose up -d`
- **THEN** el programador sigue con la recogida activada
