# Runbook del VPS

Cómo se preparó el servidor que recoge los precios, cómo se llevó a él el
histórico y cómo se actualiza. Está escrito a partir de lo que se hizo de
verdad, para poder repetirlo desde cero.

- **Servidor:** IONOS, plan VPS 4-8-240 (4 vCPU, 8 GB de RAM, 240 GB de
  disco NVMe).
- **Sistema:** Ubuntu 26.04 (26.04.1 LTS, núcleo 7.0), **x86_64**.
- **Desplegado:** 2026-10-16, a mano.
- **Verificado:** captura automática a las **15:17** del 2026-10-16, y
  **arranque solo tras un reinicio** del servidor.

Todos los comandos los lanza la persona responsable; ningún agente se
conecta al servidor. Cada bloque indica **dónde** se lanza:

- **[Consola IONOS]**: la consola web del panel de IONOS, como `root`.
- **[VPS]**: por SSH en el servidor, como `deploy`, desde `~/sdd-rastreador`
  salvo que se diga otra cosa.
- **[Mac]**: en el Mac, desde la carpeta del proyecto salvo que se diga otra
  cosa.

En este documento no hay datos secretos. Los marcadores se sustituyen así:

- `<IP_DEL_VPS>`: la IP pública, en el panel de IONOS (Servidores → el VPS).
- `<CLAVE_PUBLICA_PERSONAL>`: la línea de `~/.ssh/id_ed25519_personal.pub` del Mac.
- `<CLAVE_PUBLICA_COPIAS>`: la línea de `~/.ssh/precios-backups.pub` del Mac.

**Consejo general:** cuando un bloque tiene instalaciones largas, `exit` o
`ssh`, pega **línea a línea**. El 16/10, al pegar tres líneas juntas, la
instalación de Docker se comió parte de la entrada, `exit` cerró la sesión y
la línea siguiente se ejecutó en el Mac.

## 0. Por qué se reinstaló

El servidor tenía una aplicación antigua (Apache, PHP, MySQL, Jenkins,
Elasticsearch con la mitad de la RAM) y **no tenía swap**: se quedó sin
memoria (`Out of memory: Killed process … (java)`) y dejó de responder,
incluido SSH (`ssh` daba `timed out`). Se hizo copia de esa aplicación y se
reinstaló desde cero. Por eso este runbook añade un archivo de swap (sección
5) como red de seguridad.

## 1. Reinstalar Ubuntu 26.04

**[Panel de IONOS]** Servidores → el VPS → Reinstalar imagen →
**Ubuntu 26.04**, sin extras (ni «26.04 + Docker» ni Plesk). En la
configuración avanzada, poner una **contraseña de root**: es la llave de
emergencia para la consola web.

**El Cloud Config de IONOS no se aplicó.** Se escribió uno con el usuario
`deploy`, la clave y `ssh_pwauth: false`, pero tras la instalación
`deploy` no existía (`id: 'deploy': no such user`). No hay que contar con
él: todo lo siguiente se hace a mano.

## 2. Usuario `deploy` (consola web)

**[Consola IONOS]** La consola web **no permite pegar** y usa el **teclado
inglés (EE. UU.)** aunque el del Mac sea español. Cambian de sitio, entre
otros:

| Para escribir | Pulsa (teclado español) |
|---------------|-------------------------|
| `-` | la tecla a la derecha del `0` (la del `'`) |
| `/` | la tecla del `-` (a la izquierda del Mayús derecho) |
| `:` | Mayús + `ñ` |
| `@` | Mayús + `2` |

Por eso aquí solo se teclean comandos cortos y **sin guiones**:

```sh
id deploy            # → id: 'deploy': no such user
adduser deploy       # contraseña temporal, solo letras y números; el resto, Enter
adduser deploy sudo
```

La contraseña temporal solo sirve para la primera conexión: en la sección 4
se desactiva el acceso por contraseña y en la 4.3 se bloquea.

## 3. Clave SSH personal

**[Mac]**

```sh
ssh-keygen -R <IP_DEL_VPS>      # solo si se reinstaló: la huella antigua ya no vale
ssh-copy-id -i ~/.ssh/id_ed25519_personal.pub deploy@<IP_DEL_VPS>
#   → Number of key(s) added: 1
ssh -i ~/.ssh/id_ed25519_personal deploy@<IP_DEL_VPS>
```

