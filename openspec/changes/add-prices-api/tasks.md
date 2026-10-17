# Tasks

## 1. Dependencias e imagen

- [x] 1.1 Crear en una carpeta temporal (fuera del repo) un entorno virtual limpio con Python 3.12 (o dentro de `python:3.12-slim-bookworm`, como la imagen), instalar `fastapi` y `uvicorn` sin extras y escribir `requirements.txt` con todo lo que muestre `pip freeze` fijado con `==` (D12); verificar que no aparece `httpx` y que `pip install --no-deps -r requirements.txt` + `pip check` en otro entorno limpio no da errores.
- [x] 1.2 Actualizar `requirements-dev.txt` (`-r requirements.txt`, `pytest`, `httpx` fijado) e instalarlo en `.venv`; verificar que `python -m pytest` sigue pasando entero (889 tests) antes de escribir código nuevo.
- [x] 1.3 Instalar `requirements.txt` en el `Dockerfile` con `--no-deps` y `pip check`, antes de copiar `src/` (D12); añadir a `tests/docker/test_image.py` los escenarios «Sin dependencias de desarrollo» (`pytest` y `httpx` no importables) y «Dependencias de la API con versión fija» (paquetes instalados = `requirements.txt` aparte de `pip`; FastAPI sin `[standard]`), y verificar que pasan. Desde este cambio, construir la imagen (también la de los tests) necesita acceso a PyPI; añadir `requirements.txt` a `BUILD_FILES` de `tests/docker/helpers.py`.
- [x] 1.4 Añadir tests Docker de «Ingesta, programador y copias sin depender de la API» con `PYTHONPROFILEIMPORTTIME=1` (heredada por `execv` y por los procesos de supercronic; D14) (ingesta contra el servidor de pruebas con `valid_two_stations.json`, una comprobación del programador con la recogida desactivada y una copia a mano de una base de pruebas) y verificar que ninguno carga `fastapi` ni `uvicorn`.

## 2. Reglas sin base de datos

- [x] 2.1 `src/api/catalog.py` con los 21 combustibles, `slug`, unidad y tipo (D5); tests unitarios de «Contenido del catálogo», «Unidades», «AdBlue» y de la regla del identificador corto sobre los 21; verificar que pasan.
- [x] 2.2 `src/api/geo.py` con las zonas y la distancia (R = 6371 km) (D6); tests de las zonas (extremos incluidos, (0, 0), Tui, Canarias, Lisboa, París, (42.0, -9.45) frente a (42.0, -9.30)) y de las distancias de la spec (0.91, 2.01, 3.4, 5.14, 4.13, 8.26 km); verificar que pasan.
- [x] 2.3 `src/api/formatting.py`: recorte de textos (espacios, tabuladores, no separables, interiores intactos, vacío → `null`), redondeos con `Decimal` (D7) y fecha de la fuente con desfase (D8); tests con los escenarios de la spec (1.404/1.405 → 1.405, 2.0141/2.0112 → 2.01, verano, invierno, 25/10/2026 con 01:31Z y 00:31Z, 28/03/2027 → `null`); verificar que pasan.
- [x] 2.4 `src/api/health.py` con umbral, estados y `configuracion_no_valida` reutilizando `parse_interval` (D9); tests de «Todo correcto», «Captura antigua», «Justo en el umbral», «Otro intervalo» (12 → 25), «Formas admitidas» (` 3 ` → 7), «Captura con fecha en el futuro» e «Intervalo imposible»; verificar que pasan.

## 3. Acceso a la base

- [x] 3.1 `src/api/errors.py` y `src/api/db.py`: conexión por petición en solo lectura, una transacción de lectura, espera de 2 s y traducción de errores (D2); tests de API/unidad para `sin_base` (sin crear el archivo), `sin_capturas` (versión 1 vacía, versión 0 y archivo de 0 bytes), `base_ilegible` («hola»), `base_no_compatible` (versión 2) y `recogida_a_medias` con `make_pending_journal`, comprobando que ni la base ni el diario cambian; verificar que pasan.
- [x] 3.2 Tests de bloqueo con un proceso auxiliar con `BEGIN EXCLUSIVE` (4 s → 503 `base_ocupada` a los 2 ± 0,5 s con `Retry-After: 5`; 0,5 s → 200) y con `BEGIN IMMEDIATE` sin guardar (→ 200 enseguida), y de «Captura guardándose» (con una captura nueva a medio guardar bajo bloqueo exclusivo, cada respuesta es 200 con la captura anterior o 503 `base_ocupada`); verificar que pasan.
- [x] 3.3 Límite de 2 s de lectura con `set_progress_handler` y comprobación entre sentencias (D3); test con plazo pequeño y consulta lenta inyectada → 503 `consulta_demasiado_larga` y, justo después, otro proceso puede tomar el bloqueo exclusivo sin esperar; verificar que pasa.
- [x] 3.4 Tests de «Primera captura con la API en marcha» y «Base restaurada desde una copia» (sustituir el archivo y la siguiente petición ve la nueva última captura), y de «Misma Fecha de la API» (se usa la de mayor `id`); verificar que pasan.
- [x] 3.5 Candado del proceso para leer de una en una (D2, «Lecturas de la base de una en una»), con espera de 2 s y 503 `api_ocupada`; tests de «Turno que no llega» (mensaje, `Retry-After: 5`, sin abrir la base) y de que la espera del candado no cuenta en el plazo de lectura; verificar que pasan. «Muchas peticiones a la vez» se prueba en 7.1.

