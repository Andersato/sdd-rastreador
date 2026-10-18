# Spec Delta

## MODIFIED Requirements

### Requirement: Formato común de las respuestas correctas
Toda respuesta correcta de las rutas de datos SHALL ser JSON con
`attribution` (texto exacto «Ministerio de Industria, Comercio y Turismo -
Precios de carburantes en estaciones de servicio»), `capture` (`downloaded_at`
en UTC y `source_date` en hora de Madrid con su desfase, o `null`) y `data`.
La documentación y la página web con sus archivos (`map-view`) son las únicas
excepciones.

#### Scenario: Captura de origen
- **WHEN** la última captura se descargó el 2026-10-16T07:26:37Z con fecha de la fuente 2026-10-16T09:26:34 (Madrid) y se pide `GET /api/fuels`
- **THEN** la respuesta incluye `"capture": {"downloaded_at": "2026-10-16T07:26:37Z", "source_date": "2026-10-16T09:26:34+02:00"}` y la atribución exacta

#### Scenario: Captura sin fecha de la fuente
- **WHEN** la última captura se descargó el 2026-11-02T05:17:03Z sin fecha de la fuente
- **THEN** la respuesta incluye `"source_date": null`

#### Scenario: Fecha de la fuente en horario de invierno
- **WHEN** la fecha de la fuente guardada es 2026-11-02T06:16:58
- **THEN** la respuesta la da como `2026-11-02T06:16:58+01:00`

#### Scenario: La página no es JSON
- **WHEN** se pide `GET /`
- **THEN** la respuesta es la página HTML, sin `attribution`, `capture` ni `data` en JSON

### Requirement: Formato común de los errores
Toda respuesta de error SHALL ser JSON con `attribution` y `error`, con un
`code` estable y un `message` en español. Parámetros no válidos: 422 con un
mensaje que nombra el parámetro; rutas inexistentes: 404; otro método que no
sea GET: 405 (la página web y sus archivos admiten también HEAD); error
inesperado: 500 sin detalles internos (rutas, SQL o trazas).

#### Scenario: Parámetro no válido
- **WHEN** se pide `GET /api/stations/nearby?lat=40,4168&lon=-3.7038&fuel=gasoleo-a`
- **THEN** la respuesta es 422 con el código `parametro_no_valido` y un mensaje que nombra `lat` y dice que se espera un número con punto decimal

#### Scenario: Ruta inexistente
- **WHEN** se pide `GET /api/precios` o `GET /precios`
- **THEN** la respuesta es 404 con el código `no_encontrado` y la atribución

#### Scenario: Método no permitido
- **WHEN** se pide `POST /api/fuels` o `DELETE /api/stations/4375`
- **THEN** la respuesta es 405 con el código `metodo_no_permitido`, la cabecera `Allow: GET` y la atribución, y la base no cambia

#### Scenario: HEAD en la API
- **WHEN** se pide `HEAD /api/fuels`
- **THEN** la respuesta es 405 con el código `metodo_no_permitido` y la cabecera `Allow: GET`

#### Scenario: Error inesperado
- **WHEN** una consulta falla por un error no previsto
- **THEN** la respuesta es 500 con el código `error_interno` y el mensaje «error interno de la API; revisa el log del servicio», sin rutas, SQL ni trazas, y el detalle queda en el log de la API

### Requirement: Documentación interactiva
La API SHALL servir su documentación interactiva en `/api/docs` y la
descripción de sus rutas en `/api/openapi.json`, con parámetros, valores por
defecto y límites, y con la atribución al Ministerio en su descripción. La
raíz y las rutas fuera de `/api/` las usa la página web (`map-view`) y no
aparecen en la descripción de la API.

#### Scenario: Documentación
- **WHEN** se pide `GET /api/openapi.json`
- **THEN** describe exactamente las rutas `/api/health`, `/api/fuels`, `/api/stations/nearby`, `/api/stations/{station_id}` y `/api/provinces/prices`, su descripción incluye la atribución, y `GET /api/docs` responde 200 con una página HTML

#### Scenario: Sin documentación en la raíz
- **WHEN** se pide `GET /docs` o `GET /openapi.json`
- **THEN** la respuesta es 404 `no_encontrado`

#### Scenario: La página no está en la documentación
- **WHEN** la página web se sirve en `/` y se pide `GET /api/openapi.json`
- **THEN** no aparece la ruta `/` ni ningún archivo de la web

#### Scenario: Documentación desde el Mac (verificación manual)
- **WHEN** con el túnel SSH abierto y el Mac con acceso a internet (la página carga sus estilos y scripts de una CDN) se abre `http://127.0.0.1:8000/api/docs`
- **THEN** se ven las cinco rutas y se puede lanzar `GET /api/health` desde la página
