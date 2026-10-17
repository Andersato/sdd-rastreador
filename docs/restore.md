# Restaurar una copia de seguridad

Cómo volver a tener una base de datos de precios a partir de una copia
`prices-AAAA-MM-DD.db.gz` (ver «Copias de seguridad» en el README y
`docs/offsite-backups.md`).

**Regla de oro: nunca se sobrescribe un `prices.db` que ya existe.** En el
Mac la copia se restaura siempre en una carpeta nueva. En un VPS, el
`prices.db` que haya se aparta con otro nombre, nunca se borra.

## 1. En el Mac (para comprobar una copia o consultarla)

Con la copia más reciente de la carpeta del Mac
(`~/Backups/precios-gasolineras/`, la que trae `src.backup.pull`):

```sh
COPIA=$(ls ~/Backups/precios-gasolineras/prices-*.db.gz | sort | tail -1)
echo "$COPIA"
DESTINO=~/restauracion-$(date +%F-%H%M)          # carpeta nueva
mkdir "$DESTINO"                                 # falla si ya existe: no se pisa nada
gunzip -c "$COPIA" > "$DESTINO/prices.db"
sqlite3 -readonly "$DESTINO/prices.db" "PRAGMA integrity_check;"
sqlite3 -readonly "$DESTINO/prices.db" "SELECT COUNT(*) FROM snapshots;"
```

Esperado:

- `PRAGMA integrity_check` responde `ok`.
- El número de capturas es **el mismo que dice la línea del log del VPS de
  esa copia** (`copia guardada: prices-AAAA-MM-DD.db.gz (…, N capturas, …)`).
  Para verla:
  `docker compose logs scheduler | grep 'copia guardada: prices-AAAA-MM-DD'`
  en el VPS, o la salida de `docker compose run --rm backup` si se hizo a
  mano.
- `data/prices.db` del proyecto en el Mac no se ha tocado (el procedimiento
  no lo usa en ningún paso).

Para usar la base restaurada sin tocar nada más, se abre en solo lectura
(`sqlite3 -readonly …`). Cuando ya no haga falta, se puede borrar la carpeta
`$DESTINO`, que es solo una copia.

## 2. En un VPS (nuevo o tras perder la base)

Se lanza en el VPS, como `deploy`, desde `~/sdd-rastreador`, con el proyecto
ya instalado según `docs/vps-deployment.md`. La copia se sube antes desde el
Mac (por ejemplo,
`scp ~/Backups/precios-gasolineras/prices-AAAA-MM-DD.db.gz deploy@<IP_DEL_VPS>:~/`;
`scp` usa la clave personal, no la dedicada a las copias, que solo puede
leer).

```sh
cd ~/sdd-rastreador
docker compose stop                                   # 1. parar el programador
docker compose ps                                     #    no debe quedar nada en marcha
ls -l data/                                           # 2. ¿hay ya un prices.db?
[ -e data/prices.db ] && mv data/prices.db "data/prices.db.apartada-$(date +%F-%H%M)"
gunzip -c ~/prices-AAAA-MM-DD.db.gz > data/prices.db  # 3. restaurar
sqlite3 -readonly data/prices.db "PRAGMA integrity_check;"         # 4. comprobar
sqlite3 -readonly data/prices.db "SELECT COUNT(*) FROM snapshots;"
ls -ln data/                                          #    a nombre de deploy
docker compose up -d                                  # 5. solo si todo está bien
docker compose logs --tail 20 scheduler               #    "recogida activada"
```

- El paso 2 **aparta** el `prices.db` que hubiera (con la fecha en el
  nombre), no lo borra: si la restauración sale mal, se vuelve atrás
  deshaciendo el `mv`.
- El paso 4 debe dar `ok` y el número de capturas de la línea del log de esa
  copia. **Si no, no se arranca el programador**: se borra el `prices.db`
  recién restaurado, se vuelve a poner el apartado y se prueba con otra
  copia.
- Este procedimiento en un VPS está documentado pero no se ha probado (solo
  se prueba la restauración en el Mac).

## Prueba de la restauración en el Mac

| Fecha | Copia usada | Capturas (log del VPS) | Capturas restauradas | `integrity_check` | `data/prices.db` del Mac |
|-------|-------------|------------------------|----------------------|-------------------|--------------------------|
| pendiente | | | | | |
