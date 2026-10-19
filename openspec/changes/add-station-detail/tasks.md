# Tasks

## 0. Autorización

- [x] 0.1 Autorización del usuario (18/10/2026) para modificar ocho tests de `map-view` cuyos escenarios cambian con este cambio: `test_open_and_see_details`, `test_full_detail`, `test_tap_on_a_station_marker` y `test_requests_while_using_the_page` en `test_web_search.py`; `test_touch_targets` con su función de apoyo `touch_targets`, `test_no_api_word_in_page_texts` y `test_rotate_with_detail_open` en `test_web_accessibility.py`; y `test_ios_simulator` en `test_web_readme.py`. Cada cambio va en la tarea que provoca el fallo (4.1, 4.3, 5.2, 6.1 y 7.1). Ningún otro test existente se modifica sin preguntar.

## 1. Preparación de los tests

- [ ] 1.1 Añadir a `tests/fixtures/web/make_web_fixtures.py` las respuestas fijas de D11 y generarlas:
  - `station_4375`, `station_4375_newer`, `station_4375_full` y `station_4375_empty`;
  - `station_1001`, `station_1002` y `station_1003`;
  - `station_not_found`.

  Son respuestas de nuestra API escritas a partir de la spec `prices-api` («Ficha de una estación»), no del Ministerio. Verificar con el test que ya carga cada archivo de `tests/fixtures/web/` y comprueba `status` y cuerpo.
- [ ] 1.2 En `tests/web_fixtures.py`:
  - `open_page` acepta `user_agent` y lo pasa a `new_context`;
  - nuevo `WebPage.intercept_directions()` (D11): `context.route` para `maps.apple.com`, `www.google.com/maps` y `www.openstreetmap.org/directions`, que anota URL y cabeceras y aborta sin pasar por `blocked`.

  En `tests/web_helpers.py`, las constantes `UA_LINUX_CHROME`, `UA_MAC_SAFARI` y `UA_IPADOS`. Verificar con un test de humo en `tests/functional/test_web_harness.py`, sobre un HTML vacío servido por `page.route` con un enlace `target="_blank"` a `https://maps.apple.com/?daddr=1,2`:
  - al pulsarlo, la URL queda anotada y `web.guard.blocked` sigue vacía;
  - sin `intercept_directions()`, la misma pulsación deja la URL en `web.guard.blocked`; el test lo comprueba y vacía la lista antes de terminar, porque la guarda solo falla al desmontar el fixture;
  - control de `Referer` con `route.request.all_headers()`: un enlace con `rel="noreferrer"` llega sin `Referer` y otro igual sin `noreferrer` sí lo lleva, para que la comprobación no pueda pasar en vacío.

## 2. Lógica pura (`web/js/logic.js`)

- [ ] 2.1 Escribir `scheduleLines` (D2) y probarla en `tests/unit/test_web_detail_logic.py` con los escenarios de «Horario tal como lo publica el Ministerio»: varios tramos, uno, dos franjas en un día, «L: 24H», tramos vacíos y espacios, formato raro, `null`, «;» y el número `24`. Verificar que pasan.
- [ ] 2.2 Escribir `parseDetail` y `orderPrices` (D3) y probarlas con los escenarios de «Precios de todos los combustibles…» y de «Sin respuestas de otra ficha»:
  - buscado el primero, otra unidad, sin precios, buscado ausente;
  - elementos no válidos y ningún precio válido;
  - `prices` `null`, objeto o ausente;
  - `data.id` «1002», numérico o ausente;
  - `slug` buscado repetido.

  Verificar que pasan.
- [ ] 2.3 Escribir `newerCaptureText` (D4) y probarla con «Captura nueva…» (en `UTC` → «10:26»), misma captura, captura del detalle desconocida, anterior y búsqueda sin fecha, en Chromium y en WebKit. Verificar que pasan.
- [ ] 2.4 Escribir `mapsProvider` y `directionsLink` (D5) y probarlas:
  - con los agentes de usuario del iPhone 13 y del Pixel 7 de Playwright, `UA_MAC_SAFARI`, `UA_IPADOS`, `UA_LINUX_CHROME` y variantes con mayúsculas cambiadas;
  - con las coordenadas de "1003" (`40.44,-3.73`) y de "4375" (`40.416775,-3.70379`);
  - comprobando las tres URLs exactas de la spec y los tres nombres accesibles.

  Verificar que pasan.

