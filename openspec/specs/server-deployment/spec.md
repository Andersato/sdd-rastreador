# server-deployment Specification

## Purpose

Dejar por escrito, en un runbook del repo, cómo se prepara el VPS, cómo se
lleva a él el histórico sin perder capturas y cómo se actualiza, para poder
repetirlo desde cero sin depender de la memoria.

## Requirements

### Requirement: Runbook del VPS en docs/
`docs/` SHALL contener un runbook del VPS en español, con los comandos
exactos en el orden en que se lanzan y lo que se espera ver tras cada paso.
Debe distinguir qué se lanza en la consola web de IONOS, qué por SSH en el
VPS y qué en el Mac. Todos los comandos los lanza el usuario; los pasos
MUST NOT requerir que un agente se conecte al servidor.

#### Scenario: Datos del servidor
- **WHEN** se lee el inicio del runbook
- **THEN** indica proveedor (IONOS), sistema (Ubuntu 26.04), arquitectura (x86_64), fecha del despliegue (2026-10-16) y la verificación hecha (captura automática a las 15:17 y arranque solo tras un reinicio)

#### Scenario: Dónde se lanza cada comando
- **WHEN** se lee cualquier paso del runbook
- **THEN** está marcado como consola web de IONOS, VPS por SSH o Mac

#### Scenario: Sin secretos
- **WHEN** se busca en el runbook la IP del servidor, contraseñas o claves privadas
- **THEN** no aparecen: se usan marcadores como `<IP_DEL_VPS>` y se explica de dónde sale cada valor

### Requirement: Preparación del servidor
El runbook SHALL describir lo que se hizo de verdad: reinstalación con
Ubuntu 26.04; que el Cloud Config de IONOS no se aplicó; usuario `deploy`
con sudo creado a mano en la consola web; clave con `ssh-copy-id`; acceso
solo por clave; `ufw` solo con OpenSSH; Docker y Compose de los paquetes de
Ubuntu; y clave de despliegue de GitHub de solo lectura.

#### Scenario: Consola web de IONOS
- **WHEN** se lee el paso de creación del usuario `deploy`
- **THEN** avisa de que la consola web no permite pegar y usa teclado inglés (con los caracteres que cambian de sitio, como `-`, `/`, `:` o `@`) y da comandos cortos para teclear a mano

#### Scenario: Acceso solo por clave
- **WHEN** se lee el paso de SSH
- **THEN** incluye `/etc/ssh/sshd_config.d/00-solo-claves.conf` con `PasswordAuthentication no`, `KbdInteractiveAuthentication no` y `PermitRootLogin no` (con el nombre `00-` para que se lea antes que `50-cloud-init.conf`, que trae `PasswordAuthentication yes`: en `sshd` gana el primer valor leído), comprobar la sintaxis con `sshd -t` antes de recargar, verificar los valores efectivos con `sshd -T`, bloquear la contraseña de `deploy` con `passwd -l`, y abrir una segunda sesión SSH antes de cerrar la primera para no quedarse fuera

#### Scenario: Cortafuegos
- **WHEN** se lee el paso de `ufw`
- **THEN** permite solo OpenSSH, se activa después de permitirlo y se comprueba con `ufw status`, que muestra solo OpenSSH

#### Scenario: Docker desde los paquetes de Ubuntu
- **WHEN** se lee el paso de Docker
- **THEN** usa los paquetes de Ubuntu (no el repositorio de Docker), añade `deploy` al grupo `docker`, y comprueba `docker compose version`

#### Scenario: Clave de despliegue
- **WHEN** se lee el paso de GitHub
- **THEN** crea en el VPS una clave propia, la registra en el repo como clave de despliegue sin permiso de escritura y clona con ella

### Requirement: Swap y actualizaciones de seguridad
El runbook SHALL añadir un archivo de swap de 2 GB (el VPS tiene 8 GB de
RAM) que sobreviva a reinicios, poner el sistema en Europe/Madrid y dejar
las actualizaciones de seguridad automáticas activas, con reinicio
automático cuando haga falta a las 05:30 (fuera de la copia de las 04:43 y
de las comprobaciones del minuto 17), con lo que se espera ver.

