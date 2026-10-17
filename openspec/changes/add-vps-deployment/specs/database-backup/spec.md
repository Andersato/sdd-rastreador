# Spec Delta

## Purpose

Proteger el histórico de precios con copias diarias verificadas en la
máquina que recoge, una segunda copia descargada al Mac que el servidor no
puede borrar, y un procedimiento de restauración probado.

## ADDED Requirements

### Requirement: Copia diaria a hora fija
Con la recogida activada (`COLLECTION_ENABLED=true`), el programador SHALL
hacer una copia de `./data/prices.db` cada día a las 04:43 de Madrid, como
proceso aparte: su fallo MUST quedar solo en el log, sin parar ni reiniciar
el programador. Con la recogida desactivada, a esa hora solo se registra que
las copias están desactivadas.

#### Scenario: Copia de madrugada (lógica con reloj inyectado; disparos reales tras archivar)
- **WHEN** el programador está en marcha el 2026-10-17 de 00:00 a 06:00 de Madrid y `./data/prices.db` tiene 28 capturas
- **THEN** se hace una sola copia, a las 04:43, y queda `./backups/prices-2026-10-17.db.gz`

#### Scenario: Cambios de hora (lógica con reloj inyectado; disparos reales tras archivar)
- **WHEN** el programador está en marcha los días 2026-10-25 y 2027-03-28
- **THEN** cada uno de esos días se hace exactamente una copia, a las 04:43 de Madrid

#### Scenario: Recogida desactivada
- **WHEN** `.env` no tiene `COLLECTION_ENABLED` y llegan las 04:43
- **THEN** no se crea ningún archivo en `./backups`, `./data` queda exactamente igual que antes y el log indica que las copias están desactivadas en esta máquina

#### Scenario: Una copia fallida no para el programador
- **WHEN** la copia de las 04:43 falla porque `./backups` no tiene permiso de escritura para el usuario del programador
- **THEN** el programador sigue en marcha sin reiniciarse y la comprobación de las 05:17 se hace con normalidad

### Requirement: Copia al arrancar si la última es antigua
En la comprobación de arranque, con la recogida activada, el programador
SHALL hacer una copia si no hay ninguna en `./backups` o si la más reciente
(por la fecha del nombre, sin contar archivos ajenos) se modificó por
última vez hace más de 26 horas. La copia se hace después de la decisión de
capturar de esa comprobación (y de su ingesta, si la hay).

#### Scenario: Servidor apagado más de un día
- **WHEN** la última copia se creó el 2026-10-16 a las 04:43, el VPS está apagado desde el 2026-10-17 a las 03:00 y el programador arranca el 2026-10-18 a las 08:00
- **THEN** en la comprobación de arranque se hace una copia, `./backups/prices-2026-10-18.db.gz`, y la siguiente es la del 2026-10-19 a las 04:43

#### Scenario: Apagado solo a la hora de la copia
- **WHEN** la última copia se creó el 2026-10-16 a las 04:43, el VPS está apagado de 04:00 a 05:00 del 2026-10-17 y el programador arranca a las 05:00 (han pasado 24 h 17 min)
- **THEN** al arrancar no se hace ninguna copia; ese día no hay copia y la siguiente es la del 2026-10-18 a las 04:43

#### Scenario: Justo en el límite
- **WHEN** la última copia se creó el 2026-10-16 a las 04:43 y el programador arranca el 2026-10-17 a las 06:43 (26 h exactas)
- **THEN** al arrancar no se hace ninguna copia

#### Scenario: Sin copias
- **WHEN** `./backups` está vacía, `./data/prices.db` tiene 8 capturas y el programador arranca
- **THEN** en la comprobación de arranque se hace una copia

#### Scenario: Con la recogida desactivada
- **WHEN** `.env` no tiene `COLLECTION_ENABLED`, `./backups` está vacía y el programador arranca
- **THEN** no se hace ninguna copia y `./backups` sigue vacía

#### Scenario: Arranque con captura pendiente
- **WHEN** al arrancar toca capturar y la última copia tiene 30 horas
- **THEN** primero se hace la ingesta y después la copia, que incluye la captura nueva

