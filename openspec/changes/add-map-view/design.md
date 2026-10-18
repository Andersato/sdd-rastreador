# Design

## Context

Motivación y alcance: ver proposal.md. Requisitos: `specs/map-view/spec.md`
y el delta de `specs/prices-api/spec.md`.

Estado actual que condiciona el diseño:

- `src/api/app.py` crea la app con `create_app(db_path, …)`. Las rutas están
  todas bajo `/api/`. Los errores de Starlette pasan por un manejador que
  responde 404 `no_encontrado` y 405 `metodo_no_permitido` con `Allow: GET`
  fijo (`app.py`, manejador `http_error`).
- `src/api/access_log.py` escribe una línea por petición. Para las rutas de
  la web solo saldrá la ruta (no tienen parámetros conocidos).
- `container/api.py` arranca uvicorn con `create_app(Path(DB_PATH), …)`. La
  imagen copia `src/` y `container/` a `/app/`.
- `tests/conftest.py` bloquea la red de Python fuera de `127.0.0.1`. Ese
  bloqueo no alcanza al navegador de Playwright, que es otro proceso.
- No hay JavaScript en el repo ni paso de compilación. Node está instalado
  en el Mac, pero no se usará: los tests de JavaScript corren en el
  Chromium de Playwright.

## Goals / Non-Goals

**Goals:**
- Servir `web/` desde la misma app sin cambiar nada observable en `/api/*`:
  mismos 404 y 405 y la misma documentación.
- Separar la lógica pura (formatos, tercios, redondeo, fechas,
  `Retry-After`, validación de respuestas) de la lógica que toca el DOM y
  Leaflet, para probarla con unitarios en el navegador.
- Que los tests funcionales sean deterministas: reloj, ubicación y zona
  horaria simulados, y ninguna petición fuera del equipo.

**Non-Goals:**
- Empaquetar o minificar el JavaScript, compatibilidad con navegadores
  antiguos (se usan módulos ES y `fetch`), traducciones.
- Cambiar el registro de accesos para que omita los archivos estáticos.

## Decisions

### D1. Archivos de `web/`

```
web/
  index.html          página única (lang="es"), sin scripts ni estilos en línea
  styles.css
  favicon.ico
  js/
    main.js           arranque: conecta estado, mapa, controles y peticiones
    api.js            peticiones con tiempo límite y clasificación de respuestas
    logic.js          funciones puras: formatos, tercios, coordenadas, fechas,
                      Retry-After, validación de /api/fuels y de cercanas
    storage.js        preferencias con try/catch
    view.js           DOM: hojas inferiores, panel, lista, ficha, avisos,
                      leyenda, foco
    map.js            todo lo que toca Leaflet
  vendor/leaflet/     leaflet.js, leaflet.css, images/, LICENSE, VERSION
```

`index.html` carga `vendor/leaflet/leaflet.js` como script clásico (global
`L`) y después `js/main.js` como `type="module"`. Los módulos importan
`logic.js` y no dependen unos de otros en ciclo. `logic.js` y `api.js` no
tocan el DOM ni `L`, así que se pueden importar a solas en los unitarios.

*Alternativa descartada:* un solo `app.js`. Es más fácil de servir, pero no
se puede probar la lógica sin cargar la página entera.

### D2. Leaflet 1.9.4

Leaflet 1.9.4 es la última versión estable de la rama 1.x. Funciona como
script clásico, sin compilar, y es la API que documentan casi todos los
ejemplos. La rama 2.x solo se distribuye como módulos ES y cambia la API
(por ejemplo, ya no hay global `L`); no aporta nada que necesitemos aquí.

- **Obtención:** del tarball de npm
  `https://registry.npmjs.org/leaflet/-/leaflet-1.9.4.tgz`, comprobando su
  `integrity` (sha512) con el valor que publica el registro. De ahí se
  copian a `web/vendor/leaflet/` `dist/leaflet.js`, `dist/leaflet.css`,
  `dist/images/` y `LICENSE` (BSD-2-Clause).
- **`VERSION`:** guarda la versión y la suma sha512 del tarball.
- **Descarga:** se hace una sola vez y la lanza el usuario con el comando
  exacto de la tarea 1.2.

### D3. Servir la web: montaje que no toca `/api/`

`create_app` recibe `web_dir: Path | None`. Por defecto es
`Path(__file__).parents[2] / "web"`, que vale igual en el repo y en `/app`
dentro de la imagen. Con `web_dir=None`, o si la carpeta no existe, no se
monta nada y `GET /` da 404 como antes. La web se monta en `/`, después de todas las rutas,
con una subclase de `StaticFiles` (`html=True`, para que `/` sirva
`index.html`) que:

