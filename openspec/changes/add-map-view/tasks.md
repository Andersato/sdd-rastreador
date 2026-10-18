# Tasks

## 1. Preparación: dependencias, Leaflet y utilidades de test

- [x] 1.1 Añadir a `requirements-dev.txt`, con versión fija y solo ahí (nunca en `requirements.txt`), `pytest-playwright==0.10.0`, `playwright==1.64.0`, `greenlet==3.5.6`, `pyee==14.0.0`, `python-slugify==9.1.3` y `text-unidecode==1.3`, que son las versiones que el usuario ya instaló en el `.venv` (D11). Verificar con `.venv/bin/pip check` y con un `pip install -r requirements-dev.txt` que no cambie nada. Verificar también que la imagen no los incluye: `requirements.txt` no cambia.
- [x] 1.2 Pasar al usuario el comando exacto para descargar `leaflet-1.9.4.tgz` del registro de npm y comprobar su `integrity` sha512, y esperar su resultado (D2). Copiar a `web/vendor/leaflet/` `leaflet.js`, `leaflet.css`, `images/` y `LICENSE`, y escribir `VERSION` con la versión y la suma. Verificar que la suma coincide con la del registro.
- [x] 1.3 Añadir el marcador `browser` en `pyproject.toml` y, en `tests/`, los fixtures de navegador (D11):
  - servidor uvicorn en un puerto libre con base de prueba en `tmp_path`;
  - Chromium lanzado con `--host-resolver-rules`;
  - guarda de red con `context.route` y teselas sustituidas por `tests/fixtures/web/tile.png`;
  - registro de peticiones;
  - ubicación simulada con `add_init_script`;
  - `page.clock`;
  - lectura de respuestas fijas desde `tests/fixtures/web/`.

  Verificar con un test de humo, sobre un HTML vacío servido por `page.route`:
  - una petición a `https://example.org/` queda bloqueada y anotada por la guarda, y la comprobación final de la guarda lanza un error;
  - una petición a `/api/health` llega al servidor de prueba.
- [x] 1.4 Crear todas las respuestas fijas de `tests/fixtures/web/` con la forma de D11, de modo que estén listas antes de los tests que las usan:
  - **503:** `base_ocupada` y `api_ocupada` con `Retry-After` 5, 12, ausente, 0, `abc`, 3600 y una fecha; `consulta_demasiado_larga`; `sin_capturas` con mensaje, sin mensaje y con `<b>sin datos</b>`; código desconocido; 503 en HTML.
  - **Otros errores:** 502 en HTML; 500 `error_interno`; 422 `fuera_de_espana` y `combustible_desconocido`; 404; 405; 429.
  - **`/api/fuels`:** con elementos no válidos; con los 21 a 0; con `data` que no es lista.
  - **Cercanas:** con estaciones de datos no válidos; con todas descartadas; sin `data.stations`; con `total` 342 y 100 estaciones, con 2 descartadas y sin descartadas; con `total` 130 a 5 km; con 40 estaciones; con rótulo de 80 caracteres; con rótulo `<img src=x onerror=alert(1)>`; con `total` 0; con `capture.downloaded_at` de invierno y no válido.
  - **`/api/health`:** `ok`, `desactualizada`, `configuracion_no_valida` y 503.

  Los demás casos de los escenarios salen de la base de prueba o se crean en la tarea de su test. Verificar con un test que carga cada archivo y comprueba que tiene `status` y un cuerpo (`body` o `body_text`).

## 2. Servir la web desde la app

- [x] 2.1 Añadir a `create_app` el parámetro `web_dir` (D3): valor por defecto, y sin montaje si es `None` o si la carpeta no existe. Montar `web/` en `/` con la subclase de `StaticFiles` que no atiende `/api/` (404, 405 con `Allow: GET` y 307 con barra final, como hoy) y añade las cabeceras de D3 y D4. Crear `web/index.html` mínimo (título «Gasolineras baratas cerca», `lang="es"`) y `web/favicon.ico`.
- [x] 2.2 Hacer que el manejador de 405 use el `Allow` y el mensaje de la excepción:
  - en la web, `GET, HEAD` y «solo se admiten GET y HEAD»;
  - en `/api/*`, `GET` y el mensaje de siempre.