- En la primera conexión hay que escribir **`yes` completo**: un Enter vacío
  es «no» y termina con `Host key verification failed`.
- Sin `-i`, el Mac ofrece solo las claves por defecto (otra clave, del
  trabajo), el servidor no la reconoce y pide contraseña.

Para no repetir la IP ni la clave, en `~/.ssh/config` del Mac:

```
Host vps-gasolineras
  HostName <IP_DEL_VPS>
  User deploy
  IdentityFile ~/.ssh/id_ed25519_personal
  IdentitiesOnly yes
```

A partir de aquí, `ssh vps-gasolineras`.

## 4. Acceso solo por clave

### 4.1 `sudo` sin contraseña para `deploy`

**[VPS]**

```sh
echo 'deploy ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/deploy
sudo -n true && echo "sudo sin contraseña: ok"
```

Hace falta porque en la 4.3 se bloquea la contraseña de `deploy`.

### 4.2 `sshd`: sin contraseñas ni root

**[VPS]** Ojo con el orden de lectura. Los archivos de
`/etc/ssh/sshd_config.d/` se leen en orden alfabético y **en `sshd` gana el
primer valor leído**. La imagen de IONOS trae `50-cloud-init.conf` con
`PasswordAuthentication yes`. El 16/10 se puso la configuración en
`99-solo-claves.conf`, se leía después y **no tenía efecto**: el servidor
seguía aceptando contraseñas. Se descubrió el 17/10. Por eso el archivo se
llama **`00-`**:

```sh
sudo tee /etc/ssh/sshd_config.d/00-solo-claves.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sudo rm -f /etc/ssh/sshd_config.d/99-solo-claves.conf    # si existe, del primer intento
sudo sshd -t && echo "sintaxis: ok"                      # antes de recargar
sudo systemctl reload ssh
sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin) '
```

Esperado de `sshd -T`, en cualquier orden (son los **valores efectivos**, que
es lo que cuenta; no basta con leer los archivos):

```
permitrootlogin no
passwordauthentication no
kbdinteractiveauthentication no
```

**Antes de cerrar la sesión**, abre **otra** desde el Mac. Si algo ha ido
mal, la primera sigue abierta para arreglarlo:

**[Mac]**

```sh
ssh vps-gasolineras exit && echo "clave personal: ok"
```

### 4.3 Bloquear la contraseña de `deploy`

**[VPS]**

```sh
sudo passwd -l deploy
sudo passwd -S deploy       # la segunda columna debe ser L (bloqueada)
```

Comprobación desde el Mac con una clave que el servidor no conoce. Debe
fallar **sin pedir contraseña**:

**[Mac]**

```sh
ssh -o IdentitiesOnly=yes -i ~/.ssh/precios-backups deploy@<IP_DEL_VPS> exit
#   antes de autorizarla en la sección 10: Permission denied (publickey).
```

## 5. Sistema: actualizaciones, swap y zona horaria

### 5.1 Actualizar e instalar lo necesario

**[VPS]** (línea a línea)

