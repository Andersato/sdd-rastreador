# Proposal

## Why

La API de precios (`add-prices-api`) ya responde qué gasolineras hay cerca de
un punto y a qué precio, pero solo se puede consultar a mano con JSON. Falta
la primera interfaz: una página con un mapa en la que cualquiera vea de un
vistazo dónde está la gasolinera más barata cerca de él.

## What Changes

- Nueva página web en la raíz `/`, servida por la propia API como archivos
  estáticos (HTML + JavaScript sin paso de compilación) desde `web/`, en el
  mismo puerto 8000 y solo en `127.0.0.1` del VPS. Se usa por el túnel SSH.
- Al abrirla pide la ubicación del navegador; si se deniega, no está
  disponible o tarda, centra el mapa en España y el usuario elige el punto
  pinchando. Siempre se puede cambiar el punto pinchando, y volver a la
  ubicación con un botón.
- Las coordenadas se envían solo a la propia API, redondeadas a 3 decimales
  (unos 100 m). Ni la ubicación ni el punto pinchado se guardan en el
  navegador ni en la URL. OpenStreetMap recibe, como en cualquier mapa, las
  peticiones de las teselas de la zona que se ve.
- Selector de combustible (de `/api/fuels`, con su unidad) y de radio (5, 10,
  25 y 50 km). La última elección se recuerda en el navegador si se puede; si
  no, la página funciona igual.
- Marcadores con el precio en texto, coloreados por tercios de las
  gasolineras mostradas (el tercio más barato, el del medio y el más caro),
  con leyenda.
- Lista ordenada por precio (lateral en escritorio, debajo del mapa en el
  móvil) sincronizada con el mapa: pulsar en una resalta la otra.
- Ficha sencilla con lo que ya trae la búsqueda: rótulo, dirección,
  municipio, precio y distancia. Se cierra con un botón y con Escape. No hace
  peticiones extra.
- Fecha y hora (de Madrid) de la captura de los precios, y aviso si
  `/api/health` dice que los datos están desactualizados.
- Atribución visible al Ministerio y a OpenStreetMap; teselas de
  OpenStreetMap respetando su política de uso.
- Mensajes claros para: API o base ocupadas (503 con `Retry-After`), sin
  datos en la base, sin resultados en el radio, punto fuera de España, API
  caída o respuesta inesperada.
- Diseño adaptado al móvil (desde 320 px de ancho, sin scroll horizontal) y
  accesibilidad básica (teclado, lectores de pantalla, contraste).
- Leaflet (dependencia nueva ya aprobada) con versión fija, copiado en el
  repo con su licencia; nunca desde una CDN.
- La raíz `/` deja de responder 404: ahora sirve la página. Las rutas de
  `/api/` no cambian.
- README: cómo abrir la web por el túnel SSH.
- La imagen Docker incluye `web/`.

Este cambio no toca la base de datos ni el histórico: la página solo lee a
través de la API, que ya abre la base en solo lectura. Los tests que usan la
API real lo hacen con una base de prueba temporal, nunca con `./data`.

### Fuera de alcance

- **`add-station-detail`** (siguiente cambio): horario en la ficha (petición
  a `/api/stations/{id}`) y enlace «Cómo llegar».
- Publicar la web en internet: dominio, HTTPS, Caddy, puertos 80 y 443,
  límites de uso por cliente.
- Gráficos e histórico de precios (`add-price-stats`).
- Cuentas de usuario, favoritos, alertas, compartir enlaces a una búsqueda.
- Buscar por dirección o municipio (geocodificación).
- Cambios en las rutas de la API o en sus respuestas.
- Distinguir puntos de Portugal, Francia o Andorra que caen dentro de las
  zonas de España de la API: se tratan como España y dan 0 resultados.
- Vista inicial con Canarias, Ceuta y Melilla: muestra Península y Baleares;
  se llega a las demás moviendo el mapa.
- Agrupar marcadores que se solapan cuando hay muchos.
- Probar en navegadores distintos de Chromium.
- Funcionar sin conexión a internet (las teselas vienen de OpenStreetMap).

## Capabilities

### New Capabilities
- `map-view`: página web con el mapa de gasolineras cercanas y más baratas,
  su lista, su ficha sencilla, los avisos de datos y errores, y cómo se
  sirve y se prueba sin servicios externos.

### Modified Capabilities
- `prices-api`: la raíz `/` y las rutas fuera de `/api/` dejan de estar
  reservadas: `/` sirve la página y los archivos de la web, que son la otra
  excepción (con la documentación) al formato JSON común; una ruta que no
  existe sigue dando 404 `no_encontrado`.

## Impact

- **Código nuevo**: `web/` (HTML, CSS, JavaScript, favicon y
  `web/vendor/leaflet/` con su licencia y versión).
- **Código modificado**: `src/api/app.py` (servir `web/` en `/`),
  `Dockerfile` (copiar `web/`), `requirements-dev.txt` (Playwright),
  `pyproject.toml` (marcador `browser`), README.