- [x] 2.3 Tests con `TestClient` en `tests/functional/test_web_serving.py`:
  - todos los escenarios de «Página servida en la raíz»: «Abrir la página», HEAD, favicon, «Archivo inexistente», carpeta, salir de `web/`, POST, `HEAD /api/fuels`, barra final `GET /api/fuels/` → 307, página sin base, página con la base ocupada y «La API sigue igual»;
  - los casos de D3 sin escenario propio: POST sobre un archivo que no existe → 405 con `Allow: GET, HEAD` y «solo se admiten GET y HEAD»; HEAD sobre un archivo que no existe → 404, comprobado solo por estado y cabeceras; `GET /api/fuels/?fuel=x` → 307 que conserva la consulta;
  - el delta de `prices-api`: `GET /precios` → 404, «La página no es JSON», «La página no está en la documentación», «HEAD en la API» y «Sin documentación en la raíz» con la web montada;
  - las cabeceras de D3 y D4 en la web, y su ausencia en `/api/docs` y en los 404, 405 y 307 de `/api/`;
  - `create_app` con `web_dir=None` → `GET /` da 404 (único test aparte sin la web);
  - en `tests/functional/test_api_format.py::test_unknown_route`, cambiar el parámetro `"/"` por `"/precios"`, según el escenario «Ruta inexistente» del delta (autorizado por el usuario). Los tests existentes de la API ya corren con la web montada, porque `make_client` usa el `web_dir` por defecto.

  Verificar que pasan con `pytest tests/functional/test_web_serving.py` y que siguen pasando todos los tests de la API.
- [x] 2.4 Docker (D12):
  - Añadir `COPY web/ /app/web/` al `Dockerfile`.
  - Actualizar los tests existentes, con la autorización del usuario: `BUILD_FILES` en `tests/docker/helpers.py` incluye `web`, y `tests/docker/test_image.py` y `tests/docker/test_build_context.py` esperan que `/app` contenga exactamente `["container", "src", "web"]`. Se mantiene la comprobación de que no entra nada más.
  - Crear `tests/docker/test_web_image.py` con el escenario «Página desde el contenedor». Usa `make_project`, con `data/` temporal vacía y un puerto libre en lugar del 8000. Comprueba que `GET /` da 200, que en `docker compose config` el único puerto publicado tiene `host_ip: 127.0.0.1`, y que la imagen contiene `index.html` y `vendor/leaflet/LICENSE`. Que sea exactamente `127.0.0.1:8000` lo sigue comprobando `tests/docker/test_api_compose.py` con `real_api_port=True`, que no cambia.

  Verificar con `pytest -m docker tests/docker/`.

## 3. Lógica pura (`web/js/logic.js`)

- [x] 3.1 Escribir `formatPrice`, `formatDistance`, `roundCoord`, `coordParam` y `normalizeLon` (D8). Probarlas con unitarios en `tests/unit/test_web_logic.py`, con los escenarios «Precios», «Distancias», «Redondeo» y «Pinchar en una copia del mundo». Verificar que pasan.
- [x] 3.2 Escribir `tiers` (D8). Probarla con los nueve escenarios de «Colores por tercios», y también con los mismos precios desordenados. Verificar que pasan.
- [x] 3.3 Escribir `captureText`, `retryAfterSeconds`, `validFuels` y `validStations` (D8). Probarlas con los escenarios de verano e invierno (en `America/New_York` y en `UTC`), fecha que no se entiende, `Retry-After` raro, elementos no válidos de `/api/fuels` y estaciones con datos que no sirven. Verificar que pasan.

## 4. Página base: mapa, teselas, atribuciones y diseño

- [x] 4.1 Adaptar a mobile first `index.html`, `styles.css` y `map.js` (D7 y D10):
  - CSS base de móvil y escritorio con `@media (min-width: 1024px)`, sin `max-width`, sin `100vh` ni `vh` sin `d`, y sin `:hover` fuera de `@media (hover: hover)`;
  - meta `viewport` con `viewport-fit=cover` y zonas seguras con `env(safe-area-inset-*)`;
  - mapa a pantalla completa en el móvil; `#panel` como hoja inferior plegable con su botón «Ver lista» y la línea de la más barata; panel lateral en escritorio;
  - `#detail` como hoja inferior en el móvil y en el panel en escritorio, sin `L.popup`;
  - la vista de España, la capa de OpenStreetMap con zoom máximo 19, y la caja de atribuciones (OpenStreetMap y Ministerio) arriba a la izquierda, con «Acercar» y «Alejar» de 44×44 px debajo;
  - encuadres con el relleno de la hoja a la vista y reencuadre al girar (D7);
  - el mecanismo de la hoja (plegar y desplegar con «Ver lista», `aria-expanded`, `max-height: 70dvh`) y de `#detail` (mostrar, ocultar y `max-height: 70dvh` con «Cerrar» fijo), con contenido de prueba; 7.1 lo llena con los resultados.

  Medir a 320×568 y a 750×342 el alto de la hoja plegada compacta (D10) antes de darla por buena.