1. **Rutas de `/api/`:** si la ruta empieza por `/api/`, no busca archivos.
   - Si alguna ruta de la API casa con esa ruta con otro método, responde
     405 `metodo_no_permitido` con `Allow: GET`. Se comprueba con
     `route.matches(scope)` y `Match.PARTIAL`.
   - Si la ruta termina en `/` y sin esa barra casa con una ruta de la API,
     responde 307 a la ruta sin barra (con la misma consulta), igual que hace
     hoy `redirect_slashes` de Starlette.
   - Si no, responde 404 `no_encontrado`.
   - Así `HEAD /api/fuels` sigue dando 405, `/api/fuels/` 307 y
     `/api/precios` 404, como hoy.
     Sin esto, Starlette pasaría al montaje `/` las peticiones con un método
     que la ruta no admite.
2. **Resto de rutas:** las sirve `StaticFiles`.
   - Admite GET y HEAD.
   - Con otro método responde 405 con `Allow: GET, HEAD` y el mensaje
     «solo se admiten GET y HEAD», también sobre
     archivos que no existen (pendiente 1): primero se mira el método,
     después el archivo.
   - `HEAD` de un archivo que no existe da 404 con las mismas cabeceras que
     el GET y sin cuerpo; uvicorn no envía cuerpo en las respuestas a HEAD.
   - `StaticFiles` ya impide salir de `web/` y no lista carpetas: una carpeta
     sin `index.html` da 404.
3. **Cabeceras de las respuestas de la web** (solo para los archivos de
   `web/` y sus errores; los 404, 405 y 307 de `/api/` del punto 1 no las
   llevan, y `/api/docs` tampoco, porque su CSP impediría cargar Swagger
   desde la CDN):
   - `Cache-Control: no-cache`, para que una versión nueva de `web/` se vea
     al recargar; el navegador revalida con `ETag` y `Last-Modified`.
   - `X-Content-Type-Options: nosniff`.
   - `Referrer-Policy: strict-origin-when-cross-origin`, explícita. Así las
     teselas llevan `Referer: http://127.0.0.1:<puerto>/`, sin la ruta.
   - `Content-Security-Policy` de D4.

El manejador `http_error` se cambia para que el 405 use la cabecera `Allow`
que le pasa la excepción, con `GET` como valor por defecto (pendiente 2).
Un montaje no entra en `openapi.json`, así que la documentación no cambia.

*Alternativa descartada:* una ruta comodín `/{path:path}` con
`FileResponse`. Obliga a reescribir la protección contra rutas que salen de
la carpeta y el manejo de `ETag` que `StaticFiles` ya trae.

### D4. Content-Security-Policy

```
default-src 'none'; script-src 'self'; style-src 'self';
img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self';
font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

Con esta política el navegador garantiza «sin recursos de terceros salvo
las teselas», y además limita el daño si un texto se colara como HTML.

Leaflet escribe estilos con `element.style`, que la CSP permite. Lo que no
permite son atributos `style="…"` dentro de cadenas HTML. Por eso los
marcadores son `L.divIcon` con clases (`tier-cheap`, `tier-mid`,
`tier-expensive`, `tier-single`, `selected`) y contenido creado con
`textContent`, nunca `innerHTML` con datos.

### D5. Estado y peticiones

`main.js` guarda un único estado: combustibles, combustible y radio
elegidos, punto, origen del punto (`location` o `click`), ubicación del
navegador, si esa ubicación dio `fuera_de_espana`, resultados, gasolinera
seleccionada, error y la marca «el usuario ha pinchado» (`userClicked`),
que no se borra aunque el punto se quite tras un 422.

- **Combustibles listos:** una promesa `fuelsReady`. Toda búsqueda espera a
  que se resuelva. Si `/api/fuels` falla, la búsqueda queda pendiente con su
  punto y la lanza «Reintentar» tras unos combustibles correctos.
- **Una búsqueda a la vez:** cada búsqueda tiene un número de secuencia y su
  propio `AbortController`. Una búsqueda nueva aborta la anterior, y una
  respuesta con un número que no es el último se ignora.
- **Tiempo límite:** 15 s por petición, con `AbortController` y
  `setTimeout`. Un aborto por tiempo se distingue de uno por búsqueda nueva.
- **`api.js` clasifica cada respuesta** en: `ok` (JSON válido), `busy` (503
  `api_ocupada`, `base_ocupada` o `consulta_demasiado_larga`, con sus
  segundos de espera), `no_data` (otro 503 en JSON, con su `message`),
  `outside_spain` (422 `fuera_de_espana`), `unknown_fuel` (422
  `combustible_desconocido`), `server_error` (cualquier otro error en JSON),
  `unexpected` (cuerpo que no es JSON, en cualquier estado, o JSON con
  forma inesperada) y `unreachable` (red o tiempo agotado).
  - `view.js` traduce cada clase al texto de la spec.
  - Ningún texto propio de la página dice «API».
- **Página quieta:** no hay temporizadores repetitivos ni sondeos. Los
  únicos temporizadores son el de la ubicación (10 s), el tiempo límite de
  cada petición (15 s) y la cuenta atrás de «Reintentar».
- **`/api/health`:** se pide una vez al arrancar, en paralelo con
  `/api/fuels`. Si falla, no se avisa de nada.

### D6. Ubicación

- **Petición:** `navigator.geolocation.getCurrentPosition` con
  `enableHighAccuracy: false` y `maximumAge: 600000`, sin `timeout` nativo:
  el tiempo que el usuario tarda en responder al permiso no lo contaría. El
  plazo de 10 s lo lleva un temporizador propio desde la llamada.
- **Respuesta tardía:** si la ubicación llega tarde, se guarda y se muestra
  «Volver a mi ubicación»; solo se busca en ella si `userClicked` es falso
  (spec, «Espera de la ubicación»). Así, tras pinchar en Rabat y recibir un
  422, la ubicación que llegue no lanza ninguna búsqueda.
- **Sin geolocalización:** `navigator.geolocation` no existe, o lanza un
  error al llamarlo. Se trata como denegada.
- **Contexto seguro:** `http://127.0.0.1` cuenta como contexto seguro, así
  que la geolocalización funciona por el túnel sin HTTPS.

