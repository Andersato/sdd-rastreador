# Proposal

## Why

La recogida ya funciona en el VPS (IONOS, Ubuntu 26.04, x86_64), desplegada
a mano el 2026-10-16: captura automática verificada a las 15:17 y arranque
solo tras un reinicio. Pero lo que se hizo no está escrito en ningún sitio,
el histórico solo existe en un disco (el del VPS) y nada impide que el Mac
siga capturando por su cuenta y parta el histórico en dos bases. Este
cambio documenta el despliegue y añade lo necesario para no perder el
histórico.

## What Changes

- **Runbook del VPS** en `docs/`, con lo que se hizo de verdad para poder
  repetirlo: reinstalación con Ubuntu 26.04 (el Cloud Config de IONOS no se
  aplicó), usuario `deploy` con sudo creado a mano por la consola web (que
  no permite pegar y usa teclado inglés), clave SSH con `ssh-copy-id`,
  acceso solo por clave (`PasswordAuthentication no`, `PermitRootLogin no`),
  `ufw` solo con OpenSSH, Docker y Compose desde los paquetes de Ubuntu,
  clave de despliegue de GitHub de solo lectura, migración del histórico
  (parar el programador del Mac, `sqlite3 .backup`, `scp`,
  `integrity_check`, mismo número de capturas) y verificación tras reinicio.
  Añade: archivo de swap de 2 GB y comprobación de que las actualizaciones
  de seguridad automáticas están activas. Procedimiento de actualización:
  `git pull` + `docker compose build` + `docker compose up -d`.
- **Copias de seguridad diarias en el VPS**, lanzadas por el mismo
  supercronic del programador a una hora fija de madrugada: copia en
  caliente segura con la API de backup de SQLite (nunca copiando el
  archivo), bajo el mismo bloqueo que la ingesta; verificada con
  `PRAGMA integrity_check` antes de darla por buena; comprimida; en una
  carpeta propia montada (`./backups`, fuera de `./data`); rotación de 7
  diarias y 4 semanales; resultado en el log del programador.
- **Copia fuera del VPS**: un script del repo que el Mac ejecuta para
  descargar las copias con `rsync` por SSH (modelo *pull*: desde el VPS no
  se pueden borrar las copias del Mac), verificando la integridad de cada
  copia nueva, más instrucciones para programarlo con `launchd`.
- **BREAKING — una sola máquina recoge**: el programador solo captura (y
  solo hace copias) si el `.env` de esa máquina lo habilita explícitamente
  con `COLLECTION_ENABLED=true`. Sin esa variable arranca, lo dice en el log
  y no hace ninguna petición a la API. En el Mac, un `docker compose up -d`
  por costumbre deja de capturar.
- **Restauración** documentada y probada una vez: restaurar la última copia
  en el Mac, en una carpeta aparte, y comprobar integridad y número de
  capturas.
- `design.md` documentará que el aviso de supercronic "process reaping
  disabled, not pid 1" es esperado (el programa de arranque lo supervisa y
  el init de Docker, tini, es el proceso 1).

### Decisiones tomadas (revisión del 2026-10-16)

1. **Variable**: `COLLECTION_ENABLED`. Solo `true` (ignorando espacios y
   mayúsculas) habilita. Ausente, vacía o `false`: desactivada. Cualquier
   otro valor (`yes`, `1`, `si`…): configuración no válida, se trata como
   desactivada y el log indica el valor recibido.
2. **Mensaje de desactivada**: al arrancar y en cada comprobación horaria
   (igual que "Configuración no válida").
3. **La variable solo afecta al programador**: `docker compose run --rm
   ingest` sigue funcionando en cualquier máquina (hace falta para las
   pruebas con `--url`). El README avisa de no lanzarlo contra la API real
   en el Mac.
4. **Solo copia la máquina que recoge** (la misma variable).
5. **Hora de la copia**: 04:43 de Madrid. Además, en la comprobación de
   arranque se hace una copia si no hay ninguna o la más reciente tiene más
   de 26 h.
6. **Copia con una ingesta en curso**: espera como mucho 10 minutos; si se
   agota, la copia del día queda pendiente y se reintenta en cada
   comprobación horaria de ese día hasta hacerse. Igual si la última
   ingesta quedó a medias (`prices.db-journal`): la copia no la deshace,
   porque nunca toca `./data`. Los demás fallos no se reintentan hasta el
   día siguiente.