```sh
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Tras volver a entrar: `Ubuntu 26.04.1 LTS (GNU/Linux 7.0.0-… x86_64)`.

### 5.2 Swap de 2 GB

Con 8 GB de RAM, 2 GB de swap bastan como red de seguridad: si algo se
dispara, el sistema va más lento en vez de colgarse (lo que pasó con el
servidor anterior).

**[VPS]**

```sh
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab     # para que sobreviva a reinicios
swapon --show
free -h
```

Esperado, también después de un `sudo reboot`: `swapon --show` muestra
`/swapfile` de `2G`, y `free -h` muestra `Swap: 2.0Gi` y unos `7.7Gi` en
`Mem` (los 8 GB de RAM).

### 5.3 Zona horaria Europe/Madrid

La imagen viene en UTC. Se pone en Madrid para que el reinicio automático
de las 05:30 (5.4) sea siempre a las 05:30 de Madrid, también tras el
cambio de hora. Al programador no le afecta: su contenedor ya usa
Europe/Madrid.

**[VPS]**

```sh
sudo timedatectl set-timezone Europe/Madrid
timedatectl
```

Esperado: `Time zone: Europe/Madrid (CEST, +0200)` (o `CET, +0100` en
invierno).

### 5.4 Actualizaciones de seguridad automáticas, con reinicio a las 05:30

**[VPS]** Comprobar que están instaladas y activas:

```sh
dpkg -l unattended-upgrades | tail -1          # empieza por "ii"
systemctl is-enabled unattended-upgrades       # enabled
systemctl is-active unattended-upgrades        # active
cat /etc/apt/apt.conf.d/20auto-upgrades
```

Esperado en `20auto-upgrades`:

```
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
```

Si no está instalado o no sale así:

```sh
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades     # responder "Yes"
```

Reinicio automático **cuando una actualización lo pida**, a las **05:30**.
No coincide con la copia de las 04:43 ni con las comprobaciones del minuto
17, y el programador ya ha demostrado que vuelve solo tras un reinicio:

```sh
sudo tee /etc/apt/apt.conf.d/52-reinicio-automatico <<'EOF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "05:30";
EOF
apt-config dump | grep -i automatic-reboot
```

Esperado: `Unattended-Upgrade::Automatic-Reboot "true";` y
`Unattended-Upgrade::Automatic-Reboot-Time "05:30";`.

Comprobación posterior (cuando ocurra un reinicio automático): después de
las 06:17, `docker compose logs scheduler` muestra la comprobación de
arranque con la recogida activada y la de las 06:17, y
`ls backups/` sigue teniendo la copia de las 04:43 de ese día.

## 6. Cortafuegos

**[VPS]** Primero se permite SSH y **después** se activa (al revés, se
cortaría la conexión):

```sh
sudo ufw allow OpenSSH
sudo ufw enable              # responder "y"
sudo ufw status
```

El 16/10 el primer `ufw enable` no se aplicó (`Status: inactive`); se
repitieron las dos órdenes respondiendo `y`. Esperado, **solo OpenSSH**:

```
Status: active
To                         Action      From
OpenSSH                    ALLOW       Anywhere
OpenSSH (v6)               ALLOW       Anywhere (v6)
```

El proyecto no expone ningún puerto (en `docker compose ps`, la columna
PORTS está vacía).

## 7. Docker y Compose (paquetes de Ubuntu)

**[VPS]** De los paquetes de Ubuntu, no del repositorio de Docker. **Línea
a línea:**

```sh
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker deploy
exit
```

**[Mac]** `ssh vps-gasolineras` y, de nuevo en el VPS:

```sh
groups                      # incluye docker
docker compose version      # → Docker Compose version 2.40.3+ds1-0ubuntu1 (o posterior)
docker ps                   # funciona sin sudo
```

Versiones del 16/10: `docker.io 29.1.3`, `docker-compose-v2 2.40.3`.

Estar en el grupo `docker` equivale a tener permisos de root. `deploy` ya
los tiene con `sudo`.

También hace falta `sqlite3` para la migración y las comprobaciones:

```sh
sudo apt install -y sqlite3
```

## 8. Repositorio con una clave de solo lectura

**[VPS]** Una clave propia del VPS, registrada en GitHub como **clave de
despliegue sin permiso de escritura**: desde el VPS se puede descargar el
código, pero no subir nada.

```sh
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "vps-gasolineras"
printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
cat ~/.ssh/github_deploy.pub
```

En GitHub: el repositorio → Settings → Deploy keys → Add deploy key, con esa
línea y **sin** marcar «Allow write access». Después:

```sh
cd ~
git clone git@github.com:Andersato/sdd-rastreador.git      # "yes" a la huella de GitHub
cd sdd-rastreador
```

## 9. Configuración del proyecto

**[VPS]**

```sh
printf 'HOST_UID=%s\nHOST_GID=%s\n' "$(id -u)" "$(id -g)" > .env
mkdir -p data backups
ls -ld data backups         # las dos a nombre de deploy
cat .env                    # HOST_UID=… y HOST_GID=… (los de `id -u` e `id -g`, p. ej. 1001)
df -h /                     # espacio libre
```

`COLLECTION_ENABLED=true` se añade justo antes del primer arranque (sección
11), cuando el histórico ya está en su sitio.

**Espacio en disco.** El disco es de 240 GB. La base ocupa unos 3 MB por
captura (25,5 MB con 8 capturas el 2026-10-16; con 4 capturas al día,
algo más de 4 GB al año). Cada copia comprimida ocupa alrededor de un tercio
de la base (7,9 MB para esos 25,5 MB). Hace falta sitio para la base, para
**un volcado temporal del mismo tamaño** mientras se hace una copia y para
**11 copias comprimidas**: en total, unas 5 veces el tamaño de la base.
`df -h /` antes del primer arranque y en cada actualización.

## 10. Clave del Mac para las copias (solo lectura con `rrsync`)

Se detalla en `docs/offsite-backups.md`. Resumen de lo que se hace en el
VPS:

**[VPS]**

```sh
command -v rrsync                                  # → /usr/bin/rrsync
cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.antes-de-rrsync
echo 'command="/usr/bin/rrsync -ro /home/deploy/sdd-rastreador/backups",restrict <CLAVE_PUBLICA_COPIAS>' >> ~/.ssh/authorized_keys
cat ~/.ssh/authorized_keys                         # dos líneas: personal y la de rrsync
```

Se añade con `echo … >>` y no con `nano`. El 17/10, con `nano`, la línea
quedó cortada (sin la clave): la clave de copias no estaba autorizada y SSH
pasó a pedir contraseña, que entonces aún funcionaba (ver 4.2).

En el Mac hace falta el **`rsync` de Homebrew** (`brew install rsync`). El
de macOS (`openrsync`) no funciona con `rrsync`: da
`invalid rsync-command syntax or options`.

## 11. Migración del histórico desde el Mac

El orden importa: **el programador del Mac se para antes de copiar**, para
que no siga capturando en otra base.

**[Mac]**

```sh
docker compose stop scheduler
docker compose ps -a scheduler                                         # → exited
sqlite3 -readonly data/prices.db "SELECT COUNT(*) FROM snapshots;"     # anota el número (el 16/10: 8)
sqlite3 data/prices.db ".backup $HOME/prices-migracion.db"             # copia segura, nunca `cp` en caliente
scp ~/prices-migracion.db vps-gasolineras:sdd-rastreador/data/prices.db
```

- `~/prices-migracion.db` se conserva en el Mac como copia adicional.
- `data/prices.db` del Mac **no se borra ni se modifica**: queda como
  histórico anterior a la migración.
- El `.env` del Mac se deja **sin `COLLECTION_ENABLED`**, para que su
  programador no vuelva a capturar aunque se lance `docker compose up -d`
  por costumbre.

**[VPS]**

```sh
cd ~/sdd-rastreador
sqlite3 -readonly data/prices.db "PRAGMA integrity_check; SELECT COUNT(*) FROM snapshots;"
ls -ln data/
```

Esperado: `ok` y **el mismo número de capturas que en el Mac** (el 16/10:
`ok` y `8`), con `prices.db` a nombre de `deploy`.

**Si el número no coincide**, no se arranca el programador del VPS. Se
aparta la copia con otro nombre, sin borrarla
(`mv data/prices.db data/prices.db.descartada-$(date +%F-%H%M)`), y se
repite desde `sqlite3 … ".backup …"` en el Mac.

## 12. Primer arranque y verificación

**[VPS]** Justo antes de arrancar, se activa la recogida en esta máquina, y
**solo** en esta:

```sh
echo 'COLLECTION_ENABLED=true' >> .env
grep COLLECTION_ENABLED .env          # → COLLECTION_ENABLED=true
df -h /
docker compose build
docker compose up -d
sleep 90; docker compose logs scheduler
```

Esperado, la línea de arranque con **`recogida activada`**:

```
… · programador en marcha: comprobación ahora y cada hora en el minuto 17; intervalo configurado: 6 (por defecto); recogida activada
time="…" level=warning msg="process reaping disabled, not pid 1"
… · no toca capturar: última captura hace … (intervalo 6 h)
```

**No se da el despliegue por bueno** hasta ver `recogida activada`. Si dice
`recogida desactivada en esta máquina`, falta `COLLECTION_ENABLED=true` en
`.env` (o está mal escrito). Se corrige y se vuelve a lanzar
`docker compose up -d`.

Después, en el siguiente minuto 17, aparece la línea de esa comprobación, y
la primera copia (si no hay ninguna, se hace en la comprobación de
arranque):

```sh
docker compose logs scheduler | grep -E 'captura|copia'
ls -ln backups/              # prices-AAAA-MM-DD.db.gz a nombre de deploy
```

El 16/10 (versión anterior, sin copias), la primera captura en el VPS fue a
las 15:17:04 (`captura guardada (última captura hace 5 h 50 min, intervalo
6 h)`), y las comprobaciones salieron exactamente en el segundo :00.

### El aviso «process reaping disabled, not pid 1»

Es **normal** y no hay que hacer nada. Lo escribe supercronic (el
programador de tareas) al arrancar porque no es el proceso 1 del contenedor.
Con `init: true` en `docker-compose.yml`, el proceso 1 es el init de
Docker (tini), que recoge los procesos huérfanos. A supercronic lo lanza y
lo vigila el programa de arranque (`container/scheduler.py`).

### Verificación tras un reinicio

**[VPS]**

```sh
sudo reboot
```

**[Mac]**, al cabo de un minuto:

```sh
ssh vps-gasolineras
cd ~/sdd-rastreador && docker compose ps && docker compose logs --tail 5 scheduler
```

Esperado:

- `docker compose ps` muestra `sdd-rastreador-scheduler-1` con
  `Up … minutes` sin haber lanzado nada.
- Los logs muestran la línea `programador en marcha … recogida activada` del
  arranque y su comprobación.
- En el siguiente minuto 17, la línea de esa comprobación.

El 16/10, tras el reinicio: `Up 3 minutes`, la comprobación de arranque a
las 19:15:25 y la de las 19:17:00.

## 13. Actualizar a una versión nueva del repo

**[VPS]**

```sh
cd ~/sdd-rastreador
docker compose run --rm backup        # 1. copia a mano (también vale con el programador parado)
df -h /
git pull                              # 2.
docker compose build                  # 3.
docker compose up -d                  # 4.
docker compose ps                     # 5. en marcha
docker compose logs --tail 5 scheduler    #    "recogida activada"
```

- Ningún paso borra `data/` ni `backups/`. **Nunca** se usa
  `docker compose down -v`, `git clean` ni `rm` sobre esas carpetas.
- **Si `docker compose build` falla**, el programador sigue en marcha con la
  imagen anterior: no se ha parado nada. Para volver a la versión de antes:
  `git log --oneline -3`, `git checkout <commit anterior>`,
  `docker compose build` y `docker compose up -d`.

### Actualizar el VPS ya desplegado a la versión con copias (`add-vps-deployment`)

El VPS del 16/10 tiene la versión anterior, sin `COLLECTION_ENABLED` ni
`./backups`. **Sin estos pasos, al actualizar dejaría de capturar.**

**[VPS]**

```sh
cd ~/sdd-rastreador
# 1. Copia previa, en solo lectura (aún no existe la copia a mano) y fuera de backups/
sqlite3 'file:data/prices.db?mode=ro' ".backup $HOME/antes-de-actualizar-$(date +%F).db"
sqlite3 -readonly "$HOME/antes-de-actualizar-$(date +%F).db" "PRAGMA integrity_check; SELECT COUNT(*) FROM snapshots;"
# 2. Código, carpeta de copias y variable
git pull
mkdir -p backups                       # puede existir ya (prueba de rrsync)
echo 'COLLECTION_ENABLED=true' >> .env
grep COLLECTION_ENABLED .env           # → COLLECTION_ENABLED=true
# 3. Construir y arrancar
docker compose build
docker compose up -d
docker compose logs --tail 5 scheduler # → "recogida activada"
# 4. Primera copia a mano y comprobación
docker compose run --rm backup
ls -ln backups/
```

- Si el paso 1 falla con un aviso de diario pendiente (una captura a
  medias), se espera a la siguiente comprobación horaria y se repite.
- Esperado en el paso 4: una línea
  `copia guardada: prices-AAAA-MM-DD.db.gz (… MB, N capturas, integridad correcta)`,
  y el archivo en `backups/` a nombre de `deploy`.

## Registro

| Fecha | Qué | Resultado |
|-------|-----|-----------|
| 2026-10-16 | Reinstalación, usuario, SSH, Docker, migración (8 capturas, `ok`), arranque | ✓ Primera captura en el VPS a las 15:17:04. |
| 2026-10-16 | Reinicio del VPS | ✓ El programador volvió solo (`Up 3 minutes`). |
| 2026-10-17 | `PasswordAuthentication` corregido con `00-solo-claves.conf` | ✓ La clave desconocida da `Permission denied (publickey)` sin pedir contraseña. `sshd -T`: `permitrootlogin no`, `passwordauthentication no`, `kbdinteractiveauthentication no`. `passwd -S deploy`: `deploy L 2026-10-16 0 99999 7 -1` (bloqueada). |
| | Swap, zona horaria, reinicio automático (sección 5) | pendiente |
| | Actualización a la versión con copias (sección 13) | pendiente |