### D7. Mapa

- **Vista de España:** `fitBounds([[35.9, -9.4], [43.9, 4.4]])`, que son
  los rectángulos de la Península y Baleares de la API.
- **Capa de teselas:** `L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19})` con la atribución `© <a
  href="https://www.openstreetmap.org/copyright">OpenStreetMap
  contributors</a>`.
- **Textos de Leaflet en español:** `L.control.zoom` con `zoomInTitle:
  'Acercar'` y `zoomOutTitle: 'Alejar'`, que Leaflet usa como `title` y
  `aria-label`.
- **Atribuciones:** una sola caja arriba a la izquierda del mapa, que
  ninguna hoja tapa: se quita el control de atribución por defecto y se
  añade `L.control.attribution({position: 'topleft', prefix: false})`, con la
  de OpenStreetMap (de la capa de teselas) y la del Ministerio
  (`addAttribution('Datos: Ministerio de Industria, …')`). El control de
  zoom se añade después en la misma esquina, así que Leaflet lo apila debajo
  y no se solapan. La esquina lleva `margin-top: env(safe-area-inset-top)` y
  `margin-left: env(safe-area-inset-left)` (la muesca, en horizontal, queda
  a un lado), y la caja, un ancho máximo de la pantalla menos los márgenes. La licencia de Leaflet va en
  `vendor/leaflet/LICENSE`; OpenStreetMap no pide mostrar Leaflet.
- **Copias del mundo:** se dejan (`worldCopyJump: false`). Los pinchazos se
  normalizan con `normalizeLon` en `logic.js`:
  `((lon + 180) % 360 + 360) % 360 - 180`, y una longitud de 180 se escribe
  como -180.
- **Punto de búsqueda:** un `L.circleMarker` neutro y un `L.circle` del
  radio. Tras cada búsqueda nueva, `fitBounds(circle.getBounds(), padding)`.
- **Zona visible del mapa:** en el móvil, el mapa ocupa toda la pantalla y
  los encuadres (`fitBounds` de España y del círculo, `panInside` del
  marcador al abrir una ficha) llevan `paddingTopLeft` con el alto de la caja
  de atribuciones (sin contar el zoom, que es estrecho y queda a un lado,
  como dice la spec), y `paddingBottomRight` con el alto de la hoja
  que esté a la vista (lista plegada, lista desplegada o ficha), medidos en
  ese momento con `getBoundingClientRect`. En el escritorio el relleno es
  fijo, de 16 px. El círculo se encuadra al elegir el punto o el radio y se
  vuelve a encuadrar después de pintar cada respuesta (también con `total` 0
  y con errores que dejan el círculo), porque la hoja cambia de alto al
  llenarse. Con una hoja desplegada o una ficha alta, la hoja puede tapar en
  parte los botones de zoom: la spec no lo impide y se sigue pudiendo
  pellizcar para acercar.
  Cuando cambia el alto de la ventana (giro), se llama a
  `map.invalidateSize()` y se vuelve a meter en la zona visible el marcador
  seleccionado o, si no hay, el círculo.
- **Ficha:** no es un `L.popup`: es un elemento propio de la página
  (`<section id="detail">`), que en el móvil es una hoja inferior y en el
  escritorio va en el panel lateral (D10). Su contenido se crea con DOM y
  `textContent`, con el botón «Cerrar». Escape se escucha en `document` y la
  cierra si está abierta.

### D8. Lógica pura (`logic.js`)

- **Coordenadas:** `roundCoord(x)` redondea a 3 decimales, con la mitad
  lejos de cero, sobre `Math.abs(x) * 1000` corregido con
  `toPrecision(15)`. `coordParam(x)` devuelve el texto con
  `toFixed(3)`, por ejemplo `40.417` o `-2.400`.
- **Precios:** `formatPrice(1.4, '€/l')` da «1,400 €/l», con `toFixed(3)` y
  coma decimal.
- **Distancias:** `formatDistance(2.05)` da «2,1 km». Primero
  `Number(x.toPrecision(12))` y después la mitad hacia arriba con un
  decimal, porque 2.05 en binario es 2.0499….