#### Scenario: Swap (verificación manual)
- **WHEN** se siguen los pasos de swap y se reinicia el VPS
- **THEN** `swapon --show` y `free -h` muestran el archivo de swap de 2 GB y unos 8 GB de RAM

#### Scenario: Actualizaciones automáticas
- **WHEN** se sigue el paso de actualizaciones de seguridad
- **THEN** indica cómo comprobar que `unattended-upgrades` está instalado y activo, qué salida se espera, y cómo activarlo si no lo está

#### Scenario: Reinicio automático a las 05:30
- **WHEN** se sigue el paso de reinicio automático
- **THEN** la configuración de `unattended-upgrades` tiene el reinicio automático activado a las 05:30, el runbook explica por qué esa hora, pone el sistema en Europe/Madrid con `sudo timedatectl set-timezone Europe/Madrid` y lo comprueba con `timedatectl`, que muestra `Europe/Madrid`

#### Scenario: Recuperación tras el reinicio automático (verificación manual)
- **WHEN** una actualización pide reinicio y el VPS se reinicia solo a las 05:30
- **THEN** después de las 06:17 `docker compose logs` muestra la comprobación de arranque con la recogida activada y la de las 06:17, y la copia de las 04:43 de ese día sigue en `./backups`

### Requirement: Configuración del proyecto en el VPS
Antes del primer `docker compose up -d`, el runbook SHALL indicar cómo crear
`.env` con el usuario y grupo de `deploy` y `COLLECTION_ENABLED=true`, y las
carpetas `./data` y `./backups` a nombre de `deploy`, y comprobar que la
variable está en `.env` antes de lanzarlo.

#### Scenario: .env del VPS
- **WHEN** se sigue el paso de configuración con el usuario `deploy` (1000:1000 en el VPS de IONOS)
- **THEN** `.env` contiene `HOST_UID=1000`, `HOST_GID=1000` (los números de `id -u` e `id -g`) y `COLLECTION_ENABLED=true`

#### Scenario: Variable comprobada antes de arrancar
- **WHEN** se lee el paso del primer arranque en el VPS
- **THEN** el paso inmediatamente anterior a `docker compose up -d` añade `COLLECTION_ENABLED=true` a `.env` y lo comprueba con `grep COLLECTION_ENABLED .env`, que muestra `COLLECTION_ENABLED=true`

#### Scenario: Carpetas
- **WHEN** se termina el paso de configuración
- **THEN** `./data` y `./backups` existen y `ls -ld` las muestra a nombre de `deploy`

#### Scenario: Espacio en disco
- **WHEN** se lee el runbook
- **THEN** anota el tamaño del disco del VPS, incluye `df -h` antes del primer arranque y en el procedimiento de actualización, y explica cuánto ocupan aproximadamente la base y las 11 copias

### Requirement: Migración del histórico sin perder capturas
El runbook SHALL describir la migración del Mac al VPS: parar el programador
del Mac; copia con `sqlite3 .backup` (nunca copiar el archivo en caliente);
`scp`; `PRAGMA integrity_check` y número de capturas en el VPS, que MUST
coincidir con el del Mac antes de arrancar el programador del VPS. El
`data/prices.db` del Mac MUST NOT borrarse ni modificarse.

#### Scenario: Migración correcta
- **WHEN** el Mac tiene 8 capturas, se para su programador y se sigue la migración
- **THEN** en el VPS `PRAGMA integrity_check` da `ok`, `SELECT COUNT(*) FROM snapshots` da 8, y solo entonces se lanza `docker compose up -d`

#### Scenario: Número de capturas distinto
- **WHEN** en el VPS la base copiada tiene 7 capturas y el Mac 8
- **THEN** el runbook indica no arrancar el programador del VPS, apartar la copia del VPS con otro nombre (sin borrarla) y repetir desde la copia con `.backup`