- [x] 4.2 Ajustar los fixtures de 1.3 a los dispositivos y motores de D11 (iPhone 13 y su versión horizontal en WebKit por defecto; Pixel 7, 320×568 y escritorio en Chromium; salto con aviso si falta un motor) y escribir los tests funcionales `tests/functional/test_web_map.py` para:
  - «Sin recursos de terceros salvo las teselas», salvo «Peticiones al usar la página», que va en 7.3;
  - «Teselas de OpenStreetMap según su política de uso»: zoom 19, como mucho 40 teselas con el mismo `z`, `Referer`, y sin service worker ni Cache Storage;
  - «Atribuciones visibles», con la API caída y a 320×568 («Atribuciones con datos» y las hojas abiertas van en 7.3);
  - «Licencia de Leaflet»;
  - «Diseño mobile first», el escenario de las hojas de estilo y el diseño por tamaño de ventana sin resultados (con resultados va en 7.3);
  - «Alto de la pantalla y zonas seguras», con «En el motor de Safari» en WebKit;
  - «Sin depender de hover», el escenario de las hojas de estilo.

  «Peso de la página» va en 7.3, porque mide hasta que se ve la búsqueda. Los unitarios de fechas de 3.3 (`captureText`, `staleText`) se repiten también en WebKit (D11).

  Verificar que pasan.

- [x] 4.3 Escribir la parte de datos, sin pintar resultados (D5):
  - `api.js` completo: 15 s, secuencia, aborto de la anterior y clasificación de respuestas;
  - en `main.js`, la carga de `/api/health` y `/api/fuels` al arrancar, con `fuelsReady`;
  - la elección del combustible por defecto con `validFuels`;
  - la función que lanza la búsqueda a `/api/stations/nearby` con el punto, el combustible y el radio.

  Verificar con unitarios en `tests/unit/test_web_logic.py`, que importan `api.js` con `fetch` simulado, que cada clase de respuesta de D5 se clasifica bien con las respuestas fijas de 1.4, y que una búsqueda nueva aborta la anterior y descarta su respuesta.

## 5. Ubicación y punto de búsqueda

- [x] 5.1 Escribir en `main.js` el estado de D5, con `userClicked`, y el flujo de ubicación de D6, que lanza las búsquedas con la función de 4.3:
  - temporizador propio de 10 s y «Buscando tu ubicación…»;
  - pinchar en el mapa con las coordenadas normalizadas y redondeadas;
  - marcador del punto y círculo;
  - «Volver a mi ubicación».
  - Las coordenadas no se guardan ni van en la URL.
- [x] 5.2 Tests funcionales `tests/functional/test_web_location.py` para:
  - «Punto de búsqueda desde la ubicación del navegador»;
  - «Espera de la ubicación», salvo «Volver a una ubicación tardía fuera de España» y «Pinchar fuera de España mientras se espera», que van en 9.3;
  - «Sin ubicación del navegador», con todos sus órdenes de llegada, salvo «Pinchar y que no llegue la ubicación» y «Pinchar y que después se deniegue», que van en 7.3;
  - «Coordenadas enviadas con 3 decimales»;
  - «Ubicación y punto pinchado sin guardar».

  Usan `page.clock` y la ubicación simulada. Verificar que pasan.

## 6. Combustibles, radio y preferencias

- [x] 6.1 Escribir:
  - los selectores de combustible y radio con sus etiquetas;
  - la espera a `fuelsReady` de 4.3 antes de buscar;
  - `storage.js` con la clave y las reglas de D9: solo se guarda al cambiar un selector, y al cambiar uno se conserva lo guardado del otro.
- [x] 6.2 Tests funcionales `tests/functional/test_web_controls.py` para:
  - «Selector de combustible», incluidos los elementos no válidos, salvo «Cambiar a Hidrogeno», que va en 7.3, y «Ningún combustible con estaciones» y «Lista de combustibles que no se puede usar», que van en 9.3;
  - «Selector de radio»;
  - «Recordar la última elección»: «Volver a abrir», «Combustible guardado que ya no se vende» y «Valores guardados no válidos» («Almacenamiento bloqueado» va en 7.3);
  - el pendiente 4: con `hidrogeno` guardado y sin estaciones, se cambia solo el radio, se vuelve a abrir con Hidrogeno a la venta, y sale elegido Hidrogeno.

  Verificar que pasan y que no hay errores sin capturar en la consola.

## 7. Búsqueda, lista, colores y ficha

