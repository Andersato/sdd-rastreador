# Comprobaciones del contenedor que no se automatizan

Los tests de `tests/docker/` comprueban casi todo el comportamiento del
contenedor en el Mac. Crean sus proyectos temporales en
`~/.cache/precios-gasolineras-tests/` (una carpeta por ejecución, que se
borra al terminar) y no en la carpeta temporal del sistema: en macOS esa está
en `/private/var/folders/…`, y Colima solo comparte con su máquina virtual la
carpeta personal (`$HOME`). Así funcionan igual con Colima, OrbStack y Linux.

Quedan tres cosas que se comprueban a mano:

1. **Permisos en Linux.** En macOS, Docker no aplica los permisos de las
   carpetas compartidas por número de usuario, así que los escenarios del
   requisito «Escritura en ./data en un host Linux» solo se pueden ver en un
   Linux de verdad. Se comprobó el 2026-10-12 en una máquina Linux de
   OrbStack (sección 1, registro histórico). Las siguientes comprobaciones en
   Linux se harán en el VPS (`add-vps-deployment`).
2. **Conexión real por HTTPS.** Una única ejecución contra la API del
   Ministerio, para ver que desde la imagen se conecta bien (certificados).
3. **Programador en el Mac** (`add-scheduled-collection`): lo que depende
   del paso real del tiempo, de reiniciar Colima o de suspender el Mac.

## 1. Lista de comprobación en Linux (OrbStack, 2026-10-12)

> **Registro histórico.** Es lo que se hizo el 2026-10-12, cuando Docker en
> el Mac lo daba OrbStack. Se deja tal cual como registro. Ahora el Mac usa
> Colima, y las siguientes comprobaciones en Linux se harán en el VPS
> (`add-vps-deployment`).

No se llama a la API real: la máquina sirve las respuestas guardadas de
`tests/fixtures/` con un servidor local.

### Preparar la máquina

En el Mac:

```sh
orb create ubuntu ingest-check
orb -m ingest-check        # abre una terminal en la máquina
```

Dentro de la máquina. OrbStack monta las carpetas del Mac en la misma ruta,
así que el proyecto se copia desde ahí (sin datos, sin `.env` y sin el entorno
de Python):

```sh
PROYECTO=/Users/<tu usuario>/…/sdd-rastreador     # ruta del proyecto en el Mac
tar -C "$PROYECTO" --exclude=./data --exclude=./.env --exclude=./.venv \
    --exclude=./.git -czf /tmp/sdd-rastreador.tgz .
chmod 644 /tmp/sdd-rastreador.tgz
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
# Usuario «deploy» con número 1001, con permiso para usar Docker
sudo groupadd --gid 1001 deploy
sudo useradd --create-home --uid 1001 --gid 1001 --shell /bin/bash deploy
sudo usermod -aG docker deploy
sudo -iu deploy
```

Ya como `deploy` (`id` debe mostrar `uid=1001(deploy) gid=1001(deploy)` y el
grupo `docker`):

```sh
mkdir sdd-rastreador && cd sdd-rastreador
tar -xzf /tmp/sdd-rastreador.tgz
printf 'HOST_UID=%s\nHOST_GID=%s\n' "$(id -u)" "$(id -g)" > .env
mkdir data
docker compose build
# Servidor local con las respuestas guardadas (en otra terminal o en segundo plano)
python3 -m http.server 8000 --bind 0.0.0.0 --directory tests/fixtures >/dev/null 2>&1 &
URL="http://$(hostname -I | awk '{print $1}'):8000/valid_two_stations.json"
# Para contar capturas
captures() { python3 -c "import sqlite3; print(sqlite3.connect('data/prices.db').execute('SELECT count(*) FROM snapshots').fetchone()[0])"; }
```

### Escenarios

Para cada uno: el comando, lo que debe pasar y cómo comprobarlo. `deploy` no
tiene `sudo`: las líneas marcadas «(otra terminal)» se ejecutan en una segunda
terminal de la máquina (`orb -m ingest-check`) con tu usuario normal, desde
`/home/deploy/sdd-rastreador`.

**A. «Usuario del host con número distinto de 1000»**

