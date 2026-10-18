# Design

## Context

La motivación está en proposal.md («Why») y el comportamiento, en las specs
`station-detail` y `map-view` de este cambio. Aquí solo se explica cómo se
construye sobre la web que dejó `add-map-view`.

Estado actual de la web (`web/`, unos 208 KB servidos al abrir, de un
límite de 300 KB):

- `logic.js` reúne la lógica pura: formatos, fechas en hora de Madrid,
  `Retry-After` y validación de respuestas. Se prueba en el navegador desde
  `tests/unit/test_web_logic.py`.
- `api.js` hace cada petición con `request(path, signal)`, que tiene un
  límite de 15 s, y clasifica la respuesta con `classify()` en `ok`, `busy`,
  `no_data`, `outside_spain`, `unknown_fuel`, `server_error`, `unexpected`,
  `unreachable` o `aborted`.
- `main.js` guarda el estado y la búsqueda. `select(id, source)` abre la
  ficha y `closeDetail()` la cierra. `clearStations()` se llama al lanzar
  cada búsqueda y en todos sus errores.
- `view.js` pinta la ficha sencilla en `#detail-body`, con «Cerrar» en
  `.detail-actions`. Al abrirla, el foco pasa a «Cerrar».
- `map.js`: `showMarker(id)` hace `panInside` del marcador en la zona
  visible, calculada con el alto actual de la hoja.
- La CSP (D4 de `add-map-view`) es `default-src 'none'; script-src 'self';
  … connect-src 'self'; form-action 'none'`, y la cabecera
  `Referrer-Policy` es `strict-origin-when-cross-origin`.
- Los tests (`tests/web_fixtures.py`):
  - Usan cinco dispositivos: `iphone` y `iphone_landscape` en WebKit, y
    `pixel`, `small` y `desktop` en Chromium.
  - Una guarda de red en `context.route` aborta y anota toda petición que
    no va al servidor de prueba, y hace fallar el test al terminar.
  - `WebPage.mock(path, …)` sirve respuestas fijas por ruta, con retención
    (`hold`), errores de red y peticiones que no contestan nunca.
  - `page.clock` controla el tiempo.

## Goals / Non-Goals

**Goals:**
- Que todo lo nuevo de lógica pura (horario, precios, validación, captura,
  dispositivo y enlace) sea función de `logic.js`, para probarlo con
  unitarios sin DOM.
- Que el control de las peticiones de detalle esté en un único módulo, sin
  repartir estado por `main.js`.
- Reutilizar `request()` y `classify()` de `api.js` y los textos de
  `MESSAGES`, sin duplicar criterios de error.
- No cambiar la API, la CSP ni el servidor.

**Non-Goals:**
- Precargar detalles de gasolineras que no se han abierto.
- Guardar detalles entre búsquedas o entre visitas a la página.
- Detectar el dispositivo por otra vía que el agente de usuario (por
  ejemplo, `navigator.userAgentData`).

## Decisions

### D1. Archivos

- `web/js/logic.js` añade funciones puras (D2 a D5).
- Nuevo `web/js/detail.js`: la caché de detalles por búsqueda y sus
  peticiones (D6). No toca el DOM.
- `web/js/view.js` añade el pintado de la zona de estado, el horario, los
  precios, el aviso de captura y el enlace (D8).
- `web/js/main.js` conecta las piezas (D7).
- `web/index.html` añade en `#detail` la zona de estado, la zona de
  información y el enlace (D8).
- `web/styles.css` añade sus estilos (D9).
- Ningún archivo nuevo de terceros. El aumento previsto es de unos 8 a
  10 KB, con lo que el total queda en unos 218 KB de 300 KB.

*Alternativa descartada:* meter la caché en `main.js`. Ese archivo ya tiene
11 KB de estado de la búsqueda. La caché tiene su propio ciclo de vida
(una búsqueda) y se prueba mejor por separado.

### D2. Horario: `scheduleLines(schedule)`

Devuelve una lista de textos:
- Si `schedule` no es texto, devuelve `[]`.
- Si lo es, lo parte por `;`, quita a cada tramo los espacios del
  principio y del final (como `String.prototype.trim`, que incluye
  tabuladores y espacios no separables) y descarta los vacíos.