## 3. Caché y peticiones del detalle (`web/js/detail.js`)

- [ ] 3.1 Escribir `createDetailLoader` (D6), con `fetchOne` y `now` inyectables, y la traducción `errorText` en `view.js`. Hacer que `fail()` de `main.js` use `errorText` sin cambiar textos. Verificar en `tests/unit/test_web_detail_logic.py`, con `fetchOne` y `now` falsos:
  - una sola petición por `id` (también al reabrir mientras carga y tras un error);
  - `reset(fuelSlug)` aborta y descarta lo que está en camino, y una respuesta de una generación anterior que llega después no cambia ninguna entrada (así se prueba el descarte por generación, que en el navegador no se puede forzar porque la petición antigua se aborta);
  - `parseDetail` recibe el combustible guardado en `reset`;
  - `retry()` no hace nada antes de `retryAt` ni con dos toques seguidos;
  - un `id` `""` o numérico no pide nada y da `unexpected` sin reintento;
  - la ruta va codificada (`12%2F3%3Fx`).

  Verificar también que siguen pasando los tests de errores de la página: `pytest tests/functional/test_web_errors.py`.

## 4. Ficha completa en la página

- [ ] 4.1 Añadir a `web/index.html` y `web/js/view.js` la estructura de D8: `#detail-status`, `#detail-retry`, `#detail-info` y `#detail-directions` (el orden del DOM da el de tabulación), y el pintado de cada estado (cargando, cargado, error y aviso de captura). Conectarlo en `main.js` (D7):
  - `openDetail` y `closeDetail` solo reemplazan `#detail-head`;
  - `select()` abre y pinta;
  - `onChange` vuelve a pintar solo la ficha abierta y llama a `map.showMarker`;
  - `clearStations()` llama a `detail.reset(state.fuel)`;
  - se guarda `state.searchCapture`;
  - al cerrar se cancela el temporizador del «Reintentar» del detalle.

  Modificar, con la autorización de 0.1, los tests de `map-view` que fallan desde este momento:
  - `test_open_and_see_details`: una petición `/api/stations/{id}` por cada una de las tres fichas;
  - `test_full_detail`: datos de la búsqueda visibles antes de que llegue el detalle (con `hold=True`), sin exigir «ninguna petición»;
  - `test_tap_on_a_station_marker`: la única petición es `/api/stations/1001`;
  - `test_rotate_with_detail_open`: espera a que llegue el detalle antes de contar peticiones.

  Escribir `tests/functional/test_web_detail.py` con los escenarios de «Carga del detalle al abrir la ficha», «Horario…», «Precios…» y «Captura del detalle más nueva…» (respuestas fijas; iPhone por defecto), incluida «Gasolinera de la búsqueda sin identificador válido». Verificar que pasan.
- [ ] 4.2 Añadir a `tests/functional/test_web_detail.py`, con `hold=True` y `page.clock`, los escenarios de «Una petición por gasolinera y búsqueda» y «Sin respuestas de otra ficha»:
  - reabrir, también mientras llega;
  - tres fichas;
  - nueva búsqueda, también la de la ubicación del navegador, probada así: abrir "4375", esperar el detalle, cerrar la ficha, pulsar «Volver a mi ubicación» (en el móvil está en la hoja de la lista), reabrir "4375" y comprobar que se pide de nuevo una sola vez;
  - respuesta de una búsqueda anterior (en el navegador se comprueba que la ficha muestra solo la respuesta nueva y que hubo dos peticiones; la petición antigua se aborta, así que su `release()` va dentro de un `try`; el descarte por generación ya lo prueba 3.1);
  - página quieta 5 minutos;
  - cambiar de ficha antes de la respuesta;
  - otro identificador;
  - cerrar antes de la respuesta.

  Repetir en el Pixel 7 los de comportamiento común: abrir la ficha, llega el detalle, reabrir la misma ficha y cambiar de ficha antes de la respuesta. Verificar que pasan.