```sh
docker compose run --rm ingest --url "$URL"; echo "código: $?"
ls -ln data/
captures
```

Esperado: código 0. `data/` solo contiene `prices.db`, con dueño `1001 1001`.
Hay 1 captura.

**B. «Base existente en Linux»** (sigue después de A)

```sh
docker compose run --rm ingest --url "$URL"; echo "código: $?"
ls -ln data/
captures
```

Esperado: código 0. `data/` sigue conteniendo solo `prices.db` (ni
`-journal` ni `.tmp-…`), con dueño `1001 1001`. Hay 2 capturas.

**C. «Carpeta sin permiso de escritura»**

```sh
mv data data-ok
sudo mkdir data && sudo chmod 755 data      # (otra terminal) data/ vacía, de root
docker compose run --rm ingest --url "$URL"; echo "código: $?"
ls -la data/
```

Esperado: código distinto de 0. Mensaje
`Error: no se ha podido crear la base de datos /app/data/prices.db: …`.
`data/` sigue vacía.

```sh
sudo rmdir data                             # (otra terminal)
mv data-ok data                             # volver al estado de B
```

**D. «Base de datos a nombre de otro usuario»**

```sh
sudo chown root:root data/prices.db && sudo chmod 644 data/prices.db   # (otra terminal)
ls -ln data/; sha256sum data/prices.db
docker compose run --rm ingest --url "$URL"; echo "código: $?"
ls -ln data/; sha256sum data/prices.db
```

Esperado: código distinto de 0. Mensaje
`Error: no se ha podido guardar en la base de datos /app/data/prices.db: …`.
El listado y el hash de `prices.db` son iguales antes y después.

### Terminar

```sh
exit                      # salir de deploy
exit                      # salir de la máquina
orb delete -f ingest-check     # en el Mac: borra la máquina y todo lo que contiene
```

## 2. Ejecución real única por HTTPS

Se hace sobre una **copia** de `data/`, en una carpeta aparte, para no tocar
el histórico real con una prueba. Es una sola petición a la API. La lanza
siempre la persona responsable del proyecto, nunca un agente ni un test.

En el Mac, desde la carpeta del proyecto (con `.env` creado y la imagen
construida):

```sh
rm -rf /tmp/pg-real && mkdir -p /tmp/pg-real/data
cp docker-compose.yml .env /tmp/pg-real/
cp data/prices.db /tmp/pg-real/data/
cd /tmp/pg-real
docker compose run --rm ingest; echo "código: $?"
python3 -c "import sqlite3; print(sqlite3.connect('data/prices.db').execute('SELECT count(*) FROM snapshots').fetchone()[0])"
docker compose down
```

Esperado: código 0. El resumen muestra las estaciones procesadas (unas
12 000). La copia tiene una captura más que `data/prices.db` original.

## 3. Programador en el Mac

Se hace con el programador real ya activado (`docker compose up -d`, ver el
README), así que no añade peticiones a la API aparte de las capturas que le
tocan. Antes, comprueba que:

- Colima arranca al iniciar sesión: `brew services start colima`, y
  `brew services list` lo muestra `started`.
- Colima usa el montaje virtiofs: `colima status` muestra
  `mountType: virtiofs`. Con sshfs los bloqueos de archivos no son fiables.

Para ver el estado y las últimas líneas del log:

```sh
docker compose ps scheduler
docker compose logs --tail 20 scheduler
```

### Escenarios

1. **Comprobaciones horarias** (escenario «Comprobaciones horarias»).
   Pasadas al menos 2 horas desde `docker compose up -d`, los logs muestran
   una línea por hora, siempre en el minuto 17 (y ninguna a en punto),
   además de la de arranque.
2. **Reinicio de Docker** (escenario «Reinicio de Docker»). Reinicia Colima
   (`brew services restart colima`) o reinicia el Mac. Sin lanzar nada,
   `docker compose ps scheduler` lo muestra en marcha (`running`) y los logs
   tienen una línea nueva de `programador en marcha` seguida de su
   comprobación.
3. **Parado por el usuario** (escenario «Parado por el usuario»). Lanza
   `docker compose stop`, apunta el número de capturas
   (`sqlite3 data/prices.db "SELECT COUNT(*) FROM snapshots"`) y reinicia
   Colima (`brew services restart colima`). `docker compose ps -a scheduler`
   lo muestra parado (`exited`) y el número de capturas no cambia. Vuelve a
   activarlo con `docker compose up -d`.