### Requirement: Copia en caliente sin tocar la base
El volcado SHALL hacerse con la API de backup de SQLite, nunca copiando el
archivo, bajo el bloqueo de `price-ingestion`; verificar y comprimir, ya sin
él. Con una ingesta en curso MUST esperar como mucho 10 minutos. Si se
agota, o la última ingesta quedó a medias, la copia del día queda pendiente
y se reintenta en cada comprobación horaria de ese día. MUST NOT modificar
`./data/prices.db` ni dejar archivos en `./data`.

#### Scenario: Copia con el programador en marcha
- **WHEN** `./data/prices.db` tiene 28 capturas y 340.000 precios y se hace una copia
- **THEN** la copia, una vez descomprimida, tiene las mismas 28 capturas y 340.000 precios, y `./data` sigue conteniendo solo `prices.db`, con el mismo contenido que antes

#### Scenario: Ingesta en curso que termina pronto
- **WHEN** a las 04:43 una ingesta manual contra un servidor local tiene el bloqueo y termina a las 04:45 guardando la captura 29
- **THEN** la copia empieza después de que termine la ingesta y contiene las 29 capturas

#### Scenario: Ingesta en curso que no termina
- **WHEN** el 2026-10-17 a las 04:43 otro proceso tiene el bloqueo y no lo suelta hasta las 05:00
- **THEN** a las 04:53 se deja de esperar sin crear ninguna copia, las copias anteriores y `./data` quedan exactamente igual, el log indica que la copia queda pendiente porque había otra ingesta o copia en curso, y en la comprobación de las 05:17 se hace la copia `./backups/prices-2026-10-17.db.gz`

#### Scenario: Orden en una comprobación con copia pendiente
- **WHEN** la copia del 2026-10-17 está pendiente y a la comprobación de las 05:17 también le toca capturar
- **THEN** primero se hace la ingesta y después la copia, que incluye la captura nueva; si el bloqueo está ocupado, la copia vuelve a esperar como mucho 10 minutos

#### Scenario: Reintentos durante el día
- **WHEN** la copia del 2026-10-17 está pendiente por ingesta en curso y el bloqueo sigue ocupado en las comprobaciones de las 05:17 y las 06:17
- **THEN** cada una de esas comprobaciones intenta la copia y lo deja en el log; en la primera comprobación en que el bloqueo está libre se hace `./backups/prices-2026-10-17.db.gz`, y las siguientes de ese día ya no intentan copiar

#### Scenario: Pendiente hasta el final del día
- **WHEN** la copia del 2026-10-17 sigue pendiente tras la comprobación de las 23:17
- **THEN** la comprobación de las 00:17 del 2026-10-18 no intenta copiar y la siguiente copia es la del 2026-10-18 a las 04:43

#### Scenario: Otros fallos no se reintentan
- **WHEN** la copia de las 04:43 falla porque la base no pasa `PRAGMA integrity_check`
- **THEN** las comprobaciones horarias de ese día no intentan copiar; la siguiente copia es la del día siguiente a las 04:43

#### Scenario: Comprobación horaria durante el volcado
- **WHEN** una copia está volcando la base (tiene el bloqueo) y llega una comprobación horaria a la que le toca capturar
- **THEN** la comprobación deja en el log "otra ingesta o copia en curso" sin hacer ninguna petición, y en la siguiente comprobación vuelve a tocar

#### Scenario: Comprobación horaria durante la verificación o la compresión
- **WHEN** una copia ya ha terminado el volcado y está verificándolo o comprimiéndolo cuando llega una comprobación horaria a la que le toca capturar
- **THEN** la comprobación lanza la ingesta con normalidad y guarda la captura, y la copia termina con las capturas que había al volcar

#### Scenario: Ingesta anterior a medias
- **WHEN** a las 04:43 del 2026-10-17 en `./data` hay un `prices.db-journal` de una ingesta que se cortó mientras guardaba
- **THEN** no se crea ninguna copia, `./data/prices.db` y `./data/prices.db-journal` quedan exactamente igual, el log indica que la copia queda pendiente porque la última ingesta quedó a medias, y en la comprobación de las 05:17, a la que le toca capturar por la ingesta a medias, la ingesta resuelve el diario y justo después, en esa misma comprobación, se hace `./backups/prices-2026-10-17.db.gz`