`[]` se pinta como «Horario no disponible». Cada tramo va en su propio
elemento de bloque con `overflow-wrap: anywhere`. No hay ninguna otra
transformación, porque así se decidió con los datos del 18/10/2026: « y »
no se parte y las abreviaturas no se traducen.

### D3. Respuesta del detalle: `parseDetail(body, id)`

Devuelve `{ok: true, lines, prices, capture}` o `{ok: false}`. Este último
caso se pinta como «El servidor ha dado una respuesta inesperada». Se
comprueba, en este orden:

1. `body.data` es un objeto.
2. `data.id` es texto e igual a `id`, sin convertir tipos.
3. `data.prices` es una lista.
4. Los precios válidos son los que tienen `slug`, `name` y `unit` como texto
   no vacío y `price` numérico, finito y mayor que 0.
5. Si la lista tenía elementos pero ninguno es válido, la respuesta es
   inesperada. Una lista vacía es válida: la ficha dice «No hay precios…».

`prices` sale ya ordenada con `orderPrices(prices, fuelSlug)`:
- primero el elemento con `slug === fuelSlug`, marcado con `searched: true`
  (si hay varios con ese `slug`, solo el primero);
- después los demás, en el orden recibido.

Lo que no se usa del detalle (rótulo, dirección…) se ignora sin
comprobarlo.

### D4. Captura más reciente: `newerCaptureText(searchCapture, detailCapture)`

- Usa el mismo criterio de fecha válida que `madridDateTime`: texto
  `YYYY-MM-DDTHH:MM:SSZ` que `Date` entiende.
- Si las dos fechas son válidas y la del detalle es estrictamente
  posterior, devuelve «Horario y precios de una captura más reciente: del
  DD/MM/AAAA a las HH:MM (hora de Madrid)».
- En cualquier otro caso devuelve `null`.

`main.js` guarda la `capture` de la última búsqueda correcta en el estado
para poder compararla.

### D5. Enlace: `mapsProvider(userAgent)` y `directionsLink(provider, lat, lon)`

**`mapsProvider(userAgent)`** pasa el agente de usuario a minúsculas y
devuelve:
- `google` si contiene `android`;
- si no, `apple` si contiene `iphone`, `ipad`, `ipod` o `macintosh`;
- si no, `osm`.

`android` se mira primero: algunos agentes de Android mencionan otros
sistemas.

**`directionsLink(provider, lat, lon)`** devuelve `{href, label}`. Cada
coordenada se escribe con `String(number)`, que es la escritura más corta
del número en JavaScript (`40.44`, `-3.7`, `40.416775`). Con coordenadas de
España nunca sale notación exponencial.

| Destino | `href` | `label` (nombre accesible) |
|---|---|---|
| `apple` | `https://maps.apple.com/?daddr=LAT,LON` | «Cómo llegar con Apple Maps (se abre en otra pestaña)» |
| `google` | `https://www.google.com/maps/dir/?api=1&destination=LAT,LON` | «Cómo llegar con Google Maps (se abre en otra pestaña)» |
| `osm` | `https://www.openstreetmap.org/directions?route=` + `encodeURIComponent(';LAT,LON')` | «Cómo llegar con OpenStreetMap (se abre en otra pestaña)» |

Las cadenas se montan a mano y no con `URLSearchParams`, que codificaría la
coma de Apple y de Google como `%2C`, y la spec fija la coma literal.

Las coordenadas son las de la estación en la búsqueda (`latitude` y
`longitude`), que `validStations` ya garantiza que son números. Así el
enlace existe desde que se abre la ficha, aunque el detalle falle.

*Alternativas descartadas:*
- El esquema `geo:`, porque en iOS no funciona y en Android deja elegir la
  aplicación (fuera de alcance).
- `maps.apple.com/directions?destination=`, el formato nuevo, porque
  `?daddr=` lo admiten también los iOS antiguos.

### D6. Caché y peticiones: `createDetailLoader({fetchOne, now, onChange})` en `detail.js`

**Estado.**
- Un `Map` de `id` a una entrada `{status, result, retryAt}`:
  - `status` es `loading`, `ok` o `error`;
  - `result` es la salida de `parseDetail` o la clasificación del error;
  - `retryAt` es el instante en que se activa «Reintentar», o 0.
- Un `AbortController` de la búsqueda actual.
- Un número de generación.

