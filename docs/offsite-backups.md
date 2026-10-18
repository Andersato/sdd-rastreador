# Copia de seguridad fuera del VPS (en el Mac)

Las copias diarias se hacen en el VPS (`backups/`, ver «Copias de seguridad»
en el README). Para no depender de un solo disco, el Mac se las descarga una
vez al día y las verifica.

Es **el Mac quien se conecta al VPS** («modelo pull»): el VPS no tiene acceso
al Mac, así que nada de lo que pase en el VPS puede borrar las copias del
Mac. Y la clave que usa el Mac **solo puede leer `backups/`**: no abre
terminal, no escribe, no borra y no ve nada más del VPS.

## Qué hace falta en el Mac

- El proyecto con su `.venv` (ver el README, «Preparar el entorno»).
- **El `rsync` de Homebrew** (dependencia del Mac, solo para este script):

  ```sh
  brew install rsync
  /opt/homebrew/bin/rsync --version | head -1     # rsync  version 3.x
  ```

  El `rsync` que trae macOS (`/usr/bin/rsync`, que en realidad es
  `openrsync`) **no sirve**: el `rrsync` del VPS rechaza lo que manda
  («invalid rsync-command syntax or options»). El script usa siempre el de
  Homebrew (`/opt/homebrew/bin/rsync`, o `/usr/local/bin/rsync` en un Mac
  Intel), nunca el del sistema, y si no lo encuentra termina con un mensaje
  que dice cómo instalarlo.

## 1. Clave SSH dedicada a las copias

Una clave **solo para esto**, distinta de tu clave personal y **sin
contraseña** (la usa `launchd` sin que nadie esté delante).

En el Mac:

```sh
ssh-keygen -t ed25519 -N "" -C "precios-backups (Mac, solo lectura)" -f ~/.ssh/precios-backups
cat ~/.ssh/precios-backups.pub          # la línea que hay que llevar al VPS
```

## 2. Restringirla en el VPS con `rrsync`

En el VPS, como `deploy`, con tu clave personal. **No uses `ssh-copy-id`**:
añadiría la clave sin restricción. Se añade a mano una línea al final de
`~/.ssh/authorized_keys`:

```sh
command -v rrsync                                # normalmente /usr/bin/rrsync
mkdir -p ~/sdd-rastreador/backups
cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.antes-de-rrsync
nano ~/.ssh/authorized_keys                      # añadir la línea de abajo, al final
```

La línea (con la clave entera que imprimió `cat` en el Mac en lugar de
`ssh-ed25519 AAAA…`):

```
command="/usr/bin/rrsync -ro /home/deploy/sdd-rastreador/backups",restrict ssh-ed25519 AAAA… precios-backups (Mac, solo lectura)
```

- `rrsync -ro …/backups`: con esta clave solo se puede **leer** con `rsync`,
  y solo dentro de `backups/`.
- `restrict`: sin terminal, sin reenvíos de puertos ni de agente.

## 3. Primera conexión (a mano)

Para aceptar la huella del VPS (`known_hosts`); después el script no puede
preguntar:

```sh
ssh -i ~/.ssh/precios-backups -o IdentitiesOnly=yes deploy@<IP_DEL_VPS>
```

Se acepta la huella y la conexión se corta enseguida con
`rrsync error: Not invoked via sshd`: es lo esperado (no abre terminal).

## 4. Descargar las copias

Desde la carpeta del proyecto en el Mac:

```sh
.venv/bin/python -m src.backup.pull --host deploy@<IP_DEL_VPS>
```

Opciones: `--dest` (carpeta del Mac; por defecto
`~/Backups/precios-gasolineras/`), `--key` (por defecto
`~/.ssh/precios-backups`) y `--rsync` (si el de Homebrew está en otro sitio).
Nunca prueba otras claves ni pide contraseña.

Qué hace:

1. Lista las copias del VPS (solo los archivos `prices-AAAA-MM-DD.db.gz`; ni
   archivos ajenos ni los temporales de una copia en curso). Si no puede
   conectar, termina con error **sin tocar nada del Mac**.
2. Descarga las nuevas o cambiadas en la subcarpeta `descargando/`, las
   verifica (se descomprimen, `PRAGMA integrity_check` da `ok`, tienen
   capturas) y solo entonces las pasa a la carpeta principal. Una copia del
   mismo día que ha cambiado en el VPS sustituye a la del Mac solo si la
   nueva está bien.
3. Las que fallan van a `rechazadas/` (no cuentan para nada) y el script
   termina con error. En la siguiente ejecución se vuelven a intentar.
4. Si no ha fallado ninguna, aplica en el Mac la misma rotación que el VPS
   (7 diarias y 4 semanales), decidida solo con lo que hay en el Mac. Lo que
   el VPS haya borrado sigue en el Mac hasta que lo borre la rotación del Mac.