#### Scenario: Ingesta a medias que no se resuelve
- **WHEN** la copia del 2026-10-17 está pendiente por un `prices.db-journal` y la ingesta de las 05:17 falla con HTTP 503 antes de guardar
- **THEN** la copia sigue pendiente, no se crea ninguna copia y se vuelve a intentar en la comprobación de las 06:17

### Requirement: Una sola copia a la vez
Dos copias (diaria, al arrancar o a mano) MUST NOT solaparse en ningún paso
(volcado, verificación, compresión ni rotación). La segunda SHALL esperar a
que termine la primera; los 10 minutos de espera cuentan en total, sea por
una ingesta o por otra copia. Si se agotan, la diaria queda pendiente y la
copia a mano termina con error. Esperar a otra copia no retrasa ninguna
ingesta.

#### Scenario: Copia a mano a la vez que la diaria
- **WHEN** a las 04:43 del 2026-10-20 coinciden la copia diaria y una copia a mano, y cada una tarda 3 minutos
- **THEN** la segunda empieza cuando termina la primera, las dos terminan bien y queda un único `./backups/prices-2026-10-20.db.gz` verificado

#### Scenario: La primera copia no termina a tiempo
- **WHEN** una copia a mano empieza a las 04:40 del 2026-10-20 y tarda 15 minutos, y a las 04:43 llega la diaria
- **THEN** a las 04:53 la diaria deja de esperar, queda pendiente y lo indica en el log; en la comprobación de las 05:17 se hace la copia; la copia a mano termina bien

#### Scenario: Espera total de 10 minutos
- **WHEN** a las 04:43 una copia a mano lleva en curso hasta las 04:49 y después una ingesta tiene el bloqueo de `./data` hasta las 05:00
- **THEN** la diaria deja de esperar a las 04:53 (10 minutos en total) y queda pendiente

#### Scenario: Copia a mano que espera demasiado a otra copia
- **WHEN** una copia diaria empieza a las 04:43 y tarda 15 minutos, y a las 04:45 se lanza una copia a mano
- **THEN** a las 04:55 la copia a mano termina con código distinto de 0 y el mensaje "ya hay otra ingesta o copia en curso", sin crear nada en `./backups`; la diaria termina bien

#### Scenario: Ingesta durante la verificación de otra copia
- **WHEN** una copia está comprimiendo y otra copia la espera, y llega una comprobación horaria a la que le toca capturar
- **THEN** la ingesta se hace con normalidad, sin esperar a ninguna de las dos copias

### Requirement: Copia verificada antes de darla por buena
Cada copia SHALL pasar `PRAGMA integrity_check` con resultado `ok` y tener
al menos una captura antes de comprimirse; el comprimido MUST
descomprimirse sin errores antes de ocupar su nombre final. Si falla
cualquier paso, MUST NOT quedar ningún archivo nuevo ni temporal en
`./backups`, las copias anteriores quedan intactas y no se hace rotación.

#### Scenario: Copia correcta
- **WHEN** `./data/prices.db` está sana y tiene 28 capturas
- **THEN** queda `./backups/prices-2026-10-17.db.gz`, que se descomprime con `gunzip` en una base que da `ok` en `PRAGMA integrity_check` y tiene 28 capturas

#### Scenario: Base dañada
- **WHEN** `./data/prices.db` no pasa `PRAGMA integrity_check`
- **THEN** no se crea ninguna copia nueva, no se borra ninguna anterior y el log indica que la base no ha pasado la verificación

#### Scenario: Base inexistente o sin capturas
- **WHEN** `./data/prices.db` no existe, o existe sin ninguna captura
- **THEN** no se crea ninguna copia, `./data` queda exactamente igual y el log indica que no hay nada que copiar

#### Scenario: Base ilegible
- **WHEN** `./data/prices.db` contiene el texto "hola"
- **THEN** no se crea ninguna copia, el archivo queda exactamente igual y el log indica que no se ha podido leer la base

#### Scenario: Versión de estructura desconocida
- **WHEN** `./data/prices.db` tiene la versión de estructura 7, pasa `PRAGMA integrity_check` y su tabla de capturas tiene 28 filas
- **THEN** se crea la copia con normalidad, `./data/prices.db` queda exactamente igual y la línea del log incluye un aviso con la versión 7