**Operaciones.**
- `reset()`: aborta el controlador, crea otro, vacía el `Map` y suma 1 a la
  generación. Lo llama `clearStations()` de `main.js`, que se ejecuta al
  lanzar cualquier búsqueda (también la que provoca la ubicación) y en
  todos sus errores. Así se cumple «se olvidan al lanzarse», no al recibir
  la respuesta.
- `open(station, fuelSlug)`:
  - Si ya hay entrada para ese `id`, la devuelve tal cual y no pide nada.
  - Si el `id` no es texto no vacío, crea una entrada `error` de tipo
    `unexpected` con `retryable: false`, sin petición.
  - Si no, crea la entrada en `loading` y lanza
    `fetchOne('/api/stations/' + encodeURIComponent(id), signal)`.
- `retry(id)`: solo actúa si la entrada está en `error`, es reintentable y
  `now() >= retryAt`. Entonces la pasa a `loading` antes de pedir, de modo
  que un segundo toque no hace nada, y lanza una petición.
- Al llegar una respuesta:
  - si su generación ya no es la actual, o el resultado es `aborted`, se
    ignora;
  - si no, se actualiza la entrada (con `parseDetail` si es `ok`; con
    `retryAt = now() + seconds * 1000` si es `busy`) y se llama a
    `onChange(id)`.

**Cambiar de ficha no aborta.** La respuesta de la ficha anterior completa
su entrada y no se pinta, porque `main.js` solo pinta si `id` es la ficha
abierta. Así reabrirla no vuelve a pedir nada.

**Tiempo.** `now` es `Date.now` y `page.clock` lo controla en los tests. La
cuenta de `Retry-After` vive en la entrada, no en el botón, y por eso sigue
desde el error original al reabrir la ficha.

**Errores.** Cada clasificación de `classify()` da su texto, como en `fail()`
de `main.js`:

| Clasificación | Texto |
|---|---|
| `busy` | `MESSAGES.busy`, con los segundos de `Retry-After` |
| `no_data` | `noDataText(message)` |
| `unreachable` | `MESSAGES.unreachable` |
| `server_error`, `unknown_fuel`, `outside_spain` | `MESSAGES.server_error` (otros errores JSON que no son 503, incluido el 404 `estacion_no_encontrada`) |
| `unexpected` | `MESSAGES.unexpected` |

Una función `errorText(result)` en `view.js` reúne esta traducción. `fail()`
pasa a usarla, sin cambiar ningún texto.

*Alternativa descartada:* abortar la petición al cambiar de ficha. Obligaría
a pedirla otra vez al reabrir y rompería «como mucho una petición por
gasolinera y búsqueda».

### D7. Conexión en `main.js`

- `select(id, source)`:
  - tras `view.openDetail(…)`, llama a `detail.open(station, state.fuel)` y
    pinta la entrada con `view.renderDetail(entry, …)`;
  - el enlace se pinta con `directionsLink(mapsProvider(navigator.userAgent),
    station.latitude, station.longitude)`.
- `onChange(id)`: si `state.selected === id` y la ficha está abierta,
  vuelve a pintar la entrada y llama a `map.showMarker(id)` (D10).
- «Reintentar» del detalle: llama a `detail.retry(state.selected)`, pinta
  la entrada (otra vez «Cargando horario…») y mueve el foco a la zona de
  estado.
- `clearStations()` llama a `detail.reset()`.
- `state.searchCapture` guarda `result.body.capture` de la última búsqueda
  correcta.
- Al cerrar la ficha se cancela el temporizador del «Reintentar» del
  detalle (D8), pero no la entrada.
- `window.__mapView` expone también el cargador, como el resto del estado,
  para depurar.

### D8. Vista de la ficha

Estructura de `#detail`:

```
#detail
  #detail-body            (con scroll)
    datos de la búsqueda   (como hoy: rótulo, dirección, municipio, precio, distancia)
    #detail-status         role="status", aria-live="polite", tabindex="-1"
    #detail-retry          botón «Reintentar» (oculto si no hay error reintentable)
    #detail-info           aviso de captura, horario (lista) y precios (lista)
  .detail-actions          (fija al pie)
    #detail-close          «Cerrar»
    #detail-directions     <a target="_blank" rel="noopener noreferrer"> «Cómo llegar»
```

