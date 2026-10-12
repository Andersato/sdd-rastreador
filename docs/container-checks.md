# Comprobaciones del contenedor que no se automatizan

Los tests de `tests/docker/` comprueban casi todo el comportamiento del
contenedor en el Mac. Quedan dos cosas que se comprueban a mano:

1. **Permisos en Linux.** En macOS, Docker no aplica los permisos de las
   carpetas compartidas por número de usuario, así que los escenarios del
   requisito «Escritura en ./data en un host Linux» solo se pueden ver en un
   Linux de verdad. Se usa una máquina Linux de OrbStack, que se borra al
   terminar.
2. **Conexión real por HTTPS.** Una única ejecución contra la API del
   Ministerio, para ver que desde la imagen se conecta bien (certificados).

## 1. Lista de comprobación en Linux (OrbStack)

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