#### Scenario: Versión desconocida sin tabla de capturas
- **WHEN** `./data/prices.db` tiene la versión de estructura 7 y no tiene tabla de capturas
- **THEN** no se crea ninguna copia y el log indica que no hay nada que copiar

#### Scenario: Disco lleno (error simulado)
- **WHEN** no queda espacio en el disco a mitad de la copia
- **THEN** en `./backups` no queda ningún archivo nuevo ni temporal, las copias anteriores quedan intactas y el log muestra el error

#### Scenario: Copia interrumpida
- **WHEN** se lanza `docker compose stop` a mitad de una copia
- **THEN** el comando termina en menos de 15 segundos, en `./backups` no queda ningún archivo nuevo ni temporal y `./data` queda exactamente igual que antes

### Requirement: Carpeta ./backups montada aparte
Las copias SHALL guardarse en `./backups` del host, distinta de `./data` y
a nombre del usuario del host, montada solo en el programador y en la copia
a mano: si no existe, ambos MUST fallar sin crearla, pero
`docker compose run --rm ingest` MUST funcionar sin ella. `backups/` MUST
estar en `.gitignore` y `.dockerignore`.

#### Scenario: Archivos a nombre del usuario del host (verificación manual)
- **WHEN** en el VPS el usuario `deploy` (1001:1001) es dueño de `./backups` y se hace una copia
- **THEN** `./backups/prices-2026-10-17.db.gz` pertenece a 1001:1001

#### Scenario: ./backups inexistente
- **WHEN** existe `./data` pero no `./backups` y se lanza `docker compose up -d`
- **THEN** el comando termina con código distinto de 0, `./backups` sigue sin existir y no se hace ninguna petición a la API

#### Scenario: La ingesta manual no necesita ./backups
- **WHEN** existe `./data` pero no `./backups` y se lanza `docker compose run --rm ingest --url <servidor local>` con una respuesta guardada válida
- **THEN** se guarda la captura, el comando termina con código 0 y `./backups` sigue sin existir

#### Scenario: La ingesta manual no ve las copias
- **WHEN** existe `./backups` y se lanza `docker compose run --rm ingest`
- **THEN** el contenedor de la ingesta no tiene montada la carpeta `./backups`

#### Scenario: Fuera del repo y de la imagen
- **WHEN** `./backups` contiene copias y se lanzan `git status` y `docker compose build`
- **THEN** `git status` no muestra nada de `backups/` y la imagen no contiene ningún archivo de `backups/`

### Requirement: Nombre y rotación de las copias
Cada copia SHALL llamarse `prices-AAAA-MM-DD.db.gz` (fecha de Madrid, que
manda en la rotación). Tras una copia correcta se conservan 7 diarias (las
más recientes) y 4 semanales: la última de cada una de las 4 semanas (lunes
a domingo) más recientes con copia y sin diarias; el resto con ese patrón se
borra. Una copia del mismo día MUST sustituir a la anterior solo ya
verificada.

#### Scenario: Rotación tras una copia
- **WHEN** `./backups` tiene una copia por cada día del 2026-09-01 al 2026-10-16 y se hace la del sábado 2026-10-17
- **THEN** quedan las de los días 11 al 17 de octubre (7 diarias, que tocan las semanas del 5 y del 12 de octubre) y las de los domingos 2026-10-04, 2026-09-27, 2026-09-20 y 2026-09-13 (4 semanales): 11 archivos en total; se borran las 36 restantes, del 2026-09-01 al 2026-10-10

#### Scenario: Semanas con huecos
- **WHEN** `./backups` tiene solo las copias de los días 2026-08-26, 2026-09-02, 2026-09-10, 2026-09-16, 2026-09-24 y 2026-10-01 al 2026-10-06, y se hace la del 2026-10-07
- **THEN** quedan las de los días 1 al 7 de octubre (7 diarias) y las de 2026-09-24, 2026-09-16, 2026-09-10 y 2026-09-02 (últimas de sus semanas), y se borra la de 2026-08-26

#### Scenario: Semana sin ninguna copia
- **WHEN** `./backups` tiene las copias de 2026-09-06, 2026-09-13, 2026-09-27, 2026-10-04 y 2026-10-11 al 2026-10-16 (ninguna en la semana del 14 al 20 de septiembre), y se hace la del 2026-10-17
- **THEN** quedan las de los días 11 al 17 de octubre y las de 2026-10-04, 2026-09-27, 2026-09-13 y 2026-09-06 (la semana sin copias no cuenta): 11 archivos, y no se borra ninguna