**Zona de estado.** Solo lleva el texto corto:
- «Cargando horario…» mientras carga;
- «Ficha cargada» cuando hay detalle, también al reabrir desde la caché
  (decisión del usuario: siempre es verdad);
- el mensaje de error.

Va siempre visible y con estilo discreto. Puede recibir el foco tras
«Reintentar» y por eso no se oculta visualmente: así el foco nunca queda
en un elemento invisible.

**Zona de información.** Fuera de la zona viva, para que el lector no lea
todo de golpe:
- encabezados «Horario» y «Precios» (`h3`);
- horario como `<ul>` de tramos, o «Horario no disponible»;
- precios como `<ul>`. Cada `<li>` lleva «Nombre · 1,529 €/l» y, si es el
  buscado, un `<span class="searched-tag">Buscado</span>` al final y la
  clase `searched`, de modo que el texto «Buscado» es visible y forma parte
  del contenido accesible;
- con `prices` vacía, «No hay precios de esta gasolinera en la última
  captura»;
- el aviso de captura más reciente, encima del horario.

Todo se pinta con `textContent`, como el resto de la página.

**Orden de tabulación.** «Reintentar» → «Cerrar» → «Cómo llegar», que es el
orden del DOM. No hay trampa de foco: un Tab más desde «Cómo llegar» sigue
al siguiente elemento de la página.

**«Reintentar» del detalle.** Es un botón propio (`#detail-retry`), no el
`#retry` de la página. Si `retryAt` está en el futuro, se pinta desactivado
con un `setTimeout(retryAt - now)` que lo activa. Ese temporizador se
cancela al cerrar o al volver a pintar la ficha.

**Enlace.** Lleva `aria-label` con el `label` de D5. El texto visible es
«Cómo llegar», al principio del nombre accesible (WCAG 2.5.3).

`rel="noreferrer"` hace que la navegación no lleve `Referer`, aunque la
página use `strict-origin-when-cross-origin`. La CSP no restringe la
navegación de un enlace (no hay `navigate-to`), así que no hay que tocarla.

### D9. Estilos (mobile first)

- `.detail-actions` pasa a `display: flex; gap; justify-content:
  space-between`: «Cerrar» a la izquierda y «Cómo llegar», con aspecto de
  botón principal, a la derecha, al alcance del pulgar derecho. Los dos con
  `min-height` y `min-width` de `var(--touch)` (44 px).
- `#detail-retry` reutiliza el estilo de `.retry` (44 px).
- Horario y precios llevan `overflow-wrap: anywhere` y las listas no tienen
  viñetas. El precio de cada línea no se parte (`white-space: nowrap` en su
  `span`) y el nombre sí.
- `.searched` va en negrita con un borde a la izquierda, y `.searched-tag`
  es una etiqueta con texto; el color nunca es la única pista.
- Escritorio (`@media (min-width: 1024px)`): `.detail` pasa de `max-height:
  none` a `max-height: 70dvh`, con `#detail-body` desplazable y
  `.detail-actions` fija. Así la fila de acciones se ve siempre y la lista
  sigue debajo, en el panel (pendiente del proposal).
- Sin `vh`, sin `max-width` y sin `:hover` fuera de `@media (hover: hover)`.
  Las zonas seguras ya las tiene el relleno de `.detail`, y la fila de
  acciones está dentro.

### D10. El marcador sigue a la vista cuando la ficha crece

Al llegar el detalle, la hoja crece hasta como mucho el 70 % del alto. Tras
pintarla, `onChange` llama a `map.showMarker(id)`, que vuelve a calcular el
relleno con el alto nuevo de la hoja y hace `panInside` sin cambiar el
zoom. Lo mismo al reabrir desde la caché, porque `select()` ya llama a
`showMarker` después de abrir y el contenido se pinta antes.

*Alternativa descartada:* reservar el alto máximo de la ficha desde que se
abre. Taparía mapa en vano mientras carga y, con detalles cortos, dejaría
un hueco vacío.

### D11. Tests

**Unitarios** (`tests/unit/test_web_detail_logic.py`), con la misma
técnica que `test_web_logic.py`: `import('/js/logic.js')` y
`import('/js/detail.js')` desde una página vacía.
- `scheduleLines`: los escenarios del horario, incluidos los reales del
  18/10/2026.
