# Proposal

## Why

Hoy cada captura hay que lanzarla a mano (`docker compose run --rm ingest`),
así que el histórico solo crece cuando alguien se acuerda. Para que tenga
valor necesita capturas regulares, también cuando el ordenador se ha
reiniciado o ha estado suspendido. Es el paso previo a llevar lo mismo al
VPS (`add-vps-deployment`).

## What Changes

- Nuevo servicio programador en `docker-compose.yml` que se arranca una vez
  con `docker compose up -d`, se queda vivo (`restart: unless-stopped`) y
  vuelve solo tras reiniciar el ordenador o Docker. `docker compose up -d`
  arranca solo el programador: no lanza el servicio `ingest`, que sigue
  funcionando igual que hoy con `docker compose run --rm ingest`.
- Dentro del programador, una comprobación cada hora, en un minuto fijo
  distinto de :00 (propuesta: :17), y otra nada más arrancar el servicio. Si
  la última captura guardada tiene 6 horas o más (con un margen de 15
  minutos), o no hay ninguna, se lanza la ingesta; si no, no se hace nada y no se llama a la API. El intervalo se
  configura en `.env` (horas enteras, 6 por defecto).
- La programación usa supercronic, nueva herramienta dentro de la imagen
  (aprobada por el usuario): versión fija y suma de comprobación verificada
  al construir, para Mac (arm64) y para el VPS (amd64).
- Bloqueo: nunca dos ingestas a la vez, tampoco entre el programador y una
  ejecución manual. La segunda termina enseguida sin llamar a la API y lo
  explica. El bloqueo vive en la propia ingesta, así protege también las
  ejecuciones con `.venv`.
- Protección ante respuestas sospechosamente cortas (pendiente desde
  `add-price-ingestion`): si la respuesta trae menos del 80 % de las
  estaciones de la última captura guardada, no se guarda nada y se avisa.
- Zona horaria Europe/Madrid para la programación y los mensajes del
  programador. Los instantes guardados en la base siguen en UTC.
- Logs del programador visibles con `docker compose logs`: una línea por
  comprobación con el resultado (captura guardada con su resumen, o el motivo
  por el que no se ha capturado). Con rotación para que no crezcan sin límite.
- README: cómo activarlo, ver los logs, cambiar el intervalo, pararlo y
  quitarlo; que OrbStack debe tener activado "Start at login"; cómo aceptar
  una respuesta corta; y que no se lance la ingesta con `.venv` mientras el
  programador está activo.

### Decisiones tomadas (revisión del 2026-10-12)

1. **Captura completa**: toda captura guardada es completa (la ingesta
   guarda todo o nada); "última captura" es la última guardada. Las
   rechazadas por respuesta corta no se guardan.
2. **Margen de 15 minutos**: toca capturar si faltan 15 minutos o menos para
   cumplir el intervalo; así una captura de las 10:17:40 no retrasa la
   siguiente hasta las 17:17.
3. **80 %**: se comparan las estaciones con al menos un precio válido de la
   respuesta con las estaciones con algún precio de la última captura, sin
   cambiar la estructura de la base. Si la última captura no tiene ninguna
   estación con precio, no se compara. Porcentaje con un decimal, truncado.
4. **`--accept-short-response`**: opción manual para guardar a sabiendas una
   respuesta corta; su aviso cuenta en el resumen. El programador nunca la
   usa, y su línea de log al rechazar incluye el comando exacto
   `docker compose run --rm ingest --accept-short-response`.
5. **Fallos**: cada ingesta es un proceso aparte; su fallo solo se registra
   en el log y el programador nunca termina ni se reinicia por ello. La
   captura pendiente se reintenta en cada comprobación horaria (como mucho
   una petición por hora), también tras una respuesta corta rechazada.
6. **Configuración no válida** (usuario o grupo 0, intervalo no válido): el
   programador sigue en marcha sin pedir nada y repite el motivo en el log
   en cada comprobación, para no reiniciarse en bucle.