#### Scenario: Primeras copias
- **WHEN** `./backups` está vacía y se hacen copias 3 días seguidos
- **THEN** quedan las 3 copias y no se borra nada

#### Scenario: Segunda copia el mismo día
- **WHEN** existe `./backups/prices-2026-10-17.db.gz` con 28 capturas y se hace una copia a mano ese mismo día, después de la captura 29
- **THEN** `./backups/prices-2026-10-17.db.gz` pasa a tener 29 capturas y sigue habiendo un solo archivo de ese día

#### Scenario: Segunda copia del mismo día que falla
- **WHEN** existe `./backups/prices-2026-10-17.db.gz` y una segunda copia ese día no pasa la verificación
- **THEN** `./backups/prices-2026-10-17.db.gz` queda exactamente igual que antes

#### Scenario: Una copia fallida no borra copias
- **WHEN** `./backups` tiene 11 copias y la copia del día falla
- **THEN** siguen las mismas 11 copias, sin cambios

### Requirement: Archivos ajenos y temporales en ./backups
La rotación SHALL contar solo los archivos con el patrón y una fecha válida
que no sea posterior al día en curso; el resto son ajenos y MUST NOT
tocarse. Excepción: los temporales de una copia cortada (que ya no está en
curso), que la siguiente copia borra y lo indica en el log.

#### Scenario: Fecha imposible en el nombre
- **WHEN** `./backups` contiene `prices-2026-02-31.db.gz` además de 12 copias válidas
- **THEN** se trata como archivo ajeno: no cuenta para la rotación y sigue intacto

#### Scenario: Fecha futura en el nombre
- **WHEN** el 2026-10-17 `./backups` contiene `prices-2030-01-01.db.gz` además de 12 copias válidas y se hace la copia del día
- **THEN** `prices-2030-01-01.db.gz` se trata como archivo ajeno: no ocupa ninguna diaria, sigue intacto y el log muestra un aviso con su nombre

#### Scenario: Temporales de una copia cortada
- **WHEN** el VPS se apagó a mitad de una copia y en `./backups` quedó su archivo temporal, y después se hace una copia correcta
- **THEN** el temporal desaparece, la línea del log lo indica, y los archivos ajenos y el resto de copias no se tocan

#### Scenario: Archivos ajenos
- **WHEN** `./backups` contiene `antes-de-migrar.db` y `notas.txt` además de 12 copias con el patrón
- **THEN** tras la rotación siguen `antes-de-migrar.db` y `notas.txt` intactos

### Requirement: Copia a mano
SHALL existir un comando, documentado en el runbook, que lanza una copia
fuera de hora, con el programador en marcha o parado, con las mismas
garantías, rotación y línea de log que la diaria. Termina con código 0 si
la copia es correcta y distinto de 0 si no; nunca queda pendiente. Con la
recogida desactivada MUST terminar con código distinto de 0 sin crear
nada.

#### Scenario: Copia antes de una actualización
- **WHEN** con el programador en marcha y la recogida activada se lanza el comando de copia a mano el 2026-10-20
- **THEN** queda `./backups/prices-2026-10-20.db.gz` verificada, el comando muestra la misma línea que el log de la copia diaria y termina con código 0

#### Scenario: Copia a mano con el programador parado
- **WHEN** tras `docker compose stop` se lanza el comando de copia a mano el 2026-10-20 con la recogida activada
- **THEN** queda `./backups/prices-2026-10-20.db.gz` verificada, el comando termina con código 0 y el programador sigue parado

#### Scenario: Copia a mano con una ingesta en curso
- **WHEN** se lanza el comando de copia a mano mientras una ingesta tiene el bloqueo y no lo suelta en 10 minutos
- **THEN** el comando termina con código distinto de 0 y el mensaje "ya hay otra ingesta o copia en curso", sin crear nada en `./backups`

#### Scenario: Copia a mano sin ./backups
- **WHEN** no existe `./backups` y se lanza el comando de copia a mano
- **THEN** termina con código distinto de 0 y `./backups` sigue sin existir