#### Scenario: Programador del Mac parado antes de copiar
- **WHEN** se lee la migración
- **THEN** el primer paso es `docker compose stop` en el Mac y comprobar con `docker compose ps` que no queda nada en marcha, y después poner o dejar el `.env` del Mac sin `COLLECTION_ENABLED`

### Requirement: Arranque y verificación tras reinicio
El runbook SHALL describir el primer arranque y una verificación tras
reiniciar el VPS: el programador vuelve solo, el log MUST mostrar que la
recogida está activada y la siguiente comprobación horaria aparece en él.
Si el log dice que está desactivada, indica qué revisar.

#### Scenario: Verificación tras reinicio
- **WHEN** se sigue el paso de verificación tras `sudo reboot`
- **THEN** indica comprobar `docker compose ps` (programador en marcha), que `docker compose logs` muestra la línea de arranque con la recogida activada (con el texto exacto que se espera ver) y, en el siguiente minuto 17, la línea de esa comprobación

#### Scenario: Verificación tras el primer arranque
- **WHEN** se sigue el paso del primer `docker compose up -d` en el VPS
- **THEN** el paso siguiente comprueba en `docker compose logs` que la recogida está activada, antes de dar el despliegue por bueno

#### Scenario: Recogida desactivada por error
- **WHEN** tras arrancar, el log del VPS dice que la recogida está desactivada
- **THEN** el runbook indica revisar `COLLECTION_ENABLED=true` en `.env` y volver a lanzar `docker compose up -d`

### Requirement: Procedimiento de actualización
El runbook SHALL describir cómo actualizar el VPS a una nueva versión del
repo: copia a mano, `git pull`, `docker compose build` y
`docker compose up -d`, y cómo comprobar que el programador sigue
capturando. Los pasos MUST NOT borrar `./data` ni `./backups`.

#### Scenario: Actualización
- **WHEN** se sigue el procedimiento de actualización
- **THEN** los pasos son, en orden: copia a mano, `git pull`, `docker compose build`, `docker compose up -d` y comprobar `docker compose ps` y `docker compose logs`; ninguno usa `docker compose down -v`, `rm` sobre `./data` o `./backups`, ni `git clean`

#### Scenario: Actualizar el VPS ya desplegado a esta versión
- **WHEN** el VPS desplegado el 2026-10-16 (sin `COLLECTION_ENABLED` ni `./backups`) se actualiza a la versión de este cambio
- **THEN** el runbook indica, antes de `docker compose up -d`, crear `./backups` a nombre de `deploy` y añadir `COLLECTION_ENABLED=true` a `.env`, y después comprobar en el log que la recogida está activada; sin esos pasos el VPS dejaría de capturar

#### Scenario: Fallo al construir
- **WHEN** `docker compose build` falla durante una actualización
- **THEN** el runbook indica que el programador anterior sigue en marcha con la imagen anterior y cómo volver a la versión previa con `git checkout`

### Requirement: Aviso esperado de supercronic
El runbook SHALL explicar que el aviso "process reaping disabled, not pid 1"
de supercronic al arrancar el programador es esperado y no requiere hacer
nada.

#### Scenario: Aviso en el log
- **WHEN** se lee la sección de verificación del runbook
- **THEN** menciona el aviso "process reaping disabled, not pid 1" y explica que es normal porque el programa de arranque supervisa supercronic y el init de Docker es el proceso 1

### Requirement: Comprobaciones de Linux en el VPS
`docs/container-checks.md` SHALL incluir cómo repetir en el VPS los
escenarios de "Escritura en ./data en un host Linux" de
`ingestion-container`, en una copia temporal del proyecto con otro nombre de
proyecto de Compose y un servidor local con las respuestas de
`tests/fixtures/`. MUST NOT usar `~/sdd-rastreador/data` ni pedir nada a la
API real, y se anota la fecha y el resultado.