- **Tercios:** `tiers(prices)` trabaja en milésimas enteras
  (`Math.round(p * 1000)`).
  - Con un solo precio distinto, todas son `single`.
  - Las del mínimo son `cheap` y las del máximo `expensive`.
  - Para cada otro precio se calculan L (cuántas son más baratas) y H
    (cuántas son más caras). Es `cheap` si `3L < N` y no `3H < N`;
    `expensive` si `3H < N` y no `3L < N`; si no, `mid`. Así no hay
    divisiones.
- **Fecha de la captura:** `captureText(iso)` acepta solo
  `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`. Formatea con
  `Intl.DateTimeFormat('es-ES', {timeZone: 'Europe/Madrid', …, hourCycle:
  'h23'})` mediante `formatToParts`, para no depender del formato por
  defecto. Con cualquier otro valor da `null`, y la página muestra «Fecha de
  la captura desconocida».
- **`Retry-After`:** `retryAfterSeconds(value)` admite `^\d+$` entre 1 y 60;
  en cualquier otro caso, 5.
- **Validación:** `validFuels(data)` y `validStations(stations)` aplican las
  reglas de la spec y devuelven también cuántas estaciones descartan.

### D9. Preferencias

- **Clave:** `precios-gasolineras.preferencias`, con el JSON `{"fuel":
  "<slug>", "radius": <km>}`. Lectura y escritura van en try/catch, y
  `JSON.parse` también.
- **Cuándo se guarda:** solo cuando el usuario cambia un selector. Los
  valores que la página elige por defecto (al arrancar o tras un 422
  `combustible_desconocido`) no se guardan, para no borrar la preferencia
  si el combustible vuelve a venderse (pendiente 4). Al cambiar solo el
  radio se conserva el combustible guardado, aunque ahora no esté en la
  lista; al cambiar el combustible se conserva el radio guardado. Si no
  había nada guardado, se escribe solo la clave que cambió (por ejemplo
  `{"radius": 25}`), y al leer se acepta que falte cualquiera de las dos.
- **Coordenadas:** nunca se guardan ni se escriben en la URL.

### D10. Vista, colores y accesibilidad

**Mobile first.** `styles.css` está escrito para el móvil (320–430 px) y
el escritorio se añade con una sola media query `@media (min-width:
1024px)`; no hay media queries `max-width`. Por debajo de 1024 px (también
tabletas y móviles en horizontal) se usa el diseño de móvil.

**Estructura de `index.html`** (el orden del DOM es el del móvil: mapa y
después la hoja):

```
<div id="map">                       mapa (atribuciones y zoom dentro, arriba a la izquierda)
<section id="panel">                 hoja de la lista (móvil) / panel lateral (escritorio)
  <div class="panel-head">           siempre a la vista
    controles (combustible, radio, «Volver a mi ubicación»)
    aviso de datos desactualizados (role="status")
    zona aria-live: pista, mensaje, recuento
    «Reintentar»
    fila: recuento + «Ver lista» (solo móvil)
    «Más barata: …» (solo móvil)
  <div class="panel-body">           móvil: solo desplegada; escritorio: siempre
    captura, «Hay N gasolineras…», descartadas, leyenda, <ol> de la lista
<section id="detail" hidden>         ficha: hoja inferior (móvil) / en el panel (escritorio)
```

**Móvil (base).**
- `body` con `height: 100dvh` y `overflow: hidden`; `#map` con `position:
  fixed; inset: 0` y `height: 100dvh`, así que ocupa toda la pantalla.
- `#panel` y `#detail` con `position: fixed; left: 0; right: 0; bottom: 0`,
  fondo blanco, esquinas superiores redondeadas y `z-index` por encima de
  los controles de Leaflet (1000). Relleno: `calc(8px +
  env(safe-area-inset-bottom))` abajo y `calc(16px +
  env(safe-area-inset-left/right))` a los lados.
- La hoja plegada solo enseña `.panel-head`. La desplegada (`.expanded`)
  enseña también `.panel-body`; la hoja entera tiene `max-height: 70dvh`, y
  el cuerpo, `overflow-y: auto` y `overscroll-behavior: contain` para que el
  scroll de la lista no mueva el mapa ni la página.
- **Estado entre búsquedas:** la hoja sigue desplegada mientras cada búsqueda
  nueva dé lista. Si una se queda sin lista (sin resultados, error o punto
  fuera de España), se quita `.expanded`, y la siguiente empieza plegada.
- **Ficha:** al abrirla, `#panel` se oculta (`hidden`) y se ve `#detail` en su
  sitio, con `max-height: 70dvh`: el contenido se desplaza dentro y la fila
  de «Cerrar» va fuera de la parte que se desplaza, siempre a la vista. Al
  cerrarla vuelve `#panel` con su estado de plegada o desplegada.