- `parseDetail` y `orderPrices`: elementos válidos y no válidos, `data.id`
  ausente, numérico o distinto, `prices` ausente, `null` u objeto, y ningún
  precio válido.
- `newerCaptureText`: posterior, igual, anterior, desconocida y búsqueda sin
  fecha. Se ejecuta en Chromium y en WebKit, como las demás fechas.
- `mapsProvider`, con los agentes de usuario de los cinco dispositivos, un
  iPad con iPadOS, un Linux y mayúsculas cambiadas; y `directionsLink`, con
  "1003" y "4375".
- `createDetailLoader`, con `fetchOne` y `now` falsos:
  - una petición por `id`;
  - reutilización mientras carga y tras un error;
  - `reset` descarta respuestas en camino;
  - `retry` respeta `retryAt` y no hace nada con dos toques seguidos;
  - un `id` no válido no pide nada.

**Funcionales**, con Playwright, en `tests/functional/`:
- `test_web_detail.py`: carga, horario, precios, captura, caché, carreras,
  límite de 15 s, errores, textos sin «API» e inyección de HTML.
- `test_web_directions.py`: enlace por dispositivo, privacidad y pulsación.
- `test_web_detail_layout.py`: mobile first, objetivos táctiles,
  atribuciones, giro, zonas seguras y accesibilidad.

**Respuestas fijas** nuevas en `tests/fixtures/web/`, generadas por
`make_web_fixtures.py` con la forma de siempre:
- `station_4375.json`: «L-D: 24H», `gasoleo-a` 1.459 y `gasolina-95-e5`
  1.529, captura `2026-10-16T07:26:37Z`;
- `station_4375_newer.json`: `gasoleo-a` 1.479, captura `08:26:40Z`;
- `station_4375_full.json`: cuatro tramos y cinco precios;
- `station_4375_empty.json`: `schedule` `null` y `prices` `[]`;
- `station_1001.json`, `station_1002.json` y `station_1003.json`, con
  horarios distintos;
- `station_not_found.json`: 404 `estacion_no_encontrada`.

Los errores reutilizan las respuestas que ya existen (`busy_base_retry_5`,
`busy_api_retry_12`, `busy_base_retry_abc`, `long_query`, `no_captures`,
`bad_gateway_html`, `proxy_503_html` e `internal_error`). Los casos de forma
rara (id distinto, `prices` no lista, horarios de los escenarios) son dicts
en el propio test, que `WebPage.mock` ya admite.

**Agente de usuario.** `open_page` pasa a aceptar `user_agent`, que llega a
`new_context`. Los dispositivos `small` y `desktop` lo fijan siempre en los
tests de esta spec con constantes de `tests/web_helpers.py`:

- `UA_LINUX_CHROME`;
- `UA_MAC_SAFARI`;
- `UA_IPADOS`, con «Macintosh» y sin «iPad».

Sin ese parámetro, el Chromium de Playwright en un Mac dice «Macintosh» y
el test dependería del equipo. `iphone` y `pixel` usan el agente de su
descriptor.

**Pulsar «Cómo llegar» sin abrir nada.** Un método nuevo,
`WebPage.intercept_directions()`:
- registra un `context.route` para `https://maps.apple.com/**`,
  `https://www.google.com/maps/**` y `https://www.openstreetmap.org/directions**`;
- anota la URL y las cabeceras y hace `route.abort()`;
- no pasa por la lista `blocked` de la guarda, y por eso no hace fallar el
  test.

Al registrarse después de la guarda tiene prioridad sobre ella (Playwright
prueba primero la ruta más reciente). Va en el contexto y no en la página
porque `target="_blank"` abre otra página del mismo contexto, y el test la
espera con `context.expect_page()`. En Chromium, `--host-resolver-rules`
impide además cualquier resolución de DNS. Los tests que no pulsan el
enlace no registran esta ruta, así que cualquier petición a esos dominios
sigue haciéndolos fallar («Sin peticiones hasta pulsar»).

**Encaje con la API real.** Un test con la base de prueba guarda "4375" con
`Horario` «L-D: 24H» y los dos precios del escenario «Estación con precios»
de `prices-api`, abre su ficha y comprueba el horario y los precios.

**Tests de `map-view` que cambian con la spec** (requieren la autorización
del usuario, como en `add-map-view`):
- `tests/functional/test_web_search.py::test_open_and_see_details`:
  «Abrir y ver la ficha» pasa a esperar una petición `/api/stations/{id}`
  por cada una de las tres fichas.