7. **Bloqueo**: la decisión "¿toca?" y la ingesta van bajo el mismo bloqueo.
   Cubre procesos del mismo sistema (contenedores que comparten `./data`, o
   dos procesos en el Mac), no la combinación `.venv` + contenedor: el README
   avisa de no usar `.venv` con el programador activo. Mecanismo indicado
   por el usuario: `flock` sobre la carpeta de datos (no crea archivos ni
   interfiere con los bloqueos de SQLite, y en la primera ejecución
   `prices.db` aún no existe). Cualquier alternativa se justifica en
   design.md.
8. **Parada**: `docker compose stop` interrumpe una ingesta en curso sin
   esperarla; los datos ya están protegidos (todo o nada).
9. **Intervalo**: variable `CAPTURE_INTERVAL_HOURS` en `.env`, horas enteras
   de 1 a 24; vacía o ausente vale 6; se aplica al volver a lanzar
   `docker compose up -d`.
10. **Pruebas**: el programador admite otra URL de la API, solo para probarlo
    contra un servidor local. Reinicio de OrbStack/ordenador y suspensión se
    verifican a mano.
11. **Valores concretos**: minuto 17; logs de como mucho 3 × 10 MB.
12. **Un solo cambio**: el bloqueo y el filtro del 80 % van en este cambio,
    porque el programador depende de los dos.

### Fuera de alcance

- Despliegue en el VPS y copias de seguridad: `add-vps-deployment`.
- Guardar solo los precios que cambian.
- Alertas o notificaciones (correo, móvil…) cuando falla una captura: solo
  queda en los logs.
- Arranque automático de OrbStack/Docker al iniciar sesión: es un ajuste de
  la máquina que se documenta en el README, no se automatiza.
- Más de una ingesta por comprobación o reintentos dentro de la misma
  comprobación.

## Capabilities

### New Capabilities
- `scheduled-collection`: recogida automática y periódica de capturas con el
  servicio programador: cuándo comprueba, cuándo decide capturar, intervalo
  configurable, arranque y parada, zona horaria y logs.

### Modified Capabilities
- `price-ingestion`: se añaden la protección ante respuestas con menos del
  80 % de estaciones (y la opción manual para aceptarlas) y el bloqueo que
  impide dos ingestas a la vez sobre la misma base.
- `ingestion-container`: la imagen incluye el programador con versión fija y
  verificada para arm64 y amd64, y los datos de zona horaria de Madrid. (Que
  `docker compose up` no lance `ingest` se especifica en
  `scheduled-collection`.)

## Impact

- `docker-compose.yml`: servicio programador nuevo; `ingest` deja de
  arrancar con `docker compose up`; rotación de logs.
- `Dockerfile`: descarga verificada de supercronic (los datos de zona
  horaria ya vienen en la imagen base; se comprueba).
- `src/ingestion/`: bloqueo, comparación con la última captura y nueva
  opción manual; comprobación de "¿toca capturar?" sin llamar a la API ni
  modificar `./data`.
- Tests existentes que preparan una captura previa y luego ingieren
  respuestas pequeñas: hay que revisarlos para que no choquen con el filtro
  del 80 %.
- `.env`: nueva variable opcional `CAPTURE_INTERVAL_HOURS`.
- README: sección del programador.
- Tests nuevos con respuestas guardadas en `tests/fixtures/` (incluida una
  respuesta corta); tests de Docker que se saltan si no está disponible.
- Dependencias: supercronic en la imagen (aprobada). Ninguna nueva de Python.
- Base de datos: sin cambios de estructura; los datos históricos no se
  tocan.
- API del Ministerio: en funcionamiento normal, una petición cada 6 horas
  (o cada 5 h 45 min como mínimo, por el margen); mientras falle o se
  rechace, como mucho una por hora.