- **Hoja plegada compacta:** los controles en una fila que se parte en dos si
  no cabe (selectores sin etiqueta encima, con la etiqueta a la izquierda en
  la misma línea); el recuento y «Ver lista» en la misma fila; y debajo «Más
  barata: …» en una línea que se corta con puntos suspensivos si no cabe. A
  320×568, unos 190 px; en horizontal (342 px de alto), unos 150 px. La tarea
  4.1 lo mide antes de darlo por bueno.
  *Medido en la 4.1 (con resultados y «Volver a mi ubicación»):* a 320×568
  la hoja plegada mide 270 px (los controles ocupan tres filas) y la zona
  visible del mapa es el 41 % del alto (la spec pide 40 %); a 750×342, 166
  px, con los controles a partir de y=186 (mitad inferior); en el iPhone
  (390×664), 218 px y el 58 %.
- **Selectores en Safari:** `appearance: none` y una flecha SVG en línea
  (`data:`), porque Safari no respeta el alto mínimo de 44 px de un `select`
  con su aspecto nativo (medía 23 px).
- Botón «Ver lista» / «Ocultar lista» con `aria-expanded` y
  `aria-controls="panel-body"`. La línea «Más barata: CEPSA · 3,4 km · 1,399
  €/l» es un botón que abre la ficha de esa gasolinera.
- Sin arrastre: la hoja se despliega y se pliega solo con su botón.

**Escritorio (`min-width: 1024px`).**
- `body` en rejilla de dos columnas: `360px` y el resto; `#map` pasa a
  `position: relative` en la segunda columna, con `height: 100dvh`.
- `#detail` y `#panel` van en la primera columna, uno encima del otro, sin
  posición fija; el panel tiene su propio scroll (`overflow-y: auto`) y
  `.panel-body` se ve siempre. «Ver lista» y «Más barata» se ocultan.

**Sin hover.** No hay reglas `:hover` fuera de `@media (hover: hover)`, y
las que hay solo cambian el fondo. Ninguna información aparece solo al
pasar el puntero (no se usan `title` ni tooltips de Leaflet como única vía).

**Alturas y zonas seguras.** Ninguna medida en `vh` sin `d`. La meta
`viewport` es `width=device-width, initial-scale=1, viewport-fit=cover`, sin
`maximum-scale` ni `user-scalable`, para que `env(safe-area-inset-*)` tenga
valor en iOS y no se impida el zoom.

**Giro.** `resize` y `orientationchange` llaman, con un `requestAnimationFrame`,
a `map.invalidateSize()` y al reencuadre de D7. No se hace ninguna petición.

**Peso.** Sin contar teselas ni `/api/`: `leaflet.js` (unos 145 KB),
`leaflet.css` (15 KB), los módulos propios, `styles.css`, `index.html` y el
favicon, unos 210 KB en total, por debajo del límite de 300 KB. Leaflet no
llega a pedir sus imágenes (`images/`) porque los marcadores son
`L.divIcon` y no hay control de capas. Fuentes del sistema
(`system-ui`), sin fuentes web. No se comprime en el servidor: queda fuera
de este cambio.

**Filas.** `overflow-wrap: anywhere` en rótulos y direcciones; el precio va
en su propia columna de la fila, con `flex: none`.

**Objetivos táctiles.** Selectores, botones, filas y los botones de zoom de
Leaflet (agrandados con CSS) miden al menos 44×44 px.

**Colores.** Se eligen azul, ámbar y rojo, que se distinguen mejor que el
verde y el rojo con daltonismo:

| Tercio | Fondo | Texto | Contraste |
|--------|-------|-------|-----------|
| Más barata | `#0b5cad` (azul) | blanco | ≈ 6,7:1 |
| Intermedia | `#f2c94c` (ámbar) | `#1f2328` | ≈ 10:1 |
| Más cara | `#b42318` (rojo) | blanco | ≈ 6,6:1 |
| Precio único | `#4b5563` (gris) | blanco | ≈ 7,6:1 |

La gasolinera resaltada lleva un borde de 3 px `#1f2328` y va encima de las
demás; los colores no cambian. Los tests miden el contraste en el navegador.

**Accesibilidad.**
- La lista es un `<ol>` de `<button>`.
- Los selectores tienen su `<label for>`.
- Una zona `aria-live="polite"` en `.panel-head` para la pista, el mensaje o
  error y el recuento, y el aviso de datos desactualizados aparte, con
  `role="status"`. «Hay N…» y las descartadas van en `.panel-body`, fuera de
  esa zona: la spec no pide anunciarlos.
- Los marcadores no se alcanzan con el teclado: la lista es la vía
  accesible.

**Foco.**
- Al abrir una ficha, el foco pasa a su botón «Cerrar».
- Al cerrarla con «Cerrar» o con Escape, vuelve a la fila de esa gasolinera
  si la lista se ve (escritorio o hoja desplegada), tanto si se abrió desde
  la lista como desde el marcador; con la hoja plegada, al botón «Ver lista».
  Si se abrió desde «Más barata: …», vuelve a ese botón.
- Si la ficha se cierra por una búsqueda nueva, el foco se queda en el
  control que se usó (selector, botón o mapa) (pendiente 3).
- Si «Volver a mi ubicación» desaparece con el foco en él (por un 422), el
  foco pasa a la zona de mensajes, que tiene `tabindex="-1"`.