#### Scenario: Carpeta temporal
- **WHEN** se siguen las comprobaciones de Linux en el VPS
- **THEN** todas trabajan en una carpeta temporal fuera de `~/sdd-rastreador` (por ejemplo `~/ingest-check-<fecha>`) que se borra al terminar, y `~/sdd-rastreador/data` y `~/sdd-rastreador/backups` quedan exactamente igual que antes

#### Scenario: Sin tocar el programador real
- **WHEN** se siguen las comprobaciones de Linux con el programador real en marcha
- **THEN** el programador real sigue en marcha sin reiniciarse durante y después de las pruebas, porque las pruebas usan otro nombre de proyecto de Compose y solo `docker compose run --rm ingest --url <servidor local>`, nunca `up`; en la copia temporal no se reconstruye la imagen (usa la del programador real, del mismo commit), porque su nombre es fijo y se sustituiría la del programador

#### Scenario: Servidor de respuestas guardadas sin abrir puertos
- **WHEN** se lee cómo se sirven las respuestas de `tests/fixtures/` en las comprobaciones de Linux
- **THEN** el servidor local es accesible para el contenedor de la ingesta sin añadir reglas a `ufw` ni abrir ningún puerto al exterior, y `ufw status` muestra solo OpenSSH antes y después

#### Scenario: Escenarios cubiertos
- **WHEN** se lee la sección de comprobaciones de Linux en el VPS
- **THEN** cubre los cuatro escenarios de "Escritura en ./data en un host Linux" con el usuario `deploy`, con el resultado esperado de cada uno y un hueco para anotar fecha y resultado

#### Scenario: Conexión HTTPS real
- **WHEN** se lee la comprobación de conexión real por HTTPS en `docs/container-checks.md`
- **THEN** indica que se verificó desde el VPS con la captura automática de las 15:17 del 2026-10-16 y no pide repetirla

### Requirement: API en el VPS solo por túnel SSH
El runbook SHALL describir cómo actualizar el VPS a la versión con la API,
comprobar que la API responde dentro del servidor, que su puerto solo
escucha en `127.0.0.1` y que `ufw` sigue igual, y cómo usarla desde el Mac
con un túnel SSH. MUST NOT indicar abrir ningún puerto en `ufw` ni publicar
la API en otra dirección.

#### Scenario: Actualización a la versión con la API
- **WHEN** se sigue el procedimiento de actualización para esta versión
- **THEN** tras `docker compose up -d` indica comprobar que `docker compose ps` muestra el programador y la API en marcha, que `curl -s http://127.0.0.1:8000/api/health` en el VPS devuelve `status` `ok`, que `sudo ss -tlnp` solo muestra `127.0.0.1:8000` para ese puerto, y que `sudo ufw status` sigue mostrando solo OpenSSH

#### Scenario: Salud justo después de arrancar
- **WHEN** el `curl` de la salud justo después de `docker compose up -d` devuelve `base_ocupada` (el programador recién arrancado está guardando una captura) o `status` `desactualizada`
- **THEN** el runbook indica repetirlo pasados unos segundos o tras la siguiente captura, y solo investigar si sigue igual

#### Scenario: Túnel desde el Mac
- **WHEN** se lee el paso de uso desde el Mac
- **THEN** da el comando `ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>`, explica que mientras está abierto la API se usa en `http://127.0.0.1:8000/api/docs` del Mac, cómo cerrarlo (Ctrl+C), y que si el puerto 8000 del Mac está ocupado (por ejemplo, por la API local) se usa otro puerto local como `-L 8001:127.0.0.1:8000`

#### Scenario: Sin secretos
- **WHEN** se revisa el runbook
- **THEN** usa el marcador `<IP_DEL_VPS>` y no contiene la dirección real del servidor ni claves

#### Scenario: Puerto expuesto por error
- **WHEN** `sudo ss -tlnp` muestra `0.0.0.0:8000` o `[::]:8000`
- **THEN** el runbook indica parar la API con `docker compose stop api` en ese momento y revisar los puertos del servicio `api` en `docker-compose.yml`, sin tocar `ufw`
