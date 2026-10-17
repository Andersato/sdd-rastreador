# Design

## Context

Ver proposal.md (Why y decisiones tomadas). Estado actual relevante:

- `docker-compose.yml` define `ingest` (perfil `manual`) y `scheduler` sobre
  un ancla común `x-app` que monta solo `./data` con
  `create_host_path: false`.
- `container/scheduler.py` escribe un crontab de una línea
  (`17 * * * * python /app/container/check.py`), lanza supercronic y una
  comprobación de arranque, y reenvía SIGTERM a todo el contenedor.
- `container/check.py` rechaza root/grupo root y llama a
  `src.ingestion.scheduled.main`, que valida el intervalo, coge el bloqueo
  y decide si captura.
- `src/ingestion/lock.py`: `data_dir_lock` hace `flock` no bloqueante
  (`LOCK_NB`) sobre la carpeta de la base y lanza `IngestionBusy`.
- `storage.read_last_snapshot` abre la base en solo lectura y distingue
  diario pendiente (`SQLITE_READONLY_ROLLBACK` → `InterruptedIngestion`),
  versión desconocida y archivo ilegible.
- En el Mac (macOS 26.7.1) `rsync` es `openrsync` (protocolo 29,
  "rsync version 2.6.9 compatible").
- El VPS ya funciona con la versión anterior, sin `COLLECTION_ENABLED` ni
  `./backups`: si se actualiza sin los pasos de la migración, deja de
  capturar.

## Goals / Non-Goals

**Goals:**
- Copias en caliente, verificadas y rotadas, sin crear ni modificar nada en
  `./data` y sin retrasar las ingestas más que el volcado.
- Reutilizar el bloqueo y los mensajes existentes; solo biblioteca estándar
  de Python más `rsync`/`ssh` del sistema.
- Que la misma lógica de rotación y verificación sirva en el VPS y en el
  Mac.

**Non-Goals:**
- Cambiar la estructura de la base o el formato de las capturas.
- Gestionar el VPS desde el repo (nada de Ansible ni scripts remotos): el
  runbook son comandos que lanza el usuario.
- Recuperar una copia pendiente tras reiniciar el programador ese día (solo
  la regla de 26 h).

## Decisions

### D1. Paquete nuevo `src/backup/`
Módulos: `rotation.py` (qué copias se conservan, función pura),
`verify.py` (descomprimir, `integrity_check`, contar capturas), `make.py`
(copia en la máquina que recoge) y `pull.py` (descarga en el Mac). Depende de
`src.ingestion` (bloqueo, lectura de la base, formato de cifras), nunca al
revés: la ingesta sigue sin saber nada de copias.
*Alternativas:* meterlo en `src/ingestion/` (mezcla responsabilidades);
un script suelto en `scripts/` para el Mac (duplicaría rotación y
verificación). El Mac lo ejecuta con `.venv/bin/python -m src.backup.pull`;
la imagen ya copia `src/`.

### D2. Bloqueos: el de `./data` solo para el volcado y otro propio en `./backups`
Una copia coge primero el `flock` de la carpeta `./backups` (exclusión entre
copias) y después el de `./data` (exclusión con las ingestas). Al terminar
el volcado suelta el de `./data`; verificación, compresión y rotación se
hacen solo con el de `./backups`. Las ingestas nunca cogen el de `./backups`,
así que no hay ciclo de espera posible ni una ingesta espera a una copia que
está comprimiendo.
`data_dir_lock` gana un parámetro `wait_s` (0 por defecto, comportamiento
actual): reintenta `LOCK_NB` cada segundo hasta agotar el plazo. Los dos
bloqueos comparten un único plazo de 10 minutos ("cuentan en total").
*Alternativas:* `flock` bloqueante con `alarm` (señales mezcladas con
SIGTERM del programador); un solo bloqueo para todo el proceso (retrasaría
capturas cuando la base ocupe GB).

### D3. Volcado con la API de backup desde una conexión de solo lectura
La fuente se abre con `mode=ro` (no crea diario ni otros archivos en
`./data`). Antes del volcado se lee `user_version` y la tabla de capturas:
- diario pendiente (`SQLITE_READONLY_ROLLBACK`) → copia **pendiente**;
- versión distinta de la conocida → se sigue, con aviso en el log;
- sin tabla de capturas o sin filas → "nada que copiar";
- archivo ilegible → error.

El destino es un temporal en `./backups`. `Connection.backup` se hace por
pasos (`pages`) con una función de progreso en Python, para que SIGTERM
(`sigterm_as_interrupt`) interrumpa en segundos y `docker compose stop`
termine en menos de 15 s.
*Alternativa descartada:* `VACUUM INTO` (necesita conexión de escritura
sobre la fuente; la spec exige la API de backup).