#### Scenario: Copia a mano en el Mac
- **WHEN** `.env` no tiene `COLLECTION_ENABLED` y se lanza el comando de copia a mano
- **THEN** termina con código distinto de 0, indica que las copias están desactivadas en esta máquina y no crea nada en `./backups`

### Requirement: Una línea de log por copia
Cada copia SHALL dejar en `docker compose logs` una línea con la fecha y
hora de Madrid y su resultado: copia guardada (nombre, tamaño comprimido con
un decimal, número de capturas con punto de miles y verificación correcta),
copias borradas por la rotación,
temporales borrados, avisos (versión desconocida, fecha futura), copias
desactivadas, pendiente (otra ingesta o copia en curso, o ingesta anterior a
medias), nada que copiar, verificación fallida o error (con el motivo).

#### Scenario: Copia guardada
- **WHEN** la copia del 2026-10-17 a las 04:43 guarda 1.204 capturas en 912,4 MB comprimidos y la rotación borra `prices-2026-10-09.db.gz`
- **THEN** el log muestra una línea con "2026-10-17 04:43", `prices-2026-10-17.db.gz`, "912,4 MB", "1.204 capturas", que la integridad es correcta, y que se ha borrado `prices-2026-10-09.db.gz`

#### Scenario: Error
- **WHEN** la copia falla porque no se puede escribir en `./backups`
- **THEN** el log muestra la hora y el motivo del error

### Requirement: Descarga de las copias al Mac
SHALL existir en el repo un script que el Mac ejecuta para traer por SSH con
`rsync` las copias de `./backups` del VPS a una carpeta del Mac
(configurable; por defecto `~/Backups/precios-gasolineras/`), con la clave
de "Acceso restringido para las copias". Es el Mac quien se conecta: el VPS
no tiene acceso al Mac. Una descarga cortada MUST NOT dejar un archivo con
nombre de copia válida.

#### Scenario: Primera descarga
- **WHEN** el VPS tiene 3 copias correctas y la carpeta del Mac no existe
- **THEN** el script crea la carpeta, descarga las 3, las verifica, muestra un resumen (copias nuevas, la más reciente y su número de capturas) y termina con código 0

#### Scenario: Sin novedades
- **WHEN** el Mac ya tiene todas las copias del VPS y se vuelve a lanzar el script
- **THEN** no se vuelve a descargar ninguna, el resumen indica 0 copias nuevas y termina con código 0

#### Scenario: Copias borradas en el VPS
- **WHEN** el Mac tiene `prices-2026-10-09.db.gz`, que la rotación del VPS ya ha borrado, y se lanza el script
- **THEN** `prices-2026-10-09.db.gz` sigue en el Mac, salvo que la rotación del propio Mac la borre

#### Scenario: VPS inaccesible
- **WHEN** no se puede conectar con el VPS (sin red, o SSH rechaza la clave)
- **THEN** el script termina con código distinto de 0 y un mensaje con el motivo, y la carpeta del Mac queda exactamente igual que antes

#### Scenario: Conexión cortada a mitad
- **WHEN** la conexión se corta mientras se descarga `prices-2026-10-17.db.gz`
- **THEN** el script termina con código distinto de 0, en la carpeta del Mac no aparece `prices-2026-10-17.db.gz` y las copias que ya había quedan intactas

#### Scenario: Solo se descargan copias
- **WHEN** `./backups` del VPS contiene `prices-2026-10-17.db.gz`, `antes-de-migrar.db`, `notas.txt` y el temporal de una copia en curso
- **THEN** el script solo descarga `prices-2026-10-17.db.gz`; los otros tres no aparecen en el Mac

#### Scenario: Descarga durante una copia en el VPS
- **WHEN** el script se lanza mientras el VPS está escribiendo la copia del 2026-10-17
- **THEN** no descarga nada de esa copia a medias; la descargará en la ejecución siguiente, ya con su nombre final

#### Scenario: Dónde se descarga
- **WHEN** el script está descargando `prices-2026-10-17.db.gz`
- **THEN** lo escribe en la subcarpeta `descargando/` de la carpeta del Mac, que no cuenta para la rotación; solo cuando está verificada pasa a la carpeta principal con su nombre, y la siguiente ejecución borra lo que haya quedado en `descargando/` tras un corte

