# Proposal

## Why

`add-map-view` dejó una ficha sencilla con lo que trae la búsqueda (rótulo,
dirección, municipio, precio y distancia). Para decidir si ir a una
gasolinera falta saber su horario, qué más vende y a qué precio, y poder
abrir la ruta hasta ella con la aplicación de mapas del móvil. La API ya
ofrece todo eso en `GET /api/stations/{id}`; solo falta usarlo en la página.

## What Changes

- Al abrir la ficha se pide `/api/stations/{id}` de esa gasolinera. Mientras
  llega, la ficha ya muestra los datos de la búsqueda y «Cargando horario…».
- **Horario** tal como lo publica el Ministerio, sin interpretarlo, partido
  en tramos (uno por línea, separando por «;») para que se lea mejor. Sin
  horario: «Horario no disponible».
- **Precios de todos sus combustibles** en la última captura, con su unidad
  («1,529 €/l»), con el combustible que se está buscando destacado (con
  texto, no solo con color) y el primero de la lista.
- Si los precios del detalle son de una captura más nueva que la de la
  búsqueda, la ficha lo dice con la fecha y hora de Madrid.
- **Peticiones justas**: como mucho una petición por gasolinera y búsqueda,
  más una por cada pulsación de «Reintentar» del detalle;
  reabrir la misma ficha reutiliza la respuesta (o la que está en camino).
  Si se abre otra ficha antes de que llegue, la respuesta anterior se guarda
  para esa gasolinera pero nunca se muestra en la ficha nueva. Una búsqueda
  nueva olvida todo lo pedido. Límite de 15 s por petición.
- **Errores solo del detalle**: si la petición falla o tarda, la ficha sigue
  con los datos de la búsqueda y muestra, en la zona del horario, el mismo
  mensaje que daría el resto de la página («El servidor está ocupado…»,
  «No se puede conectar con el servidor…», etc.) con su «Reintentar», que
  solo vuelve a pedir el detalle. Sin la palabra «API». Sin reintentos
  automáticos.
- **«Cómo llegar»**: un enlace normal (sin clave ni cuenta) que abre la ruta
  hasta la gasolinera en la aplicación de mapas del dispositivo: Apple Maps
  en iPhone, iPad y Mac; Google Maps en Android; OpenStreetMap en el resto.
  Solo lleva las coordenadas de la gasolinera (dato público), nunca la
  ubicación de quien busca ni el punto pinchado, y no envía la dirección de
  la página (`rel="noopener noreferrer"`). Está disponible desde que se abre
  la ficha, aunque el detalle falle, porque usa las coordenadas de la
  búsqueda.
- **Mobile first**, como el resto: la ficha sigue siendo la hoja inferior del
  móvil (como mucho el 70 % del alto, con su contenido desplazable) y el
  panel lateral en escritorio. «Cómo llegar» y «Cerrar» van juntos en la
  fila de acciones fija abajo de la ficha, al alcance del pulgar y siempre a
  la vista; los dos y el «Reintentar» del detalle miden al menos 44×44 px.
  Horarios y nombres largos se parten sin scroll horizontal, en vertical y
  en horizontal, de 320 px al escritorio. Nada depende de hover.
- **Presupuesto de peso**: se mantiene en 300 KB (sin teselas ni respuestas
  de `/api/`), con el requisito «Peso de la página» de `map-view`; el cambio
  añade solo unos pocos KB de JavaScript y CSS, sin imágenes ni fuentes.
- README: la sección de privacidad explica qué envía «Cómo llegar» y que la
  aplicación de mapas puede usar su propia ubicación para calcular la ruta.

Este cambio no toca la API ni la base de datos: solo lee
`/api/stations/{id}`, que ya existe. El histórico no se ve afectado.

### Fuera de alcance

- «¿Abierta ahora?» y traducir abreviaturas del horario («L-D» → «de lunes
  a domingo»). Los datos de origen son ambiguos: en la copia del 18/10/2026,
  «L: 24H» aparece en unas 370 estaciones y parece un fallo de origen, pero
  en «L: 06:30-22:30; M-D: …» «L» es de verdad el lunes. (Para «Qué no hace
  todavía».)