### D4. Verificación, compresión y publicación atómica
Sobre el volcado: `PRAGMA integrity_check` = `ok` y al menos una captura.
Después gzip a otro temporal, que se relee entero comparando el SHA-256 de
lo descomprimido con el del volcado. Solo entonces `fsync` y `os.replace` al
nombre final `prices-AAAA-MM-DD.db.gz`, que sustituye de forma atómica a la
del mismo día. Un `finally` borra los temporales ante cualquier error,
incluido disco lleno o interrupción.
Temporales: `.prices-AAAA-MM-DD.<pid>.tmp` y `.gz.tmp` (ocultos, con su
propio patrón). Como solo hay una copia a la vez (D2), cualquier temporal
que encuentre una copia con el bloqueo de `./backups` es de una copia
cortada y se puede borrar.

### D5. Rotación por la fecha del nombre
`rotation.keep(dates, today)` recibe las fechas válidas: las del patrón
exacto, fecha real y no posterior a `today` (fecha de Madrid). Diarias: las
7 más recientes. Semanales: de las demás, la última de cada semana ISO
(lunes a domingo) que no contenga ninguna diaria, las 4 semanas más
recientes con copia. El resto con el patrón se borra; los nombres con fecha
imposible o futura se ignoran (con aviso las futuras). La rotación solo se
llama tras publicar una copia correcta.

### D6. Cuándo se copia: crontab, arranque y marca de pendiente
- Crontab: se añade `43 4 * * * python /app/container/backup.py --daily`.
- Arranque: `scheduler.py` lanza `check.py --startup`; tras su decisión de
  captura (y su ingesta), si la recogida está activada y no hay copias o la
  más reciente (por fecha del nombre) tiene `mtime` de hace más de 26 h, hace
  una copia. `os.replace` conserva el `mtime` del temporal recién escrito.
- Pendiente: las comprobaciones son procesos distintos del mismo
  contenedor, así que el estado se guarda en `/tmp/backup-pending` del
  contenedor del programador (no en `./data` ni en `./backups`), con la
  fecha de Madrid. Lo crea una copia diaria o de arranque que se rinde por
  bloqueo o diario pendiente. Cada `check.py` horario lo consulta después
  de su decisión de captura, haya capturado o no, y lo borra la copia
  correcta. Una marca con fecha anterior a hoy se ignora y se borra. El
  reintento se salta (y borra la marca) si ya hay en `./backups` una copia
  de hoy con `mtime` posterior a la marca, por ejemplo una copia a mano, que
  corre en otro contenedor y nunca crea ni ve la marca. Esa comprobación
  se repite después de conseguir el bloqueo de `./backups`, por si el
  reintento ha esperado a una copia a mano que acaba de terminar.
  `/tmp` del contenedor sobrevive a un reinicio de Docker (`restart:
  unless-stopped` reutiliza el contenedor), así que `scheduler.py` borra la
  marca al arrancar, igual que reescribe el crontab: tras reiniciar el
  programador solo cuenta la regla de 26 h, como dice el fuera de alcance.

### D7. Servicio `backup` para la copia a mano
Nuevo servicio en el perfil `manual` (como `ingest`), misma imagen, entrada
`python /app/container/backup.py --manual`, con `./data` y `./backups`
montadas sin crear. Comando documentado: `docker compose run --rm backup`.
Funciona con el programador parado. `ingest` sigue montando solo `./data`.
Compose: el ancla `x-app` deja de definir `volumes`; dos anclas de volumen
(`data`, `backups`) que cada servicio combina.
Códigos de salida de la copia a mano: 0 correcta, 1 error, 2 configuración
no válida o recogida desactivada, 3 otra ingesta o copia en curso (igual
que `IngestionBusy` en la ingesta).

### D8. `COLLECTION_ENABLED` y precedencia
Compose la pasa a `scheduler` y `backup` como `${COLLECTION_ENABLED:-}`.
El servicio `backup` lleva también `TZ: Europe/Madrid`, como `scheduler`, y
`make.py` calcula la fecha del nombre con `ZoneInfo("Europe/Madrid")`
(como `madrid_time`), sin depender de `TZ`.
`parse_enabled(text)` en `container/settings.py`: `strip().lower()`;
`true` → activada; ausente, vacío o `false` → desactivada; otro valor →
`InvalidSetting` con el valor recibido.
- `check.py`, para la **captura**, comprueba en este orden: usuario root,
  grupo root, intervalo, valor de `COLLECTION_ENABLED`, desactivada; el
  primer fallo da la línea de log y no se captura (sin bloqueo, base ni
  petición).