- [x] 7.1 Escribir en `main.js` y `view.js`, sobre la búsqueda de 4.3 y la estructura de 4.1:
  - la lista;
  - los marcadores con su precio y clase de tercio;
  - la leyenda;
  - el recuento, «Ver lista» en su fila y la línea de la más barata;
  - los avisos de descartadas y de «Hay N gasolineras en este radio…»;
  - la selección sincronizada;
  - la hoja de la lista con su contenido y su estado entre búsquedas (D10);
  - la ficha sencilla en `#detail` (hoja inferior en el móvil, panel en escritorio), con «Cerrar» y Escape (D5, D7 y D10);
  - el reencuadre del círculo después de pintar cada respuesta, con el alto de la hoja que esté a la vista (D7).
- [x] 7.2 Tests funcionales `tests/functional/test_web_search.py`. Los casos normales van contra la app con base de prueba: «Encaje con la API real», con las estaciones "1001" a "1006". Los de datos no válidos o de muchas estaciones, con las respuestas fijas de 1.4. Cubren:
  - «Peticiones a la API justas y sin respuestas viejas», salvo «Pinchar con los combustibles fallidos» y «Reintentar tras fallar los combustibles», que van en 9.3;
  - «Lista de gasolineras», salvo «Todas descartadas» y «Respuesta incompleta», que van en 9.3;
  - «Recuento de gasolineras encontradas», salvo «Sin recuento», que va en 9.3;
  - «Aviso de gasolineras descartadas» y «Aviso de más gasolineras de las mostradas», con la desaparición tras otra búsqueda válida o con `total` 0, salvo «Ninguna se puede mostrar», que va en 9.3;
  - «Marcadores con el precio en texto y leyenda», incluida la leyenda «Todas a 1,459 €/l»;
  - «Lista y mapa sincronizados» («Pulsar un marcador en el escritorio» en 1280×800);
  - «Ficha sencilla de la gasolinera», en el iPhone y en el escritorio;
  - «Hoja inferior de la lista en el móvil», incluidos «Desplegada entre búsquedas» y «Se pliega al quedarse sin lista» con `total` 0, salvo «Sin lista que mostrar» y «Se pliega al quedarse sin lista» con errores, que van en 9.3;
  - «Ficha con textos largos en horizontal», en el iPhone en horizontal;
  - «Panel lateral en el escritorio»;
  - «Mapa a pantalla completa en el móvil»;
  - «Rótulo con etiquetas».

  Los escenarios comunes se repiten en el Android.

  Verificar que pasan.

- [x] 7.3 Tests funcionales que necesitan la búsqueda de 7.1, traídos de los grupos 4 a 6, en `tests/functional/test_web_search.py`:
  - «Peticiones al usar la página», «Atribuciones con datos» y «Atribuciones en el móvil» a 320×568 con la hoja desplegada y con la ficha abierta;
  - «Pinchar en Barcelona», «Pinchar en un marcador de gasolinera», «Pinchar y que no llegue la ubicación» y «Pinchar y que después se deniegue»;
  - «Cambiar a Hidrogeno»;
  - «Almacenamiento bloqueado», con `add_init_script` que hace lanzar a `localStorage` y una búsqueda completa con ficha;
  - «Diseño mobile first» con resultados («Móvil en horizontal y tableta» y «Escritorio»);
  - «Peso de la página», en el iPhone en WebKit.

  Verificar que pasan y que no hay errores sin capturar en la consola.

## 8. Captura y salud

- [x] 8.1 Mostrar la captura de cada búsqueda con `captureText`, y el aviso de datos desactualizados a partir de la única petición a `/api/health`.
- [x] 8.2 Tests funcionales `tests/functional/test_web_capture.py` para:
  - «Captura de los precios en hora de Madrid», con el navegador en `America/New_York` y en `UTC`;
  - «Aviso de datos desactualizados», con `ok`, `desactualizada`, `configuracion_no_valida`, 503 y sin respuesta.

  Verificar que pasan.

## 9. Errores y «Reintentar»

- [x] 9.1 Escribir en `view.js` y `main.js` los mensajes de cada clase de respuesta de D5 y «Reintentar»:
  - cuenta atrás de `Retry-After` para «ocupado»;
  - tras un fallo de `/api/fuels`, ningún combustible con estaciones o `combustible_desconocido`, vuelve a pedir `/api/fuels` y después busca en el punto que haya;
  - en los demás casos, repite la búsqueda.

  Al quitar «Volver a mi ubicación» tras un 422, el foco pasa a la zona de mensajes (D10).