#### Scenario: Ninguna copia en el VPS
- **WHEN** `./backups` del VPS está vacía
- **THEN** el script termina con código distinto de 0 indicando que no hay copias en el VPS, y no borra nada en el Mac

### Requirement: Acceso restringido para las copias
El script SHALL usar una clave SSH dedicada solo a las copias, sin
contraseña (para `launchd`), distinta de la clave personal. En el VPS, esa
clave MUST estar limitada en `authorized_keys` a leer `backups/` con
`rsync` (`rrsync` en solo lectura): sin terminal ni otros comandos, sin
escribir ni borrar y sin leer fuera de `backups/`.

#### Scenario: Descarga con la clave dedicada (verificación manual)
- **WHEN** se lanza el script en el Mac con la clave dedicada
- **THEN** descarga las copias de `backups/` y termina con código 0

#### Scenario: Terminal con la clave dedicada (verificación manual)
- **WHEN** desde el Mac se lanza `ssh -i <clave dedicada> deploy@<IP_DEL_VPS>` o `ssh -i <clave dedicada> deploy@<IP_DEL_VPS> ls`
- **THEN** no se abre ninguna terminal ni se ejecuta `ls`

#### Scenario: Escritura o lectura fuera de backups/ (verificación manual)
- **WHEN** con la clave dedicada se intenta subir un archivo a `backups/`, borrar `prices-2026-10-17.db.gz` con `rsync --delete`, o descargar `data/prices.db`
- **THEN** las tres operaciones fallan y `./backups` y `./data` del VPS quedan exactamente igual que antes

#### Scenario: Sin la clave personal
- **WHEN** se lee la configuración del script y la sección de copia fuera del VPS en `docs/`
- **THEN** la clave que usa es la dedicada (por defecto `~/.ssh/precios-backups`) y la documentación explica crearla con `ssh-keygen` sin contraseña y añadirla a mano en `authorized_keys` con la restricción, no con `ssh-copy-id`

#### Scenario: Sin el rsync de Homebrew
- **WHEN** en el Mac no está instalado el `rsync` de Homebrew (solo existe el `/usr/bin/rsync` del sistema) y se lanza el script
- **THEN** termina con código distinto de 0 antes de conectar, con un mensaje que dice que falta el `rsync` de Homebrew y cómo instalarlo (`brew install rsync`), sin usar `/usr/bin/rsync`, y la carpeta del Mac queda igual que antes

#### Scenario: Clave dedicada ausente
- **WHEN** no existe la clave dedicada en el Mac y se lanza el script
- **THEN** termina con código distinto de 0, indica qué clave falta y cómo crearla, no prueba ninguna otra clave y la carpeta del Mac queda igual que antes

### Requirement: Verificación de las copias descargadas
El script SHALL verificar cada copia nueva o cambiada (que se descomprime y
da `ok` en `PRAGMA integrity_check`, con al menos una captura) antes de
contarla como válida. Una copia que falla MUST apartarse a `rechazadas/`
dentro de la carpeta del Mac, no contar para la rotación y hacer que el
script termine con código distinto de 0.

#### Scenario: Copia dañada
- **WHEN** en el VPS `prices-2026-10-17.db.gz` está truncado y el resto de copias son correctas
- **THEN** el resto se descargan y verifican, `prices-2026-10-17.db.gz` queda en `rechazadas/`, el mensaje la nombra y el script termina con código distinto de 0

#### Scenario: Archivo que no es gzip
- **WHEN** en el VPS `prices-2026-10-17.db.gz` contiene el texto "hola"
- **THEN** queda en `rechazadas/` y el script termina con código distinto de 0

#### Scenario: Copia del mismo día que cambia y llega mal
- **WHEN** el Mac tiene una `prices-2026-10-17.db.gz` válida con 28 capturas, en el VPS se rehace ese día y la nueva llega truncada
- **THEN** la nueva se descarga aparte y queda en `rechazadas/`, la `prices-2026-10-17.db.gz` del Mac sigue exactamente igual que antes (28 capturas) y el script termina con código distinto de 0