### D11. Tests

**Dependencias.**
- `requirements-dev.txt` añade, con versión fija y solo para desarrollo
  (nunca en `requirements.txt` ni en la imagen), lo que instaló el usuario en
  el `.venv`: `pytest-playwright==0.10.0`, `playwright==1.64.0`,
  `greenlet==3.5.6`, `pyee==14.0.0`, `python-slugify==9.1.3` y
  `text-unidecode==1.3`. Esta versión de `pytest-playwright` ya no instala
  `pytest-base-url` ni `requests`.
- `playwright install chromium` y `playwright install webkit` se lanzan una
  vez (Chrome for Testing 156.0.8078.4 y WebKit 27.2, ya instalados en el
  Mac) y se documentan en el README.
- Se añade el marcador `browser`. Cada test de navegador se salta con un
  aviso si su motor (Chromium o WebKit) no está instalado, como los de
  Docker. La comprobación final (tarea 12.1) exige que no se salte ninguno.

**Dispositivos.** Las descripciones de Playwright tal cual, con su ventana
(el área que deja el navegador, no la pantalla entera) y su motor:
- por defecto, `iPhone 13` en **WebKit** (390×664, `is_mobile`, `has_touch`,
  `device_scale_factor` 3), el motor de Safari;
- `iPhone 13 landscape` en WebKit (750×342) para los de giro y horizontal;
- `Pixel 7` en Chromium (412×839, táctil, móvil) para repetir los escenarios
  comunes (búsqueda, hoja, ficha, controles y toques);
- 320×568 táctil en Chromium para el tamaño mínimo;
- escritorio en Chromium (1280×800, sin toque) para el panel lateral, el
  teclado y el desplazamiento de la lista.

Los navegadores los lanzan los fixtures con el `playwright` de
pytest-playwright (`playwright.webkit` y `playwright.chromium`, una vez por
sesión cada uno), no con el `browser` único del plugin. Chromium lleva
`--host-resolver-rules`; WebKit no tiene esa opción, así que en WebKit la
guarda de red es solo `context.route` (ver riesgos).

En los dispositivos táctiles los tests usan `tap()`, no `click()`. En WebKit
emulado `navigator.maxTouchPoints` vale 0 aunque haya toque: la página no lo
usa para nada y responde a los mismos eventos de clic que lanzan los toques.

**Peso de la página.** Contexto nuevo sin caché; se suman `len(await
response.body())` de las respuestas del propio origen fuera de `/api/` hasta
que la página muestra el recuento de la búsqueda. Solo cuerpos, sin
cabeceras.

**Servidor de los tests.**
- Un fixture arranca `uvicorn.Server` en un hilo, en `127.0.0.1` y en un
  puerto libre.
- La app es `create_app` con una base de prueba creada en `tmp_path` por la
  ingesta real (`tests/api_helpers.py` y `tests/storage_helpers.ingest`). En
  los casos que no necesitan base, la ruta de la base no existe.
- Nunca se usan `./data` ni el puerto 8000.

**Red del navegador.**
- Chromium se lanza con `--host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE
  127.0.0.1"`: no puede resolver ningún otro nombre, ni siquiera para el
  prefetch de DNS de los enlaces, que `context.route` no ve.
- `context.route("**/*")` deja pasar solo `http://127.0.0.1:<puerto>/`.
- Las teselas `https://tile.openstreetmap.org/{z}/{x}/{y}.png` se responden
  con `tests/fixtures/web/tile.png`, una imagen de 256×256 en gris.
- Cualquier otra petición se aborta, se anota, y el fixture hace fallar el
  test al terminar.
- Las peticiones también se registran, para los escenarios de recuento y
  de `Referer`.

**Respuestas fijas.**
- Están en `tests/fixtures/web/*.json`, con la forma `{"status", "headers",
  "body"}`, o `body_text` para HTML.
- Se sirven con `page.route` sobre la ruta concreta (`/api/fuels`,
  `/api/stations/nearby`, `/api/health`): 503 con y sin `Retry-After`, 502
  en HTML, 500, 422, respuestas con forma inesperada y estaciones con datos
  no válidos.
- Son respuestas de nuestra API escritas a mano a partir de la spec. No son
  respuestas del Ministerio, así que no hace falta pedírselas al usuario.

**Determinismo.**
- `page.clock.install()` controla los 10 s, los 15 s, la cuenta atrás de
  `Retry-After` y los 5 minutos de la página quieta, sin esperar de verdad.
- La ubicación se simula con un `add_init_script` que sustituye
  `navigator.geolocation` por un objeto controlado desde el test: conceder,
  denegar, no responder, responder más tarde o no existir.
- La zona horaria se fija con `timezone_id` del contexto: `America/New_York`
  y `UTC`.

**Unitarios de JavaScript** (`tests/unit/test_web_logic.py`).
- Se navega a `http://127.0.0.1:<puerto>/__unit__.html`, que se responde
  con un HTML vacío mediante `page.route`, sin añadir nada a `web/`.