- Favoritos y compartir la gasolinera.
- Arrastrar la hoja con el dedo (sigue con su botón).
- Publicar la web en internet.
- Gráficos o histórico de precios de la gasolinera.
- Cambios en la API o en sus respuestas.
- Elegir la aplicación de mapas a mano o usar el esquema `geo:`.
- Pasar a la aplicación de mapas el origen de la ruta: lo pone ella.

## Capabilities

### New Capabilities
- `station-detail`: ficha completa de una gasolinera en la página del mapa:
  carga del detalle (horario y precios de todos sus combustibles), sus
  peticiones y errores, y el enlace «Cómo llegar» a la aplicación de mapas
  del dispositivo.

### Modified Capabilities
- `map-view`: la ficha deja de ser «sin peticiones» (ahora pide el detalle);
  el recuento de peticiones de «Peticiones a la API justas» y de pulsar un
  marcador pasa a incluir `/api/stations/{id}`; «Cómo llegar» se añade a los
  objetivos táctiles y a lo que puede salir hacia otro origen (solo al
  pulsarlo); los tests comprueban que no se abre ninguna aplicación de mapas
  real; el README amplía la privacidad.

## Impact

- **Código modificado**: `web/index.html` (zona de detalle y «Cómo llegar»
  en la ficha), `web/js/` (petición del detalle con su caché por búsqueda,
  formato del horario, lista de precios, enlace según el dispositivo),
  `web/styles.css`, README.
- **API**: sin cambios; se usa `GET /api/stations/{id}` tal como está.
- **Dependencias**: ninguna nueva.
- **Tests**: Playwright con la API simulada (respuestas fijas en
  `tests/fixtures/web/`) en los cinco dispositivos de `map-view`: iPhone 13
  en WebKit en vertical (390×664) y en horizontal (750×342), Pixel 7 en
  Chromium (412×839), 320×568 táctil en Chromium y escritorio en Chromium
  (1280×800), con agente de usuario fijado en cada test para que no dependa
  del equipo. Las navegaciones a Apple Maps, Google Maps y OpenStreetMap se
  interceptan y se cancelan: solo se comprueba el enlace generado.
  Unitarios del formato del horario y del enlace en el navegador de
  Playwright.
- **Servicios externos**: ninguno nuevo que pida la página por su cuenta;
  solo si el usuario pulsa «Cómo llegar», su navegador abre Apple Maps,
  Google Maps u OpenStreetMap.
- **Datos guardados**: ninguno cambia.

## Decisiones tomadas

1. **Confirmada con datos reales** (copia del 18/10/2026): el horario solo
   se parte por «;» (un tramo por línea, sin espacios sobrantes ni tramos
   vacíos). Siempre tiene la forma «días: horas»; « y » separa dos franjas
   del mismo día y no parte el tramo. No se traducen abreviaturas ni se
   reordena nada.
2. El combustible buscado va el primero en la lista de precios, con el texto
   «Buscado»; los demás, en el orden del servidor (por `slug`).
3. La ficha mantiene rótulo, dirección, municipio, precio y distancia de la
   búsqueda; del detalle solo se añaden horario y precios.
4. Si se abre otra ficha antes de que llegue la respuesta, la petición
   anterior no se cancela: su respuesta se guarda para esa gasolinera (no se
   muestra en la nueva). Así reabrirla no hace otra petición.
5. Un detalle fallido también se recuerda: reabrir esa ficha muestra el
   error con «Reintentar» sin pedir nada; solo «Reintentar» pide otra vez.
6. Errores del detalle con los mismos textos y criterios que `map-view`
   (incluido `Retry-After` en los 503 de ocupado); un 404
   `estacion_no_encontrada` cuenta como «El servidor ha dado un error.
   Inténtalo más tarde.».