6b. **Bloqueo solo durante el volcado**: verificar y comprimir se hace ya
   sin él, para no retrasar capturas cuando la base ocupe varios GB. Una
   ingesta que encuentra el bloqueo cogido por una copia dice "ya hay otra
   ingesta o copia en curso".
6c. **Base con versión de estructura desconocida**: se copia igualmente si
   pasa `integrity_check` y tiene capturas, con un aviso, para no parar las
   copias tras volver atrás una actualización.
7. **Nombre y rotación**: `prices-AAAA-MM-DD.db.gz` (fecha de Madrid). 7
   diarias más 4 semanales adicionales (la última copia de cada una de las
   4 semanas más recientes que no tienen ninguna diaria): como mucho 11
   archivos. Una segunda copia el mismo día sustituye a la anterior solo
   cuando ya está verificada. La rotación solo se hace tras una copia
   correcta y nunca toca archivos con otro nombre.
8. **`./backups` solo la monta el programador**: si falta,
   `docker compose up -d` falla sin crearla; `docker compose run --rm
   ingest` funciona sin ella.
9. **Copia a mano**: un comando documentado lanza una copia fuera de hora,
   con el programador en marcha o parado (servicio manual aparte que monta
   `./backups`; `ingest` no la monta). Con una ingesta en curso, espera 10
   minutos y si no, falla; nunca queda pendiente.
9b. **Archivos de `./backups`**: los nombres con fecha imposible o futura
   son ajenos (con aviso); los temporales de una copia cortada los borra
   la siguiente copia.
10. **Carpeta del Mac**: fuera del repo, configurable; por defecto
    `~/Backups/precios-gasolineras/`.
11. **Rotación en el Mac** igual que en el VPS, decidida solo con lo que hay
    en el Mac (al ritmo actual, unos 3 MB por captura y 4 capturas al día,
    sin rotación crecería decenas de GB al año).
12. **Copia descargada que no pasa la verificación**: se aparta a
    `rechazadas/`, no cuenta para la rotación y el script termina con error.
    Se reintenta en cada ejecución (sustituye a la de igual nombre en
    `rechazadas/`). Una copia del mismo día que cambia en el VPS se
    descarga aparte y solo sustituye a la anterior ya verificada. Solo se
    descargan archivos `prices-AAAA-MM-DD.db.gz`.
12b. **`launchd`**: a las 10:00 (`StartCalendarInterval`) y además
    `RunAtLoad`, para que se ejecute al iniciar sesión si el Mac estaba
    apagado a esa hora.
13. **Acceso del Mac al VPS**: clave SSH dedicada solo a las copias, sin
    contraseña (para `launchd`), nunca la clave personal; restringida en
    `authorized_keys` con `rrsync` a leer `backups/`.
14. **Restauración**: nunca sobrescribe un `prices.db` existente. En el Mac,
    siempre en una carpeta nueva; en un VPS, con el programador parado y
    apartando el `prices.db` existente con otro nombre. Solo se prueba la
    del Mac.
15. **Comprobaciones de Linux** de `docs/container-checks.md`: se repiten
    en el VPS en una carpeta temporal, nunca sobre `~/sdd-rastreador/data`.
    La conexión HTTPS real ya está verificada (captura de las 15:17 del
    2026-10-16).
16. **Runbook**: antes del `docker compose up -d` en el VPS se añade
    `COLLECTION_ENABLED=true` a `.env`, y la verificación comprueba en el log
    que la recogida está activada. Lo mismo al actualizar el VPS ya
    desplegado a esta versión, que hoy no tiene la variable ni `./backups`.
17. **Usuario `deploy`**: está en el grupo `docker` (confirmado).
18. **`COLLECTION_ENABLED`**: `true` y `false` se leen sin distinguir
    mayúsculas ni espacios.
19. **VPS**: 8 GB de RAM, swap de 2 GB, sistema en Europe/Madrid
    (`timedatectl set-timezone`). `unattended-upgrades` con reinicio
    automático cuando haga falta a las 05:30 (no coincide con la copia de
    las 04:43 ni con las comprobaciones del minuto 17).
19b. **Dos copias a la vez**: nunca se solapan; la segunda espera, con los
    10 minutos contados en total (ingesta u otra copia). Si se agotan, la
    diaria queda pendiente y la copia a mano falla.
19c. **Precedencia**: la configuración no válida (root, grupo, intervalo,
    valor no válido) se muestra antes que "recogida desactivada".
20. **Un solo cambio**: el VPS necesita la variable y las copias a la vez.
    `tasks.md` se agrupará en tres bloques: variable + runbook, copias en
    el VPS, y descarga al Mac + restauración.