- Desde ahí se hace `import('/js/logic.js')`, y se comprueba cada función
  con los ejemplos de la spec.
- Corren en Chromium, y los de fechas (`captureText`, `staleText`, que usan
  `Intl` con `Europe/Madrid`) también en WebKit, porque el iPhone es el
  objetivo principal.
- `api.js` se importa igual. Su `fetch` se simula con `page.route` sobre las
  rutas de `/api/`, que responden con las respuestas fijas de 1.4, de modo
  que se prueba el `fetch` real del navegador.

**«En el motor de Safari»** (WebKit): `CSS.supports('height', '100dvh')` y
`CSS.supports('padding', 'env(safe-area-inset-bottom)')` son verdaderos, el
alto calculado de `body` y del mapa es igual a `innerHeight`, y el borde
inferior de la hoja plegada coincide con el de la ventana.

**Giro.** Los tests de giro abren el iPhone 13 en vertical y cambian el
tamaño con `page.set_viewport_size({'width': 750, 'height': 342})`, que
lanza `resize` (no `orientationchange`; la página escucha los dos). El
descriptor horizontal queda para los escenarios que son solo en horizontal.

**Objetivos táctiles.** Los tamaños se miden con `bounding_box()` sin tocar
los elementos: con una hoja abierta, los botones de zoom pueden quedar
tapados en parte (D7) y un toque fallaría.

**Funcionales.**
- `tests/functional/test_web_serving.py` usa `TestClient`, sin navegador:
  `/`, HEAD, favicon, carpetas, salir de `web/`, POST, `HEAD /api/fuels`,
  cabeceras y OpenAPI.
- `tests/functional/test_web_*.py` usan Playwright, agrupados por
  requisito.
- `tests/docker/test_web_image.py` comprueba la página servida por el
  contenedor.

**Comprobación del contraste:** se calcula con `getComputedStyle` y la
fórmula de luminancia relativa de WCAG.

### D12. Docker y README

- **Docker:** el `Dockerfile` añade `COPY web/ /app/web/`.
  `.dockerignore` no excluye `web/`. Los tests de Docker existentes se
  actualizan (autorizado por el usuario): `BUILD_FILES` en
  `tests/docker/helpers.py` incluye `web`, y `test_image.py` y
  `test_build_context.py` esperan que `/app` contenga exactamente
  `container`, `src` y `web`, sin nada más. El test nuevo comprueba que
  `/app/web/index.html` y `/app/web/vendor/leaflet/LICENSE` existen.
- **README:** una sección nueva, «Web del mapa», después de «API de
  consulta», con:
  - `http://127.0.0.1:8000/`;
  - el túnel `ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>`;
  - la variante `-L 8001:127.0.0.1:8000` y `http://127.0.0.1:8001/` si la
    API del Mac ocupa el 8000;
  - que el mapa necesita internet para las teselas;
  - la nota de privacidad de la spec;
  - la verificación opcional en el Simulador de iOS de Xcode: abrirlo
    (Xcode → Open Developer Tool → Simulator), elegir un iPhone con muesca,
    abrir Safari en `http://127.0.0.1:8000/` (el Simulador comparte la red
    del Mac, así que llega a `127.0.0.1` y, por él, al túnel), darle una
    ubicación (Features → Location → Custom Location, por ejemplo 40.4168,
    -3.7038) y comprobar la hoja, la ficha, los controles abajo y que la
    muesca y la barra inferior no tapan nada, en vertical y en horizontal.

  En «Tests» se añaden `playwright install chromium` y `playwright install
  webkit`.

### Pendientes resueltos

| # | Pendiente | Resolución |
|---|-----------|------------|
| 1 | HEAD y POST sobre un archivo inexistente | D3: POST da 405 con `Allow: GET, HEAD`; HEAD da 404 sin cuerpo. |
| 2 | `Allow` distinto en la web y en la API, y montaje que no capture `/api/` | D3. |
| 3 | Foco al cerrar la ficha por una búsqueda nueva | D10: se queda en el control usado. |
| 4 | ¿Se guarda el combustible elegido por defecto tras `combustible_desconocido`? | D9: no. |
| 5 | Pinchar fuera de España mientras se espera la ubicación y que llegue después | Gana el pinchazo (D5 y D6, marca `userClicked`): solo aparece «Volver a mi ubicación». Escenario «Pinchar fuera de España mientras se espera». |

## Risks / Trade-offs

- **[Riesgo]** La política de teselas de OpenStreetMap puede bloquear a
  clientes con mucho uso o sin `Referer`.
  → **Mitigación:** el uso es personal y bajo; se envía el origen como
  `Referer`; no hay precarga ni service worker.
- **[Riesgo]** Con 100 marcadores de texto a 25–50 km se solapan.
  → **Mitigación:** la lista ordenada es la vista principal. Agruparlos
  queda fuera de alcance (proposal).