- [ ] 4.3 Añadir los escenarios de «Límite de tiempo del detalle», «Errores del detalle» y «Textos del detalle como texto»:
  - 15 s con margen de 1 s;
  - `Retry-After` 5, 12 y `abc`, y `consulta_demasiado_larga`, con margen de 0,5 s;
  - reintentar con doble toque, lanzado con dos `dispatchEvent('click')` seguidos en el mismo `evaluate` (una sola petición, ninguna a `nearby` ni a `fuels`);
  - «Reintentar» que funciona tras una respuesta 200 rechazada por `parseDetail` (ningún precio válido, otro identificador y `prices` que no es lista);
  - sin datos, red, HTML 502, HTML 503, 404 y 500;
  - el resto de la página sigue igual;
  - reabrir con error y reabrir a los 2 s de un `Retry-After: 5`;
  - textos sin «API», modificando además (0.1) `test_no_api_word_in_page_texts` para que quite solo lo que llega del servidor (`#detail-head`, tramos del horario y nombres y precios de la lista) y conserve los textos propios de la ficha de D11, recorriendo sus estados;
  - horario y nombre con etiquetas.

  Verificar que pasan.
- [ ] 4.4 Añadir el test de encaje con la API real (escenario «Encaje del detalle con la API real»): base de prueba con "4375" (`Horario` «L-D: 24H», Gasoleo A 1,459 y Gasolina 95 E5 1,529). Verificar que la ficha muestra «L-D: 24H», «Gasoleo A · 1,459 €/l» y «Gasolina 95 E5 · 1,529 €/l», y que `./data` no se usa.

## 5. «Cómo llegar»

- [ ] 5.1 Pintar `#detail-directions` en `view.js` con `directionsLink(mapsProvider(navigator.userAgent), …)`, con `aria-label`, `target="_blank"` y `rel="noopener noreferrer"`. Escribir `tests/functional/test_web_directions.py` con los escenarios de «Enlace «Cómo llegar» según el dispositivo»:
  - iPhone (WebKit);
  - Mac (escritorio con `UA_MAC_SAFARI`);
  - iPad con iPadOS (`desktop` con `UA_IPADOS`);
  - Android (Pixel 7);
  - otros (`small` y `desktop` con `UA_LINUX_CHROME`);
  - muchos decimales;
  - otra pestaña y sin claves;
  - disponible aunque el detalle cargue o falle;
  - el enlace cambia con la ficha.

  Verificar que pasan.
- [ ] 5.2 Añadir los escenarios de «Cómo llegar» sin la ubicación de quien busca: sin la ubicación, sin el punto pinchado, sin peticiones hasta pulsar, y la pulsación con `intercept_directions()` y `context.expect_page()`. La pulsación comprueba que se navega exactamente a la URL, que no hay `Referer` (con `all_headers()`) y que la ficha sigue abierta. Si WebKit emulado no abre la pestaña, en el iPhone se comprueban solo `href`, `target` y `rel`, y la pulsación con la dirección de Apple Maps se prueba en `desktop` con `UA_MAC_SAFARI` (nota del escenario). Modificar (0.1) `test_requests_while_using_the_page`: pulsa "1003" y añade el escenario «Pulsar «Cómo llegar»» de `map-view`, con el mismo plan B (nota del escenario de `map-view`). Verificar que pasan y que la guarda no anota nada bloqueado.

## 6. Mobile first, accesibilidad y estilos