#### Scenario: Copia del mismo día que cambia y llega bien
- **WHEN** el Mac tiene una `prices-2026-10-17.db.gz` válida con 28 capturas y en el VPS se rehace ese día con 29
- **THEN** la nueva se descarga aparte, se verifica y solo entonces sustituye a la anterior: en el Mac queda una sola `prices-2026-10-17.db.gz`, con 29 capturas

#### Scenario: Copia rechazada que sigue en el VPS
- **WHEN** `prices-2026-10-17.db.gz` ya está en `rechazadas/` por una ejecución anterior y sigue en el VPS
- **THEN** cada ejecución vuelve a descargarla y verificarla; si vuelve a fallar sustituye a la de `rechazadas/` con el mismo nombre y el script termina con código distinto de 0; si pasa, se cuenta como válida

### Requirement: Rotación en el Mac
Tras descargar y verificar, el script SHALL aplicar en la carpeta del Mac la
rotación de "Nombre y rotación de las copias" sobre las copias válidas,
decidida solo con lo que hay en el Mac. MUST NOT borrar nada si alguna copia
nueva ha fallado, ni tocar `rechazadas/` ni archivos con otro nombre.

#### Scenario: Rotación local
- **WHEN** el Mac tiene una copia válida por día del 2026-09-01 al 2026-10-16 y el script descarga la del 2026-10-17
- **THEN** en el Mac quedan las mismas 11 copias que en "Rotación tras una copia"

#### Scenario: Copia nueva rechazada
- **WHEN** la única copia nueva, `prices-2026-10-17.db.gz`, va a `rechazadas/`
- **THEN** no se borra ninguna copia del Mac

### Requirement: Descarga programada en el Mac
La documentación SHALL incluir un archivo de `launchd` de ejemplo y los
comandos para cargarlo, comprobarlo y quitarlo, de modo que el script se
ejecute cada día a las 10:00 (`StartCalendarInterval`) y también al cargarse
o iniciar sesión (`RunAtLoad`), con la salida en un archivo de log del Mac.

#### Scenario: Instrucciones de launchd
- **WHEN** se lee la sección de copia fuera del VPS en `docs/`
- **THEN** incluye el archivo `.plist` con `StartCalendarInterval` a las 10:00, `RunAtLoad`, la ruta del log y marcadores en lugar de datos reales (`<IP_DEL_VPS>`), los comandos `launchctl bootstrap`, `launchctl print` y `launchctl bootout`, y explica que si el Mac está dormido a las 10:00 el script se ejecuta al despertar, y si estaba apagado, al iniciar sesión

#### Scenario: Dos ejecuciones el mismo día
- **WHEN** el script se ejecuta al iniciar sesión a las 09:00 y otra vez a las 10:00 sin copias nuevas en el VPS
- **THEN** la segunda no descarga nada, indica 0 copias nuevas y termina con código 0

#### Scenario: Ejecución programada (verificación manual)
- **WHEN** el archivo de `launchd` está cargado y pasa la hora configurada con el Mac encendido
- **THEN** el log del Mac muestra el resumen de esa ejecución

### Requirement: Restauración documentada y probada
`docs/` SHALL describir cómo restaurar una copia en el Mac y en un VPS
nuevo, siempre en una carpeta nueva o con el programador parado, sin
sobrescribir nunca un `prices.db` existente, y cómo comprobar integridad y
número de capturas. La restauración en el Mac MUST probarse una vez y
anotarse su fecha y resultado.

#### Scenario: Restauración en el Mac (verificación manual)
- **WHEN** se sigue el procedimiento con la copia más reciente de la carpeta del Mac
- **THEN** queda una base nueva en una carpeta aparte que da `ok` en `PRAGMA integrity_check` y tiene el mismo número de capturas que indica la línea de log del VPS de esa copia, y `data/prices.db` del Mac queda exactamente igual que antes

#### Scenario: Destino ocupado
- **WHEN** se lee el procedimiento de restauración en un VPS
- **THEN** indica parar el programador antes, apartar el `data/prices.db` existente con otro nombre en lugar de borrarlo, comprobar la base restaurada antes de volver a arrancar, y el comando para comprobar el número de capturas

#### Scenario: Resultado anotado
- **WHEN** se lee el procedimiento de restauración en `docs/`
- **THEN** incluye la fecha de la prueba en el Mac, la copia usada y el número de capturas obtenido