4. **Vuelta de una suspensión** (escenario «Vuelta de una suspensión»).
   Suspende el Mac más de 6 horas (por ejemplo, por la noche) sin parar
   Colima. Al despertarlo, como tarde en la siguiente comprobación del
   minuto 17 los logs muestran `captura guardada`, y solo una.

### Verificación posterior al archivo (no forma parte del cambio)

Los cambios de hora se comprueban antes de archivar con tests de reloj
inyectado (`tests/functional/test_scenarios_scheduled.py`). Lo que esos
tests no ven es cuándo dispara supercronic en esos días. Se revisa en los
logs reales, sin bloquear el archivo del cambio:

- **2026-10-25** (las 02:00 vuelven a ser la 01:00): entre las 01:17 y las
  04:17 hay comprobaciones cada hora; si hay dos a las 02:17, la segunda
  dice `no toca capturar` y no hay ninguna captura de más.
- **2027-03-28** (las 02:00 pasan a ser las 03:00): hay comprobaciones a
  las 00:17, 01:17, 03:17 y 04:17, ninguna a las 02:17 y ninguna repetida.

```sh
docker compose logs scheduler | grep '2026-10-25 0[0-5]:'
docker compose logs scheduler | grep '2027-03-28 0[0-5]:'
```

Si los logs de esos días ya se han rotado, se da por no comprobado y se anota.

## Resultados

### Lista de Linux

| Fecha | Escenario | Resultado |
|-------|-----------|-----------|
| 2026-10-12 | A | ✓ Código 0. `data/` solo con `prices.db`, dueño `1001 1001`. 1 captura. |
| 2026-10-12 | B | ✓ Código 0. Solo `prices.db` (sin `-journal` ni `.tmp-…`), dueño `1001 1001`. 2 capturas. |
| 2026-10-12 | C | ✓ Código 1. `Error: no se ha podido crear la base de datos /app/data/prices.db: [Errno 13] Permission denied: …`. `data/` sigue vacía. |
| 2026-10-12 | D | ✓ Código 1. `Error: no se ha podido guardar en la base de datos /app/data/prices.db: attempt to write a readonly database`. Listado y hash iguales antes y después. |

Máquina: OrbStack, Ubuntu 26.04.1 LTS, Docker 29.1.3, Compose 2.40.3.

### Ejecución real

| Fecha | Código | Resumen |
|-------|--------|---------|
| 2026-10-12 11:37 (Madrid) | 0 (deducido, pendiente de confirmar) | `Captura guardada en /app/data/prices.db`, 11 514 estaciones (2 nuevas, 11 512 actualizadas), 43 079 precios, 0 avisos. La copia pasó de 1 a 2 capturas. |
| 2026-10-12 12:59 (Madrid) | 0 | Primera captura real con Docker sobre `data/prices.db`, lanzada por el usuario después de `fix-api-tls-ciphers`: 11 514 estaciones (2 nuevas, 11 512 actualizadas), 43 074 precios, 0 avisos. La base pasó de 1 a 2 capturas. |

Notas de la ejecución de las 11:37:
- El código de salida no se registró directamente, porque la salida pasaba
  por un filtro. Es 0 porque la ingesta solo imprime el resumen cuando termina
  bien.
- Por un error al lanzar el comando, se hizo una **segunda petición** a la API
  cinco segundos después (captura 3 en la copia, 09:38:01 UTC). Solo afectó a
  la copia, que se borró después. `data/prices.db` real no se tocó: mismo
  hash antes y después.

Notas de la ejecución de las 12:59:
- La lanzó el usuario con `docker compose run --rm ingest`, después de
  `fix-api-tls-ciphers`. El código 0 se registró directamente y fue una sola
  petición.
- Se hizo sobre `data/prices.db` real, no sobre una copia como indica la
  sección 2, por decisión del usuario: era su primera captura con Docker.
  Añadir una captura no modifica las anteriores. Después, la base tiene 2
  capturas.