- **API**: sin cambios en `/api/*`; `GET /` pasa de 404 a 200.
- **Dependencias**: Leaflet (aprobada) y `pytest-playwright` (aprobada),
  solo en `requirements-dev.txt`, nunca en la imagen: `pytest-playwright
  0.10.0`, `playwright 1.64.0`, `greenlet 3.5.6`, `pyee 14.0.0`,
  `python-slugify 9.1.3` y `text-unidecode 1.3`. `playwright install
  chromium` descarga el navegador una vez (ya hecho en el Mac).
- **Tests de Docker existentes**: `tests/docker/helpers.py` (`BUILD_FILES`),
  `tests/docker/test_image.py` y `tests/docker/test_build_context.py` pasan
  a incluir `web/` en la imagen, y siguen comprobando que no entra nada más.
  En `tests/functional/test_api_format.py::test_unknown_route` el caso `"/"`
  pasa a `"/precios"`, porque `/` ahora sirve la página. Los dos cambios
  están autorizados por el usuario.
- **Tests**: Playwright en Chromium. Los casos normales, contra la API real
  de la app con una base SQLite de prueba; los errores difíciles de provocar,
  con respuestas fijas guardadas en `tests/fixtures/`. Ubicación simulada y
  teselas bloqueadas. Unitarios de colores, orden y formato, ejecutados en el
  navegador de Playwright.
- **Servicios externos**: el navegador de quien usa la página pide teselas a
  `tile.openstreetmap.org`. Nadie más: ni CDN, ni analítica, ni la API del
  Ministerio.
- **Datos guardados**: ninguno cambia.

## Decisiones tomadas

1. Se divide: la ficha queda sencilla, con los datos de la búsqueda; horario
   y «Cómo llegar» pasan a `add-station-detail`.
2. `pytest-playwright`, solo Chromium; los unitarios de JavaScript se
   ejecutan en su navegador.
3. La ubicación se pide al abrir, con botón «Volver a mi ubicación». Si
   llega pasados los 10 s y el usuario aún no ha pinchado, se usa.
4. Coordenadas enviadas con 3 decimales, por privacidad.
5. Ni la ubicación ni el punto pinchado se guardan, tampoco en la URL.
6. `consulta_demasiado_larga` se trata como «ocupada»; los demás 503 dicen
   que no hay datos disponibles y muestran el mensaje de la API.
7. Puntos de otros países dentro de las zonas de España: se acepta que den
   0 resultados.
8. Tests mixtos: API real con base de prueba para los casos normales,
   respuestas fijas para los errores.
9. Colores por tercios de las gasolineras mostradas (por posición, no por
   tramos de precio); las que tienen el mismo precio van siempre juntas.
10. Vista inicial con Península y Baleares.
11. Se piden como mucho 100 gasolineras; por defecto, el primer combustible
    de `/api/fuels` y 10 km.
12. Se muestra `capture.downloaded_at` pasado a hora de Madrid.
13. Sin reintentos automáticos: «Reintentar» se activa al pasar los segundos
    de `Retry-After`.
14. En los colores, las del precio mínimo son siempre «más barata» y las del
    máximo siempre «más cara»; los tercios deciden el resto.
15. Mientras se espera la ubicación se ve España con «Buscando tu
    ubicación…» y ya se puede pinchar; si se pincha antes, gana el punto.
16. «Volver a mi ubicación» no aparece si la ubicación está fuera de España.
17. Otros errores JSON de la API (422, 404, 405…): «El servidor ha dado un error.
    Inténtalo más tarde.» con «Reintentar».
18. HEAD: lo admiten la página y sus archivos (`Allow: GET, HEAD`); en
    `/api/*` sigue dando 405 con `Allow: GET`.
19. Estaciones descartadas por datos incompletos: aviso propio («1 gasolinera
    no se muestra por datos incompletos.»); «Hay T gasolineras en este radio; se han pedido las N
    más baratas» solo cuando la API devuelve menos de las que hay.
20. «Reintentar» tras un 422 `combustible_desconocido` vuelve a pedir
    `/api/fuels` y después busca.
21. Leyenda: «Más barata», «Intermedia» y «Más cara», con el texto «Colores
    por tercios de las N gasolineras mostradas; el precio mínimo y el máximo
    siempre en sus extremos».
22. En los textos que ve el usuario no aparece la palabra «API»: se dice «el
    servidor». Aviso de más: «Hay 342 gasolineras en este radio; se han
    pedido las 100 más baratas.»

23. Pinchar fuera de España mientras se espera la ubicación: gana el
    pinchazo aunque diera 422; la ubicación que llegue solo hace aparecer
    «Volver a mi ubicación».
24. `GET /api/fuels/` sigue redirigiendo (307) a `/api/fuels`, como hoy.
25. Los botones de acercar y alejar del mapa miden 44 px.
26. Al cambiar solo el radio se conserva el combustible guardado.

## Pendiente para design.md

Resuelto en design.md («Pendientes resueltos»): HEAD y POST sobre archivos
inexistentes, `Allow` en la web y en `/api/`, foco al cerrar la ficha por
una búsqueda nueva y combustible por defecto tras `combustible_desconocido`.
El caso de pinchar fuera de España mientras se espera la ubicación quedó
decidido en la decisión 23.