- **[Riesgo]** El montaje en `/` cambia, sin que se note, cómo se responden
  peticiones raras en `/api/` (métodos distintos de GET, rutas
  desconocidas).
  → **Mitigación:** la comprobación de D3, y tests que repiten los
  escenarios de 404 y 405 de `prices-api` con la web montada.
- **[Riesgo]** El Chromium de Playwright puede intentar conexiones que
  `context.route` no ve (prefetch de DNS, servicios internos).
  → **Mitigación:** `--host-resolver-rules` impide resolver cualquier nombre
  salvo `127.0.0.1`, y Playwright desactiva los servicios internos en modo
  headless.
- **[Contrapartida]** Redondear a 3 decimales desplaza el centro hasta unos
  70 m. Con radios de 5 km o más no cambia de forma apreciable qué
  gasolineras entran, y las distancias que se muestran son desde el punto
  redondeado.
- **[Riesgo]** El WebKit de Playwright es el motor de Safari, pero no Mobile
  Safari en un iPhone: no emula la muesca ni la barra inferior, así que
  `env(safe-area-inset-*)` vale 0 y la barra no se esconde al desplazar.
  → **Mitigación:** los tests comprueban en WebKit que las reglas con `dvh`
  y `env()` se aceptan y que el alto coincide con `innerHeight`; los valores
  reales los cubre la verificación manual opcional en el Simulador de iOS de
  Xcode (README). Solo se usan funciones estándar (módulos ES, `fetch`,
  `Intl`, `AbortController`, `dvh`), disponibles desde Safari 15.4.
- **[Contrapartida]** El propio `<select>` de WebKit hace que el navegador
  informe de una violación `style-src-attr` de la CSP (pasa también en una
  página que solo tiene un `select`). No bloquea nada de la página; los tests
  ignoran ese mensaje concreto en WebKit (`tests/web_fixtures.py`).
- **[Riesgo]** En WebKit no hay `--host-resolver-rules`, así que un prefetch
  de DNS no lo vería `context.route`.
  → **Mitigación:** la página no tiene enlaces a otros dominios salvo el de
  la atribución de OpenStreetMap, y la CSP impide cualquier petición fuera
  de su origen y de las teselas; los tests de Chromium, con la regla de
  resolución, cubren lo mismo.
- **[Riesgo]** La emulación del Android en Chromium tampoco es un móvil
  real (barra de direcciones, teclado).
  → **Mitigación:** se usan los tamaños de ventana de Playwright, que ya
  descuentan las barras.
- **[Contrapartida]** Con el mapa a pantalla completa, la hoja plegada tapa
  parte del mapa; por eso los encuadres usan relleno (D7) y la hoja
  desplegada se limita al 70 % del alto.
- **[Riesgo]** Que el navegador conserve una versión vieja de `web/` tras
  actualizar el VPS.
  → **Mitigación:** `Cache-Control: no-cache` con `ETag`.

## Verificación manual (tareas 12.2 y 12.3, 2026-10-18)

- **Mac (12.2)**, API local con los datos del 16/10, arrancada con `docker
  compose up -d api` (el programador exige `./backups` y en el Mac no hace
  falta; queda en el README). En Chrome, `http://127.0.0.1:8000/` con la
  ubicación concedida y denegada: mapa, lista y ficha correctos. Con la vista
  de móvil de las herramientas de desarrollo: hoja inferior, «Ver lista»,
  ficha y giro correctos. El aviso de datos desactualizados se ve, como
  corresponde a datos del 16/10. No se probó el Simulador de iOS (opcional).
- **VPS (12.3)**: actualización con la sección 13 del runbook, sin
  incidencias. Por el túnel, en el Mac, la página muestra los precios del día sin aviso.
  También se abrió desde un móvil real de la misma Wi-Fi, con el túnel
  escuchando en `0.0.0.0:8001` del Mac: la página se ve y funciona (hoja,
  lista y ficha); la ubicación automática no está disponible, porque el
  navegador solo la da en HTTPS o en `127.0.0.1`, y se elige el punto
  pinchando, como prevé la spec.
  *Nota:* mientras el túnel escucha en `0.0.0.0`, cualquier equipo de esa
  red llega a la API y a la web; el procedimiento documentado sigue siendo
  el túnel en `127.0.0.1`.

## Migration Plan

- **Sin migración de datos:** la base no cambia y la API sigue abriéndola
  en solo lectura.
- **Despliegue en el VPS:** el procedimiento de siempre de
  `docs/vps-deployment.md`, sección 13: `git pull`, `docker compose build`
  y `docker compose up -d`. Después, por el túnel, se abre
  `http://127.0.0.1:8000/`. Esa ejecución la lanza el usuario.
- **Verificación opcional en el Simulador de iOS** (no bloquea el archivo):
  con el túnel abierto en el Mac, Safari del Simulador de Xcode en
  `http://127.0.0.1:8000/`, con ubicación simulada (Features → Location), en
  vertical y horizontal, en un modelo con muesca. Los pasos van en el README
  (D12).
- **Vuelta atrás:** volver al commit anterior y reconstruir. Sin `web/`,
  `GET /` vuelve a dar 404.