## 4. Rutas y formato de las respuestas

- [x] 4.1 `src/api/app.py` con la aplicación (`/api/docs`, `/api/openapi.json`, sin `/docs`, descripción con la atribución), el formato común de respuestas y los manejadores de error de D4 (422 con mensajes por parámetro sin el valor recibido, 404, 405 con `Allow: GET`, 500 sin detalles); tests de «Parámetro no válido», «Ruta inexistente» (`/api/precios` y `/`), «Método no permitido», «Error inesperado», «Documentación» y «Sin documentación en la raíz»; verificar que pasan.
- [x] 4.2 `GET /api/health` con `status` en la raíz y `"status": "error"` en todos sus 503, `unexposed_fuels` (Metanol en 2 estaciones) y prioridad de la base sobre el intervalo no válido; tests de los escenarios de «Salud del servicio» e «Intervalo no válido en la salud» por HTTP; verificar que pasan.
- [x] 4.3 `GET /api/fuels` y `src/api/queries.py`; tests de «Datos de prueba» (orden por estaciones y `slug`, 17 con 0), «Captura de origen», «Captura sin fecha de la fuente» y «Combustible obligatorio por su identificador» (nombre, mayúsculas, `metanol`, ausente); verificar que pasan.
- [x] 4.4 `GET /api/stations/nearby` (D6); tests de «Búsqueda en Madrid», «Forma de la respuesta», «Radio mayor», «Mismo precio y distancias que se redondean igual», «Límite de resultados» (30 → 20, `total` 30), «Sin resultados», «Estación justo fuera de una zona» y todos los de «Límites de la búsqueda de cercanas» (incluidos `nan`, `inf`, `lat=91`, `lon=200`, `limit=2.5`); verificar que pasan.
- [x] 4.5 `GET /api/stations/{station_id}`; tests de «Estación con precios», «Estación sin precios en la última captura», «Estación inexistente», «Combustible fuera del catálogo en una estación», limpieza de textos y coordenadas (0, 0) / Tui → `null`; verificar que pasan.
- [x] 4.6 `GET /api/provinces/prices`; tests de «Media de Madrid», «Mismo nombre con espacios», «Provincia vacía», «Provincia sin ese combustible», «Estación sin coordenadas en la media por provincia», «Media con mitad» y «Empate de media» (CORUÑA (A), ZAMORA, ÁVILA); verificar que pasan.
- [x] 4.7 Tests de «Parámetros antes que la base» (sin base y radio 51 → 422; base con bloqueo exclusivo y `fuel=diesel` → 422 sin esperar) y de «Muchas consultas no cambian ./data» (100 peticiones, archivos, tamaños, fechas y contenido iguales; `journal_mode` `delete`); verificar que pasan.

## 5. Log de la API

- [x] 5.1 `src/api/access_log.py` como middleware con hora de Madrid, método, ruta, parámetros, código y duración, y coordenadas a 2 decimales (D10); tests de «Búsqueda en el log» (ni `40.416775` ni `-3.703790` en todo el log) y «Coordenadas no válidas en el log», y de que una 500 deja la traza en el log y no en la respuesta; verificar que pasan.

## 6. Arranque y servicio en Compose