- `test_web_search.py`, test de «Ficha completa» (línea 573 aprox.): deja
  de exigir «ninguna petición» y comprueba que los datos de la búsqueda se
  ven antes de que llegue el detalle (con `hold=True`).
- `test_web_search.py::test_tap_on_a_station_marker`: la única petición es
  `/api/stations/1001`.
- `test_web_search.py`, test de «Peticiones al usar la página» (línea 712
  aprox.): pulsa "1003" y añade el escenario «Pulsar «Cómo llegar»».
- El test de «Objetivos táctiles» de `test_web_accessibility.py` añade
  «Cómo llegar» y el «Reintentar» del detalle.
- El test de «Textos de la página sin la palabra API» quita hoy
  `#detail-body` del texto recogido. Pasa a quitar solo los datos de la
  gasolinera (`#detail-info` y la cabecera con los datos de la búsqueda) y
  a recorrer también los estados de la ficha.
- `test_web_readme.py`: comprueba la privacidad de «Cómo llegar» y la línea
  del Simulador.

**Determinismo.** `page.clock` controla los 15 s, `Retry-After` y la
reapertura a los 2 s; `hold=True` controla el orden de llegada de las
respuestas en las carreras; y la zona horaria es `UTC` en los escenarios de
captura.

### D12. README

En la sección de la web:
- la privacidad de «Cómo llegar» del escenario: qué aplicación abre, que
  solo lleva las coordenadas de la gasolinera, que solo ocurre al pulsar y
  que esa aplicación puede usar su propia ubicación;
- en el Simulador de iOS, que se compruebe la ficha con horario, precios y
  «Cómo llegar» (que abre Apple Maps).

## Risks / Trade-offs

- **[Riesgo]** A 750×342, la ficha al 70 % (unos 239 px) deja unos 100 px
  de mapa menos la caja de atribuciones, y meter el marcador ahí es justo.
  → `panInside` con el relleno real (D10), y un test específico en
  horizontal con atribuciones y marcador. Si no cabe, se compacta la
  cabecera de la ficha (precio y distancia en una línea) sin cambiar sus
  textos.
- **[Riesgo]** Apple Maps, Google Maps u OpenStreetMap podrían cambiar el
  formato de sus enlaces. → Son formatos públicos y estables, y se
  comprueban a mano en el Simulador de iOS (README). Los tests solo
  verifican la dirección generada, nunca abren el servicio.
- **[Riesgo]** El agente de usuario puede mentir (modo escritorio en
  Android, que dice Linux). → Ese caso abre OpenStreetMap, que funciona en
  cualquier navegador. Elegir la aplicación a mano está fuera de alcance.
- **[Compromiso]** La respuesta de una ficha anterior se completa aunque ya
  no se vea, y descarga unos cientos de bytes que quizá no se usen. → Es lo
  que permite reabrirla sin pedir nada otra vez.
- **[Compromiso]** Con una captura nueva entre la búsqueda y la ficha, el
  precio de arriba y el de «Buscado» pueden diferir. → Decisión 18 del
  proposal: lo explica el aviso de captura.
- **[Riesgo]** WebKit emulado con `target="_blank"` puede abrir la pestaña
  nueva de otra manera que Chromium. → La ruta interceptada está en el
  contexto y el test espera la página nueva con `expect_page()`. Si WebKit
  no la abre en el emulador, el test del iPhone comprueba `href`, `target` y
  `rel`, y la pulsación se comprueba en Pixel 7 y escritorio. Se documenta
  en el test.
- **[Riesgo]** Que otro test abra fichas sin respuesta fija y el detalle
  vaya al servidor de prueba sin base. → Da un 503 `sin_base` que solo
  afecta a la ficha y no hace fallar la guarda (es del propio origen).
  Los tests de `map-view` que comprueban la ficha quedan igual.

## Migration Plan

No hay migración de datos: no cambian la API ni la base, y el histórico no
se toca.

Despliegue: se reconstruye la imagen (`docker compose build api` y
`docker compose up -d`), que copia `web/`. Lo lanza el usuario, en el Mac y
en el VPS.

Marcha atrás: volver a la imagen anterior. La página no guarda nada nuevo
en el navegador.