7. Enlaces: `https://maps.apple.com/?daddr=LAT,LON`,
   `https://www.google.com/maps/dir/?api=1&destination=LAT,LON` y
   `https://www.openstreetmap.org/directions?route=%3BLAT%2CLON`, con las
   coordenadas de la búsqueda, cada número en su escritura más corta
   (40.4400 → 40.44), en otra pestaña.
8. Dispositivo por el agente de usuario: «Android» → Google Maps; si no,
   «iPhone», «iPad», «iPod» o «Macintosh» (el iPad moderno se presenta como
   Mac) → Apple Maps; el resto → OpenStreetMap.
9. Tests solo con la API simulada (respuestas fijas), como pide el cambio,
   aunque `map-view` usa la API real para sus casos normales; se mantiene un
   test de encaje con la API real para `/api/stations/{id}`.
10. Aviso de captura solo si la del detalle es posterior a la de la
    búsqueda y las dos fechas se entienden.
11. Si `prices` trae elementos pero ninguno es válido: respuesta inesperada
    con «Reintentar», sin avisar de descartados (`prices` vacía sigue
    diciendo «No hay precios…»).
12. Identificador: `data.id` debe ser texto e igual al pedido; si no,
    respuesta inesperada. Una gasolinera de la búsqueda con `id` `""` o
    numérico no pide nada y muestra respuesta inesperada sin «Reintentar»
    (las que no tienen `id` ya las descarta la lista de `map-view`).
13. Foco: la ficha no atrapa el foco; orden «Reintentar» → «Cerrar» →
    «Cómo llegar»; tras «Reintentar» del detalle, el foco va a la zona de
    estado del detalle.
14. Lectores de pantalla: solo se anuncia un estado corto («Cargando
    horario…», «Ficha cargada» o el error), también al reabrir una
    ficha ya cargada: «Ficha cargada» es cierto aunque no haya horario ni
    precios.
15. «Cómo llegar» nombra el destino para los lectores («Cómo llegar con
    Apple Maps (se abre en otra pestaña)», etc.); el texto visible es solo
    «Cómo llegar».
16. Al reabrir una ficha con «Reintentar» esperando un `Retry-After`, la
    cuenta sigue desde el error original.
17. 404 `estacion_no_encontrada`: texto genérico con «Reintentar» (decisión 6).
18. Si el detalle es de una captura más nueva, el precio de arriba (de la
    búsqueda) y el de «Buscado» (del detalle) pueden diferir; lo explica el
    aviso de captura.
19. El requisito «Ficha sencilla de la gasolinera» de `map-view` pasa a
    llamarse «Ficha de la gasolinera».
20. «Buscado» va en el contenido visible y en el texto que leen los
    lectores de pantalla; se comprueba con el árbol de accesibilidad, sin
    `aria-label` que repita el texto.
21. Si el iPhone emulado en WebKit no abre la pestaña al pulsar «Cómo
    llegar», la pulsación con la dirección de Apple Maps se comprueba en
    escritorio con un agente de usuario de Mac; en el iPhone, solo los
    atributos del enlace.
22. El usuario autoriza modificar ocho tests de `map-view` cuyos escenarios
    cambian con este cambio: `test_open_and_see_details`,
    `test_full_detail`, `test_tap_on_a_station_marker` y
    `test_requests_while_using_the_page` (`test_web_search.py`);
    `test_touch_targets` con su función de apoyo,
    `test_no_api_word_in_page_texts` y `test_rotate_with_detail_open`
    (`test_web_accessibility.py`); y `test_ios_simulator`
    (`test_web_readme.py`).
23. El plan B de la decisión 21 vale también para el escenario «Pulsar
    «Cómo llegar»» de `map-view`.
24. «Se olvidan los detalles al lanzarse la búsqueda de la ubicación» se
    prueba con «Volver a mi ubicación»: con el código actual, la ubicación
    solo busca sola si aún no se ha pinchado, y entonces no hay ficha
    abierta.

## Pendiente para design.md

Resuelto en design.md: encuadre del marcador al crecer la ficha (D10), fila
de acciones visible en el panel de escritorio (D9), criterio de «fecha
válida» (D4) y zona de estado del detalle que recibe el foco (D8).