21. **`rsync` del Mac**: el de macOS (`openrsync`) no funciona con `rrsync`
    (comprobado el 2026-10-16). Dependencia nueva aprobada: `rsync` de
    Homebrew, solo en el Mac y solo para el script de descarga, que lo usa
    de forma explícita (nunca `/usr/bin/rsync`) y falla con un mensaje
    claro si no está instalado. Se documenta en el README y en el runbook.
21b. **SSH en el VPS**: el `50-cloud-init.conf` de la imagen tenía
    `PasswordAuthentication yes` y anulaba el `99-solo-claves.conf` (en
    `sshd` gana el primer valor leído). Se resolvió con
    `/etc/ssh/sshd_config.d/00-solo-claves.conf` (`PasswordAuthentication
    no`, `KbdInteractiveAuthentication no`, `PermitRootLogin no`) y la
    contraseña de `deploy` bloqueada con `passwd -l`. La verificación del
    runbook usa `sshd -T` (valores efectivos).
22. **Runbook**: refleja lo que se hizo de verdad; las tareas pedirán al
    usuario su historial de comandos o sus salidas.

### Fuera de alcance

- API web e interfaz.
- Alertas o notificaciones si deja de capturar o falla una copia: solo el
  log del programador y la salida del script del Mac.
- Guardar solo los precios que cambian.
- Automatizar la creación del servidor (Cloud Config, Ansible…): el runbook
  es manual.
- Que un agente se conecte al VPS: todos los comandos en el servidor los
  lanza el usuario.
- Recuperar una copia pendiente si el programador se reinicia ese día: la
  cubre solo la regla de las 26 h.
- Retención más larga (por ejemplo, una copia mensual en el Mac). Riesgo
  anotado: un error que estropee datos sin romper la integridad llegaría a
  todas las copias en unas 5 semanas.
- Copias cifradas o en un tercer sitio (nube).

## Capabilities

### New Capabilities
- `database-backup`: copias de seguridad de la base de datos en la máquina
  que recoge (cuándo, cómo se hacen y verifican, rotación, log), su descarga
  verificada al Mac y la restauración.
- `server-deployment`: runbook del VPS: preparación del servidor, migración
  del histórico, verificación tras reinicio y procedimiento de
  actualización.

### Modified Capabilities
- `scheduled-collection`: el programador solo captura si `.env` lo habilita
  con `COLLECTION_ENABLED=true`; cambian la activación (que tampoco lanza
  la copia a mano), las comprobaciones, "Cuándo toca capturar" (mensaje
  "otra ingesta o copia en curso"), la línea de log y el README.
- `price-ingestion`: la copia de seguridad comparte el bloqueo de "una sola
  ingesta a la vez" y es la única que espera a que se libere.
- `ingestion-container`: `backups/` fuera del contexto de construcción; los
  escenarios del programador indican `COLLECTION_ENABLED=true`.

## Impact

- `docker-compose.yml`: nueva carpeta `./backups` montada solo en el
  programador (sin crearla si falta) y variable `COLLECTION_ENABLED`.
- `container/`: el crontab gana la línea de la copia; comprobación de la
  variable antes de capturar o copiar.
- `src/ingestion/` (o módulo hermano sin dependencias de API web ni UI):
  copia con la API de backup de SQLite bajo el bloqueo de la carpeta,
  verificación, compresión y rotación.
- Script nuevo para el Mac (Python de la biblioteca estándar + `rsync` de
  Homebrew, dependencia nueva aprobada solo para el Mac y solo para este
  script).
- `.gitignore` y `.dockerignore`: `backups/`.
- `docs/`: runbook del VPS, copia fuera del VPS con `launchd` y `rrsync`,
  restauración, y comprobaciones de Linux en el VPS en
  `docs/container-checks.md`. README: `COLLECTION_ENABLED`, `./backups` y copias.
- Tests de Docker existentes del programador: necesitan
  `COLLECTION_ENABLED=true` en su `.env` y la carpeta `./backups` en sus
  proyectos temporales.
- **Datos guardados**: la estructura de la base no cambia. La copia solo
  lee la base (API de backup de SQLite) y no deja archivos en `./data`. El
  `data/prices.db` del Mac (histórico anterior a la migración) no se toca;
  una restauración nunca sobrescribe un `prices.db` existente.
- **API del Ministerio**: sin cambios en el VPS; en el Mac, cero peticiones
  del programador salvo que se habilite.