- [ ] 6.1 Escribir los estilos de D9 en `web/styles.css`:
  - fila de acciones con «Cerrar» y «Cómo llegar» de 44 px;
  - `#detail-retry`, listas, `.searched` y `.searched-tag`;
  - en escritorio, `.detail` con `max-height: 70dvh` y el cuerpo desplazable.

  Escribir `tests/functional/test_web_detail_layout.py` con los escenarios de «Ficha completa mobile first»:
  - iPhone con cuatro tramos y cinco precios (marcador a la vista tras llegar el detalle, D10);
  - horizontal a 750×342, con atribuciones y marcador;
  - 320×568 con rótulo de 80 caracteres y atribuciones;
  - horario de 200 caracteres sin espacios;
  - Pixel 7 con toques;
  - escritorio;
  - objetivos táctiles;
  - girar con el detalle cargado sin peticiones;
  - zonas seguras.

  Modificar (0.1) `test_touch_targets` y su función de apoyo `touch_targets`, que hoy no mide enlaces, para incluir «Cómo llegar» y el «Reintentar» del detalle (escenario «Objetivos táctiles» de `map-view`).

  Antes de dar por buena la horizontal, medir la zona visible del mapa con la ficha completa. Si el marcador no cabe, compactar la cabecera según el riesgo de design.md. Verificar que pasan y que siguen pasando los tests de hojas de estilo de `test_web_map.py` (sin `max-width`, sin `vh` y sin `:hover` suelto).
- [ ] 6.2 Escribir en `tests/functional/test_web_detail_layout.py` los escenarios de «Accesibilidad de la ficha completa» (con `page.clock` en pausa, avanzar al menos 16 ms tras abrir la ficha para ver la zona de estado):
  - llega el detalle con el foco en «Cerrar» y la zona de estado diciendo «Cargando horario…» y después «Ficha cargada», sin horario ni precios dentro;
  - ficha cargada sin horario ni precios;
  - reabrir una ficha ya cargada («Ficha cargada» desde el principio, sin pedir nada);
  - error anunciado;
  - orden con el tabulador en escritorio, con salida de la ficha, usando un error con «Reintentar» activo (red caída; con un 503 y `Retry-After` el botón está desactivado y no recibe el foco);
  - foco tras «Reintentar»;
  - nombres accesibles en iPhone, Pixel 7 y escritorio con `UA_LINUX_CHROME`;
  - «Buscado» en el contenido visible y en el árbol de accesibilidad de la lista de precios (`aria_snapshot()`), sin `aria-hidden`.

  Verificar que pasan.
- [ ] 6.3 Medir el peso con el test existente de «Peso de la página» (iPhone en WebKit, sin caché) y verificar que sigue en 300 KB o menos.

## 7. README

- [ ] 7.1 Actualizar la sección de la web del README (D12): la privacidad de «Cómo llegar» y la línea del Simulador de iOS con la ficha completa. Añadir a `tests/functional/test_web_readme.py` el test de «Privacidad de «Cómo llegar»» y modificar (0.1) `test_ios_simulator` para la línea nueva del Simulador. Verificar que pasan.

## 8. Comprobación final

- [ ] 8.1 Ejecutar la batería completa: `.venv/bin/pytest`, incluidos `-m browser` y los unitarios. Verificar que no se salta ningún test de navegador por motor ausente y, para el escenario «Dispositivos del detalle», que el resumen de `pytest_terminal_summary` al ejecutar solo `tests/functional/test_web_detail*.py tests/functional/test_web_directions.py` muestra los cinco dispositivos (iphone, iphone_landscape, pixel, small y desktop) con sus motores.
- [ ] 8.2 Verificación manual opcional, que lanza el usuario y no bloquea el archivo: en el Simulador de iOS, abrir una ficha, comprobar horario, precios y «Buscado», y pulsar «Cómo llegar» para ver que abre Apple Maps con la ruta a la gasolinera. En un Android real, si lo hay, comprobar que abre Google Maps.

## Workflow follow-up

- Agente test-writer y después agente code-reviewer.
- `/opsx:archive` cuando el code-reviewer dé «Listo para archivar».
- `/publish-doc`: página de la funcionalidad «Ficha de la gasolinera», con «Qué no hace todavía» (¿abierta ahora?, traducir abreviaturas por la ambigüedad de «L» en los datos de origen, favoritos, compartir y arrastrar la hoja); decisiones en «Decisiones»; entrada del Changelog; estado en «Visión del proyecto»; y «Cómo llegar» en el Glosario si hace falta.
- El usuario reconstruye la imagen y la despliega en el Mac y en el VPS (`docker compose build api` y `docker compose up -d`).