- Para las **copias** (la de arranque y el reintento de una pendiente, que
  hace `check.py`, y las de `backup.py`) se comprueba lo mismo **salvo el
  intervalo**: usuario root, grupo root, valor de `COLLECTION_ENABLED`,
  desactivada. El intervalo solo afecta a la captura; con un intervalo no
  válido, `check.py` registra la configuración no válida, no captura, y aun
  así hace la copia de arranque o el reintento si tocan. Root y grupo root
  lo paran todo, porque los archivos quedarían a nombre de root.

La línea de arranque de `scheduler.py` añade "recogida activada",
"recogida desactivada" o "COLLECTION_ENABLED no válido".

**Nota de pruebas:** Compose recorta los espacios de los valores sin
comillas de `.env`, así que `COLLECTION_ENABLED= true ` puede llegar ya como
`true`. La normalización se prueba también pasando la variable
directamente: tests unitarios de `parse_enabled`, y tests de Docker que
cubren los dos programas que la leen: `scheduler.py` (línea de arranque),
arrancando con el archivo de Compose adicional de los tests con
`COLLECTION_ENABLED: " TRUE "` entre comillas, y `check.py`/`backup.py` con
`exec -T -e COLLECTION_ENABLED=" TRUE " scheduler …` y
`run -e COLLECTION_ENABLED=" TRUE " backup`.

### D9. Mensaje "ya hay otra ingesta o copia en curso"
`IngestionBusy` pasa a decir "ya hay otra ingesta o copia en curso sobre
<carpeta>" y la línea del programador "otra ingesta o copia en curso; no se
captura". Es un cambio de texto que viene de la spec: los tests que esperan
el texto anterior se actualizan (lista en tasks.md, grupo 1).

### D10. Descarga al Mac (`src.backup.pull`)
Argumentos: `--host deploy@<IP_DEL_VPS>`, `--dest` (por defecto
`~/Backups/precios-gasolineras`), `--key` (por defecto
`~/.ssh/precios-backups`) y `--source` (carpeta local en lugar de SSH, solo
para tests). SSH con `-i <clave> -o IdentitiesOnly=yes -o BatchMode=yes`:
nunca prueba otras claves ni pide contraseña. Si la clave no existe,
termina antes de conectar.
Pasos: (1) comprueba la clave y lista en remoto con `rsync --list-only`
filtrando `prices-????-??-??.db.gz` (los temporales ocultos y los ajenos no
pasan el filtro); si algo falla aquí, termina sin crear ni tocar nada en el
Mac; (2) solo entonces crea la carpeta si no existe y borra lo que quedara
en `descargando/` de un corte; (3) para cada copia que falte en
la carpeta principal o difiera en tamaño o fecha, la descarga con
`rsync -t` a `descargando/`; (4) la verifica (D4, en `descargando/`); si
pasa, `os.replace` a la carpeta principal; si no, a `rechazadas/`
(sustituyendo la de igual nombre); (5) si no ha fallado nada, rotación
local (D5) con la fecha de Madrid del Mac; (6) resumen y código 0, o 1 si
algo ha fallado.
**`rsync` de Homebrew, siempre explícito** (ver D11): el script nunca usa
el `/usr/bin/rsync` del sistema. Busca `/opt/homebrew/bin/rsync` (Apple
Silicon) y `/usr/local/bin/rsync` (Intel), o el que se indique con
`--rsync`, y comprueba con `--version` que es el rsync de GNU (versión 3.x),
no `openrsync`. Si no lo encuentra, termina antes de conectar con un
mensaje claro: falta el rsync de Homebrew, `brew install rsync`. Opciones
usadas: `-t`, `--list-only`, `--include/--exclude`, `-e`; nada de
`--delete`.