- La tarea 6.3 de `add-container-setup` se da por verificada con las dos
  ejecuciones: la de las 11:37 comprobó la captura sobre una copia y la de las
  12:59 confirmó el código 0.

### Programador en el Mac

| Fecha | Escenario | Resultado |
|-------|-----------|-----------|
| 2026-10-14 20:09 – 2026-10-15 19:17 | Comprobaciones horarias | ✓ (ver nota). Arranque a las 20:09:37 con captura guardada (la última era de hace 55 h). Después, una comprobación por hora, ninguna a en punto ni repetida. Capturas a las 20:09, 02:17, 08:17 y 14:16 (la de las 14:16 dice «hace 5 h 59 min», dentro del margen), todas con 0 avisos. |
| | Reinicio de Docker | pendiente (posterior al archivo: con Colima aún no se ha hecho) |
| | Parado por el usuario | pendiente (posterior al archivo: con Colima aún no se ha hecho) |
| | Vuelta de una suspensión | pendiente (posterior al archivo: con Colima aún no se ha hecho) |

Notas de las comprobaciones horarias:
- **Minuto 16 en vez de 17.** Casi todas las líneas del log van de XX:16:49 a
  XX:17:07: la comprobación se lanza hasta 11 s antes del :17, según el reloj
  del contenedor. Vale funcionalmente, porque lo que busca la spec es evitar
  el :00. Se midió el desfase entre el reloj del Mac y el de un contenedor
  el 2026-10-15 a las 19:20: de +0,06 a +0,4 s en 5 medidas, dentro del
  margen de la propia medida. El NTP de la máquina virtual está activo
  (offset −29 ms). La hipótesis de un reloj de la máquina virtual adelantado
  no se ve en esa medida: el adelanto de hasta 11 s puede deberse a
  correcciones del reloj entre sincronizaciones. Es de segundos, no de
  minutos.
- **Suspensión entre las 18:17 y las 18:45 del 2026-10-15** (confirmada por
  el usuario). No hubo comprobación a las 18:17, y al despertar hubo una a
  las 18:45:27 («no toca», sin captura); la siguiente fue la de las 19:16
  con normalidad. Es una vuelta de suspensión corta: el escenario
  «Vuelta de una suspensión» (más de 6 h, con captura al despertar) sigue
  pendiente.
| 2026-10-25 | Cambio de hora de octubre (posterior al archivo) | pendiente |
| 2027-03-28 | Cambio de hora de marzo (posterior al archivo) | pendiente |

### Tests en Colima

Máquina: Colima 0.10.3 (`vmType: vz`, **`mountType: virtiofs`**, comprobado
con `colima status` y en `~/.colima/default/colima.yaml`), aarch64,
Docker 29.5.2.

| Fecha | Ejecución | Resultado |
|-------|-----------|-----------|
| 2026-10-14 | Suite completa, primera vez | ✗ 597 pasan y 33 fallan, todos de `tests/docker/`: `bind source path does not exist: /private/var/folders/…`. Colima solo comparte `$HOME` y los proyectos temporales estaban en la carpeta temporal del sistema. Se pasan a `~/.cache/precios-gasolineras-tests/`. |
| 2026-10-14 | `tests/docker/` y tests de las barreras | ✓ 172 pasan, incluidos `flock` entre contenedores, permisos de `./data` y parada con SIGTERM. La carpeta temporal queda vacía al terminar. |
| 2026-10-14 | Suite completa | ✗ 629 pasan y 1 falla: `test_stop_during_save_keeps_complete_captures` deja `prices.db-journal` tras parar el programador (6 de 6 al repetirlo solo). La base conserva sus 3 capturas intactas. Causa: `scheduler.py` salía sin esperar a la comprobación de arranque, que moría a mitad del ROLLBACK (corregido, ver D12). |
| 2026-10-15 | Suite completa, tras el arreglo | ✓ 630 pasan. El test de la parada pasa 6 de 6 al repetirlo solo. Dos ejecuciones anteriores ese día no sirven: una falló en `test_build_fails_with_wrong_checksum` y otra se quedó colgada en una construcción de la imagen. Las dos fueron en la primera construcción sin caché, con descargas de red; con caché, los dos tests de construcción pasan en 3 s. |