- [x] 6.1 `container/api.py` (D1): rechazo de usuario 0 y grupo 0 antes de importar uvicorn/FastAPI, con los mensajes de la spec y código 2; tests unitarios como los de `test_entrypoint.py` y comprobación de que con root no se importan; verificar que pasan.
- [x] 6.2 Servicio `api` en `docker-compose.yml` (D11) y comentario de cabecera actualizado; en `make_project` sustituir `127.0.0.1:8000:8000` por un puerto libre comprobando que aparece una sola vez (D14), con un test unitario en `tests/unit/test_docker_helpers.py`; tests de `docker compose config` para «Configuración de Compose» (único puerto, `host_ip: 127.0.0.1`), «Montajes de la API» (solo `./data`, `read_only`, sin crear la carpeta) y «Rotación» (`json-file`, 10m, 3); verificar que pasan.
- [x] 6.3 Actualizar los tests Docker existentes que esperan un único contenedor tras `docker compose up -d` (`tests/docker/test_scheduler.py`, la activación con dos contenedores de `scheduled-collection`) y `test_compose_build_single_image_for_both_services` (programador, API e ingesta con la misma imagen); listar en la tarea los tests cambiados y verificar que pasan. Cambiados: `test_backup.py::test_activation_creates_neither_ingest_nor_backup`, `test_backup_scheduler.py::test_failed_daily_copy_does_not_stop_the_scheduler`, `test_collection_enabled.py::test_without_variable_mac_by_habit` y `::test_invalid_value_keeps_running`, `test_scheduler.py::test_activation_only_scheduler_with_host_user_and_startup_capture` (también comprueba el usuario de la API), `::test_root_keeps_running_without_requests` (la API no queda en marcha con root), `::test_invalid_interval_keeps_running_without_requests` y `::test_compose_build_single_image_for_both_services`; además, el compose falso de `tests/unit/test_docker_helpers.py::test_make_project_never_touches_repo_env` lleva la línea del puerto.
- [x] 6.4 Tests Docker del servicio: «Arranque en el VPS» (programador y API con el usuario de `.env`, `/api/health` en `127.0.0.1` con el puerto libre que asigna `make_project`, nunca el 8000 real), «Arranque en el Mac sin recogida», «Parada» (< 10 s, `./data` igual), «Usuario root» y «Grupo root» (mensaje en el log, puerto sin responder), «Escritura imposible» y «Entre dos contenedores (Docker)» con un bloqueo exclusivo de 4 s; verificar que pasan. Si el bloqueo entre contenedores no funciona en Colima, parar y consultar (D2, riesgos).

## 7. Integración con la ingesta

- [x] 7.1 Tests funcionales de «Recogida mientras se consulta» y «Muchas peticiones a la vez»: uvicorn real en un puerto local libre, 4 clientes pidiendo cercanas durante 30 s (y 8 clientes con radio 50 km sobre 2.000 estaciones) y una ingesta contra `tests/http_server.py` en medio; verificar que la captura se guarda (en menos de 1 s con 8 clientes) y que las respuestas posteriores salen de ella.

## 8. Documentación

- [x] 8.1 Sección de la API en el README (arranque en Mac y VPS, `http://127.0.0.1:8000/api/docs`, necesidad de `./data` y `./backups`, túnel con `<IP_DEL_VPS>`, estados y umbral de la salud, que solo lee la base, puerto 8000 ocupado); test en `tests/functional/test_scenarios_readme.py` de «Lectura del README»; verificar que pasa.
- [x] 8.2 Runbook `docs/vps-deployment.md`: actualización a la versión con la API (comprobaciones con `ps`, `curl`, `ss -tlnp` y `ufw status`), salud justo después de arrancar, túnel desde el Mac, puerto expuesto por error y vuelta atrás con `--remove-orphans`, sin la IP real; tests en `tests/functional/test_docs_vps.py` de los escenarios de «API en el VPS solo por túnel SSH»; verificar que pasan.

## 9. Mediciones y verificaciones manuales

- [x] 9.1 Escribir `tools/perf/make_year_db.py` y `tools/perf/measure.py` (D13) con tests unitarios de que `make_year_db.py` rechaza un destino existente, un destino o una copia bajo `./data`, y no modifica la copia de origen; verificar que pasan.
- [ ] 9.2 Dar al usuario los comandos exactos para: descomprimir `~/Backups/precios-gasolineras/prices-2026-10-17.db.gz` en una carpeta temporal nueva, comprobar «Datos reales (verificación manual)» de `/api/fuels` contra una consulta directa a esa copia, generar la base de un año (aviso de 4–5 GB), medir y borrarla; con los resultados que pase, apuntarlos en «Mediciones» de design.md y comprobar que todas las rutas quedan por debajo de 1 s.
- [ ] 9.3 Dar al usuario los comandos del runbook para actualizar el VPS, las comprobaciones de puerto y `ufw`, el acceso desde fuera sin túnel, el túnel, `/api/docs` en el navegador y la medición con la duración del log; apuntar en design.md los resultados que pase. Ningún agente se conecta al VPS.
- [ ] 9.4 Con el usuario, tras el siguiente `sudo reboot` del VPS (o el reinicio automático), comprobar «Reinicio del VPS» de la API; si no ocurre antes de archivar, dejarlo en «Workflow follow-up».

## 10. Verificación final

- [ ] 10.1 Ejecutar `python -m pytest` completo (incluidos los tests Docker) y `openspec validate add-prices-api --strict`; verificar que todo pasa y que `git status` no muestra nada en `data/` ni `backups/`.

## Workflow follow-up

- Agente test-writer sobre las specs del cambio y agente code-reviewer.
- `/opsx:archive` cuando el code-reviewer dé «Listo para archivar»; al archivar, actualizar el Purpose de `openspec/specs/ingestion-container/spec.md` para que incluya la API.
- `/publish-doc`: página de funcionalidad nueva para `prices-api`, actualizaciones de las de contenedor, recogida automática y servidor, Decisiones, Changelog, Visión del proyecto y Glosario (API, túnel SSH, 503).
- Pendiente del cambio anterior: revisar la copia de las 04:43 y su descarga, y los días de cambio de hora.