### D11. Clave dedicada con `rrsync`
En el Mac, `ssh-keygen -t ed25519 -N "" -f ~/.ssh/precios-backups`. En el
VPS, una línea a mano en `~deploy/.ssh/authorized_keys`:
`command="rrsync -ro /home/deploy/sdd-rastreador/backups",restrict ssh-ed25519 …`
(`restrict` quita terminal, reenvíos y agente). El Mac pide la ruta `.`,
que `rrsync` resuelve dentro de `backups/`. La primera conexión se acepta a
mano (huella en `known_hosts`) antes de cargar `launchd`, porque
`BatchMode` no puede preguntar.
**`openrsync` + `rrsync` no funciona** (tarea 3.1, 2026-10-16): con el
`rsync` de macOS, `rrsync` rechaza el comando ("invalid rsync-command syntax
or options"). Con el `rsync` de Homebrew funcionan el listado y la descarga.
El usuario aprueba el `rsync` de Homebrew como **dependencia del Mac, solo
para el script de descarga** (`brew install rsync`); se documenta en el
README y en el runbook. La clave dedicada no abre terminal
("rrsync error: Not invoked via sshd").

### D12. `launchd`
`docs/offsite-backups.md` incluye `es.preciosgasolineras.pull-backups.plist`
para `~/Library/LaunchAgents/`, con `StartCalendarInterval` a las 10:00,
`RunAtLoad`, `ProgramArguments` con la ruta absoluta de
`.venv/bin/python` y `<IP_DEL_VPS>` como marcador, y
`StandardOutPath`/`StandardErrorPath` en
`~/Library/Logs/precios-gasolineras-backups.log`. Comandos:
`launchctl bootstrap gui/$(id -u) …`, `launchctl print gui/$(id -u)/…`,
`launchctl bootout gui/$(id -u)/…`.

### D13. Aviso "process reaping disabled, not pid 1" de supercronic
Es esperado. Con `init: true`, el proceso 1 del contenedor es tini, que
recoge los procesos huérfanos. supercronic no es el proceso 1 (lo lanza
`scheduler.py`, que lo vigila y recoge a sus hijos), así que avisa de que
no hará él esa tarea. No hay que hacer nada; el runbook lo explica junto a
la verificación.

### D14. Documentación
- `docs/vps-deployment.md`: runbook (preparación, swap, zona horaria,
  `unattended-upgrades`, configuración, migración, verificación,
  actualización, copia a mano, aviso de supercronic).
- `docs/offsite-backups.md`: clave dedicada, `rrsync`, `pull`, `launchd`.
- `docs/restore.md`: restauración en el Mac (probada, con fecha y
  resultado) y en un VPS.
- `docs/container-checks.md`: comprobaciones de Linux en el VPS y HTTPS ya
  verificado.
- README: `COLLECTION_ENABLED`, `./backups` y enlaces a los anteriores.
Tests de contenido como `test_scenarios_readme.py` para lo que la spec
exige que aparezca en la documentación.

## Risks / Trade-offs

- [`openrsync` no acepta las opciones que exige `rrsync`] → confirmado en
  la tarea 3.1; se usa el `rsync` de Homebrew, explícito y comprobado por
  versión, con un error claro si falta (D10).
- [La marca de pendiente queda de un día anterior (el contenedor sigue en
  marcha tras medianoche)] → se ignora y se borra si su fecha no es la de
  hoy.
- [Con la base en varios GB, la copia tarda minutos y ocupa espacio
  temporal (volcado + gz)] → el bloqueo de `./data` solo cubre el volcado;
  el runbook pide `df -h` y explica el espacio necesario (base + 11 copias
  + un volcado).
- [Una corrupción lógica que pasa `integrity_check` llega a todas las
  copias en unas 5 semanas] → anotado como fuera de alcance (copia
  mensual).
- [`BatchMode` falla la primera vez sin `known_hosts`] → el runbook pide
  una primera conexión manual.
- [Compose recorta espacios de `.env`] → pruebas de normalización también
  pasando la variable directamente (D8).
- [El programador se reinicia con una copia pendiente] → la marca se
  borra al arrancar (fuera de alcance); queda la regla de 26 h, y la copia
  de las 04:43 del día siguiente.
- [El Mac está apagado durante días] → el modelo pull no pierde nada: la
  siguiente ejecución descarga lo que siga en el VPS.

## Migration Plan

La estructura de la base no cambia y la copia solo lee `./data`.
Actualización del VPS ya desplegado (la ejecuta el usuario, con los
comandos del runbook):
1. Copia de seguridad previa (aún no existe la copia a mano) abriendo la
   base en solo lectura, para no deshacer un diario pendiente ni modificar
   `./data` con el programador en marcha:
   `sqlite3 'file:data/prices.db?mode=ro' ".backup $HOME/antes-de-actualizar-AAAA-MM-DD.db"`,
   fuera de `./backups` (no entra en la rotación), y `integrity_check` sobre
   ella. Si falla por un diario pendiente, esperar a la siguiente
   comprobación horaria y repetir.
2. `git pull`, `mkdir backups` (a nombre de `deploy`), añadir
   `COLLECTION_ENABLED=true` a `.env` y comprobarlo con `grep`.
3. `docker compose build` y `docker compose up -d`; comprobar en el log
   "recogida activada" y la siguiente comprobación del minuto 17.
4. `docker compose run --rm backup` y comprobar la copia.

En el Mac: `mkdir backups` si se quiere usar `up -d`; sin
`COLLECTION_ENABLED`, el programador no hace nada. `data/prices.db` del Mac
no se toca.
**Vuelta atrás:** `git checkout <commit anterior>`, `docker compose build`,
`docker compose up -d`. La versión anterior ignora `COLLECTION_ENABLED` y
`./backups`; `./data` y las copias no se tocan.