- [x] 9.2 Tests funcionales `tests/functional/test_web_errors.py`, con las respuestas fijas de 1.4, para:
  - «API o base ocupadas»;
  - «Sin datos en la base»;
  - «Sin gasolineras en el radio»;
  - «Punto fuera de España»: Rabat, Londres y Lisboa;
  - «API caída o respuesta inesperada»: red caída, sin respuesta en 15 s, HTML, 503 en HTML, 500, otros errores y «Reintentar» tras combustible desconocido;
  - «Mensaje de error con etiquetas».

  Verificar que pasan.
- [x] 9.3 Tests funcionales que dependen de errores y de «Reintentar», en `tests/functional/test_web_errors.py`:
  - «Volver a una ubicación tardía fuera de España» y «Pinchar fuera de España mientras se espera»;
  - «Pinchar con los combustibles fallidos» y «Reintentar tras fallar los combustibles»;
  - «Ningún combustible con estaciones», con «Reintentar», y «Lista de combustibles que no se puede usar»;
  - «Todas descartadas», «Respuesta incompleta» y «Ninguna se puede mostrar»;
  - «Sin recuento» y la desaparición de los avisos de descartadas y de «Hay N gasolineras…» tras un error;
  - el foco tras desaparecer «Volver a mi ubicación»;
  - «Sin lista que mostrar» y «Se pliega al quedarse sin lista» con un error.

  Verificar que pasan.

## 10. Accesibilidad, móvil y textos

- [x] 10.1 Completar lo que falte de 4.1 y 7.1 para la accesibilidad y el giro: la zona `aria-live`, el foco de la ficha (también desde «Más barata»), de la hoja y de «Volver a mi ubicación» (D10), y que el giro conserve la ficha y la hoja sin peticiones nuevas. Revisar que ningún texto propio de la página dice «API», tampoco los `title` y `aria-label` de Leaflet.
- [x] 10.2 Tests funcionales `tests/functional/test_web_accessibility.py` para:
  - «Accesibilidad básica», incluidos el botón de la hoja, el foco al cerrar con la hoja plegada y desplegada y desde «Más barata», y el contraste medido de los cuatro colores, normales y resaltados;
  - «Controles al alcance del pulgar», con «Excepciones», en el iPhone, el Android, el iPhone en horizontal, 320×568 y escritorio;
  - «Sin depender de hover», «Todo con toques», en el Android sin ratón;
  - «Vertical y horizontal»;
  - «Textos largos en el móvil»;
  - «Textos de la página sin la palabra API», recorriendo los estados con las respuestas fijas.

  Verificar que pasan.

## 11. Documentación

- [x] 11.1 Añadir al README la sección «Web del mapa» de D12, con la verificación opcional en el Simulador de iOS, y en «Tests» los pasos `playwright install chromium` y `playwright install webkit`. Verificar con un test en `tests/functional/`, como `test_scenarios_readme.py`, los escenarios «Lectura del README» (URL, túnel con `<IP_DEL_VPS>`, puerto 8001, internet para las teselas y nota de privacidad), «Navegadores de los tests» y «Simulador de iOS».

## 12. Comprobación de conjunto

- [x] 12.1 Ejecutar toda la batería (`pytest`, incluidos los tests `docker` y `browser`) y `openspec validate add-map-view --strict`. Verificar que:
  - todo pasa;
  - no se ha saltado ningún test `browser`, ni de WebKit ni de Chromium;
  - el escenario «Dispositivos de los tests»: la lista de tests ejecutados muestra los cinco dispositivos (iPhone 13 en vertical y en horizontal, Pixel 7, 320×568 y escritorio) y los dos motores de D11;
  - la guarda de red no ha anotado ninguna petición fuera de `127.0.0.1`.
- [ ] 12.2 Verificación manual en el Mac: `docker compose up -d` y abrir `http://127.0.0.1:8000/`, con la ubicación concedida y denegada, en el navegador de escritorio y con la vista de móvil de sus herramientas de desarrollo. La lanza el usuario, y el resultado se anota en design.md. Opcional y sin bloquear el archivo: la misma prueba en el Simulador de iOS de Xcode con los pasos del README.
- [ ] 12.3 Verificación manual en el VPS: pasar al usuario los comandos de despliegue de `docs/vps-deployment.md`, sección 13, y abrir la página por el túnel. La lanza el usuario, y el resultado se anota en el registro de `docs/vps-deployment.md`.

## Workflow follow-up

- Agente test-writer y agente code-reviewer sobre lo implementado.
- `/opsx:archive` cuando el code-reviewer dé «Listo para archivar».
- `/publish-doc`: página de funcionalidad «Mapa de gasolineras cercanas», decisiones de design.md en lenguaje llano, entrada en el Changelog y estado en «Visión del proyecto».
- Siguiente cambio: `add-station-detail` (horario y «Cómo llegar»).