Al terminar muestra un resumen: copias nuevas, la más reciente y su número
de capturas. Código de salida 0 si todo ha ido bien y 1 si algo ha fallado.

## 5. Programarlo con `launchd` (una vez al día)

Archivo `~/Library/LaunchAgents/es.preciosgasolineras.pull-backups.plist`
(cambia `<RUTA_DEL_PROYECTO>`, `<IP_DEL_VPS>` y `<TU_USUARIO>`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>es.preciosgasolineras.pull-backups</string>
  <key>WorkingDirectory</key>
  <string><RUTA_DEL_PROYECTO></string>
  <key>ProgramArguments</key>
  <array>
    <string><RUTA_DEL_PROYECTO>/.venv/bin/python</string>
    <string>-m</string>
    <string>src.backup.pull</string>
    <string>--host</string>
    <string>deploy@<IP_DEL_VPS></string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>10</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/<TU_USUARIO>/Library/Logs/precios-gasolineras-backups.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/<TU_USUARIO>/Library/Logs/precios-gasolineras-backups.log</string>
</dict>
</plist>
```

- **`StartCalendarInterval` a las 10:00**: todos los días, bastante después
  de la copia de las 04:43 del VPS. **Si el Mac está dormido** a esa hora,
  `launchd` lo lanza al despertar.
- **`RunAtLoad`**: también se lanza al cargarlo y **al iniciar sesión**. Así,
  **si el Mac estaba apagado** a las 10:00, se descarga al encenderlo. Si
  ese día se ejecuta dos veces, la segunda no descarga nada («copias nuevas:
  0»).

**Al pegar el archivo en la terminal** (por ejemplo, con `cat > … <<'EOF'`):
en zsh con oh-my-zsh, la función que protege los caracteres que siguen a una
URL puede añadir una contrabarra en la línea del `DOCTYPE`
(`…PropertyList-1.0.dtd"\>`). Antes de cargarlo, comprueba el archivo:

```sh
plutil -lint ~/Library/LaunchAgents/es.preciosgasolineras.pull-backups.plist   # → OK
grep -c '\\' ~/Library/LaunchAgents/es.preciosgasolineras.pull-backups.plist   # → 0 (ninguna contrabarra)
```

`plutil -lint` puede dar OK aunque esté la contrabarra, así que hace falta
también el `grep`. Si da más de 0, quítala con un editor (o
`sed -i '' 's/"\\>/">/' …plist`) y vuelve a comprobarlo.

Comandos:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/es.preciosgasolineras.pull-backups.plist   # cargarlo
launchctl print gui/$(id -u)/es.preciosgasolineras.pull-backups                                   # comprobarlo
tail -n 20 ~/Library/Logs/precios-gasolineras-backups.log                                         # ver su salida
launchctl bootout gui/$(id -u)/es.preciosgasolineras.pull-backups                                 # quitarlo
```

`launchctl print` muestra, entre otras cosas, `last exit code` (0 si la
última ejecución fue bien).

## 6. Comprobar que la clave solo puede leer `backups/`

Comandos escritos enteros a propósito. En zsh (la shell por defecto de
macOS), un comando guardado en una variable (`K="ssh …"` y luego `$K`) **no
se separa en palabras** y falla; habría que usar `${=K}`.

**[VPS]** antes y después (con tu clave personal, `ssh vps-gasolineras`); la
salida debe ser idéntica:

```sh
ls -la ~/sdd-rastreador/backups
sha256sum ~/sdd-rastreador/backups/* ~/sdd-rastreador/data/prices.db
```

**[Mac]**, con la clave dedicada:

```sh
ssh -i ~/.ssh/precios-backups -o IdentitiesOnly=yes -o BatchMode=yes deploy@<IP_DEL_VPS>; echo "código: $?"
ssh -i ~/.ssh/precios-backups -o IdentitiesOnly=yes -o BatchMode=yes deploy@<IP_DEL_VPS> ls; echo "código: $?"
echo prueba > /tmp/subida.txt
/opt/homebrew/bin/rsync -t -e "ssh -i $HOME/.ssh/precios-backups -o IdentitiesOnly=yes -o BatchMode=yes" /tmp/subida.txt deploy@<IP_DEL_VPS>:./; echo "código: $?"
mkdir -p /tmp/vacio
/opt/homebrew/bin/rsync -r --delete -e "ssh -i $HOME/.ssh/precios-backups -o IdentitiesOnly=yes -o BatchMode=yes" /tmp/vacio/ deploy@<IP_DEL_VPS>:./; echo "código: $?"
/opt/homebrew/bin/rsync -t -e "ssh -i $HOME/.ssh/precios-backups -o IdentitiesOnly=yes -o BatchMode=yes" deploy@<IP_DEL_VPS>:../data/prices.db /tmp/; echo "código: $?"
ls -l /tmp/prices.db
rm -rf /tmp/subida.txt /tmp/vacio
```

Esperado: ninguna de las cinco funciona (ver la tabla de resultados) y
`/tmp/prices.db` no existe.

## Resultados

### Prueba de `rsync` con `rrsync` (tarea 3.1, 2026-10-16)

| Prueba | Resultado |
|--------|-----------|
| Terminal con la clave dedicada | ✓ No la abre: `rrsync error: Not invoked via sshd`. |
| `rsync` de macOS (`openrsync`) | ✗ `rrsync` lo rechaza: `invalid rsync-command syntax or options` (y en el Mac, `error: unexpected end of file`). |
| `rsync` de Homebrew (`rsync  version 3.5.1  protocol version 33`): listado | ✓ Lista `.` y `prueba-rrsync.txt` (17 bytes). |
| `rsync` de Homebrew: descarga de `prueba-rrsync.txt` | `rrsync` acepta el comando y lo resuelve dentro de `backups/` (`/home/deploy/sdd-rastreador/backups/prueba-rrsync.txt`), pero el archivo ya se había borrado al limpiar: `link_stat … No such file or directory`, código 23. La descarga se confirma con la primera descarga real de `src.backup.pull` (tarea 3.4). |

Decisión: se usa el `rsync` de Homebrew, solo en el Mac y solo para este
script (aprobado el 2026-10-16).

### Verificaciones manuales del acceso restringido (tarea 3.4)

| Fecha | Prueba | Resultado |
|-------|--------|-----------|
| 2026-10-17 | Descarga con la clave dedicada (`src.backup.pull`) | ✓ Código 0: `copias nuevas: 1 (prices-2026-10-17.db.gz)`, `la más reciente del VPS: prices-2026-10-17.db.gz (12 capturas, verificada ahora)`. La segunda ejecución: `copias nuevas: 0`, `(ya estaba en el Mac)`, código 0. `rrsync -ro` acepta `--dry-run --itemize-changes` y los filtros. |
| 2026-10-17 | `ssh` sin comando con la clave dedicada | ✓ No abre terminal: `PTY allocation request failed on channel 0`, `/usr/bin/rrsync error: Not invoked via sshd`, código 1. |
| 2026-10-17 | `ssh … ls` con la clave dedicada | ✓ No ejecuta `ls`: `/usr/bin/rrsync error: SSH_ORIGINAL_COMMAND does not run rsync`, código 1. |
| 2026-10-17 | Subir un archivo a `backups/` | ✓ Rechazado: `/usr/bin/rrsync error: sending to read-only server is not allowed`, código 12. |
| 2026-10-17 | Borrar con `rsync -r --delete` | ✓ Rechazado: `sending to read-only server is not allowed`, código 12. |
| 2026-10-17 | Descargar `../data/prices.db` | ✓ Rechazado: `/usr/bin/rrsync error: do not use .. in arg (anchor the path at the root of your restricted dir)`, código 12; `/tmp/prices.db` no existe. |
| 2026-10-17 | `ls -la` y `sha256sum` de `backups/` y `data/prices.db` en el VPS, antes y después | ✓ Idénticos. |

### Ejecución programada (tarea 3.5)

| Fecha | Resultado |
|-------|-----------|
| 2026-10-17 10:30 | ✓ Carga (`RunAtLoad`): `plutil -lint` OK, `launchctl bootstrap` código 0; `launchctl print`: `runs = 1`, `last exit code = 0`. Log: `copias nuevas: 0`, `la más reciente del VPS: prices-2026-10-17.db.gz (ya estaba en el Mac)`. |
| 2026-10-17 | ✓ Al pegar el `.plist` en zsh con oh-my-zsh se coló la contrabarra en el `DOCTYPE` (`grep -c '\\'` → 1, aunque `plutil -lint` daba OK). Quitada con `sed`: `grep` → 0, `plutil -lint` OK, recargado con `launchctl bootout` y `bootstrap` (código 0). |
| 2026-10-18 10:00 | ✓ Verificación posterior al archivo: launchd ejecutó la descarga por `StartCalendarInterval`. Log: `copias nuevas: 2 (prices-2026-10-17.db.gz, prices-2026-10-18.db.gz)` y `la más reciente del VPS: prices-2026-10-18.db.gz (15 capturas, verificada ahora)`. En `~/Backups/precios-gasolineras/`: `prices-2026-10-17.db.gz` (12.415.389 bytes) y `prices-2026-10-18.db.gz` (14.217.081 bytes, la copia de las 04:43 del VPS). |
| 2026-10-18 10:00 | ✓ Se esperaba `copias nuevas: 1`; fueron 2 porque la del 17 había cambiado en el VPS: a las 18:14 la sustituyó la copia manual del runbook (antes del `git pull` de la API) y pasó de 11.513.414 a 12.415.389 bytes. El Mac la verificó y sustituyó la anterior, como pide la decisión 6. |
| 2026-10-25 | pendiente: cambio al horario de invierno. |
| 2027-03-28 | pendiente: cambio al horario de verano. |
