# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Ficha sencilla de la gasolinera`
- TO: `### Requirement: Ficha de la gasolinera`

## MODIFIED Requirements

### Requirement: Sin recursos de terceros salvo las teselas
La página SHALL cargar todos sus scripts, estilos, iconos y fuentes desde
su propio origen, con Leaflet en una versión fija incluida en el repo junto
a su licencia. Las únicas peticiones a otro origen MUST ser las teselas de
`https://tile.openstreetmap.org/`. No hay analítica, CDN ni fuentes externas.
La única excepción es la navegación a la aplicación de mapas que abre el
enlace «Cómo llegar» de `station-detail`, solo cuando se pulsa.

#### Scenario: Peticiones al usar la página
- **WHEN** se abre la página con la ubicación concedida en (40.416775, -3.703790), se hace la búsqueda y se pulsa la gasolinera "1003" (40.4400, -3.7300), sin pulsar «Cómo llegar», registrando todas las peticiones del navegador
- **THEN** cada petición va al origen de la página o a `https://tile.openstreetmap.org/{z}/{x}/{y}.png`

#### Scenario: Pulsar «Cómo llegar»
- **WHEN** en el escenario anterior se pulsa «Cómo llegar» en la ficha de "1003", con la navegación interceptada y cancelada por el test
- **THEN** la única petición nueva a otro origen es la navegación de una pestaña nueva a la dirección del enlace (`maps.apple.com`, `www.google.com/maps` o `www.openstreetmap.org/directions`), y la página del mapa no pide nada más

Nota de verificación: como en el escenario «Pulsar «Cómo llegar»» de
`station-detail`, si el iPhone emulado en WebKit no abre la pestaña nueva al
pulsar, en el iPhone se comprueban solo los atributos del enlace y la
pulsación se comprueba en escritorio en Chromium con un agente de usuario de
Safari en Mac.

#### Scenario: Licencia de Leaflet
- **WHEN** se revisa la carpeta de Leaflet en `web/`
- **THEN** contiene su archivo de licencia y un archivo que indica la versión exacta incluida, y la página no usa otra copia de Leaflet

### Requirement: Cambiar el punto pinchando en el mapa
Pinchar en el mapa SHALL mover el punto de búsqueda allí y buscar de nuevo
con el combustible y el radio elegidos, haya o no ubicación del navegador.
Pinchar en un marcador de gasolinera no cambia el punto.

#### Scenario: Pinchar en Barcelona
- **WHEN** la búsqueda está en Madrid y se pincha en (41.3874, 2.1686)
- **THEN** el marcador del punto y el círculo pasan a Barcelona, se pide `/api/stations/nearby` con `lat=41.387&lon=2.169` y la lista y los marcadores muestran solo las gasolineras de esa respuesta

#### Scenario: Pinchar en un marcador de gasolinera
- **WHEN** se pulsa el marcador de la gasolinera "4375"
- **THEN** se abre su ficha, el punto de búsqueda no cambia, no se pide `/api/stations/nearby` y la única petición es la del detalle de `station-detail` (`/api/stations/4375`), si aún no se tenía

### Requirement: Peticiones a la API justas y sin respuestas viejas
La página SHALL pedir `/api/health` y `/api/fuels` una vez al abrirse, y
cada acción (ubicación, pinchar, cambiar combustible o radio, «Volver a mi
ubicación», «Reintentar») hace como mucho una petición a cada ruta que
necesita, con `limit=100`. Abrir una ficha pide como mucho su detalle, según
`station-detail`. MUST NOT repetir peticiones por su cuenta y solo muestra
la respuesta de la última acción.

#### Scenario: Página quieta
- **WHEN** la página muestra resultados y no se toca durante 5 minutos
- **THEN** no se hace ninguna petición a `/api/` en ese tiempo

#### Scenario: Abrir y ver la ficha
- **WHEN** se abre la página con ubicación concedida, se buscan cercanas y se abren las fichas de tres gasolineras
- **THEN** en total se ha pedido una vez `/api/health`, una vez `/api/fuels`, una vez `/api/stations/nearby` y una vez el `/api/stations/{id}` de cada una de esas tres gasolineras

#### Scenario: Dos pinchazos seguidos
- **WHEN** se pincha en Madrid, la respuesta tarda 2 s, y antes de que llegue se pincha en Barcelona, cuya respuesta llega enseguida
- **THEN** al final se ven solo las gasolineras de Barcelona, aunque la respuesta de Madrid llegue después

#### Scenario: Ubicación antes que los combustibles
- **WHEN** `/api/fuels` tarda 2 s en responder y el navegador concede la ubicación enseguida
- **THEN** la página espera a los combustibles y pide `/api/stations/nearby` una sola vez, después de recibirlos, con el combustible elegido según ellos

#### Scenario: Pinchar antes que los combustibles
- **WHEN** `/api/fuels` tarda 2 s en responder y se pincha en (41.3874, 2.1686) al primer segundo
- **THEN** el punto queda marcado y se pide `/api/stations/nearby` una sola vez, después de recibir los combustibles

#### Scenario: Pinchar con los combustibles fallidos
- **WHEN** `/api/fuels` falló al abrir y se pincha en (41.3874, 2.1686)
- **THEN** el punto queda marcado, no se hace ninguna petición, y al pulsar «Reintentar» se pide una vez `/api/fuels` y, si responde bien, una vez `/api/stations/nearby` con `lat=41.387&lon=2.169`

#### Scenario: Reintentar tras fallar los combustibles
- **WHEN** `/api/fuels` falló al abrir con la ubicación ya concedida, y al pulsar «Reintentar» responde 200
- **THEN** se pide una vez `/api/fuels` y, después, una vez `/api/stations/nearby` en esa ubicación

### Requirement: Ficha de la gasolinera
La ficha SHALL mostrar rótulo, dirección, municipio, precio y distancia de la
respuesta de cercanas en cuanto se abre, sin esperar a ninguna petición;
horario, precios y «Cómo llegar» se añaden según `station-detail`. En el móvil es una hoja inferior
en el sitio de la de la lista, nunca un globo sobre el mapa, de como mucho el
70 % del alto, con «Cerrar» siempre a la vista; en el escritorio, va en el
panel lateral. Se cierra con «Cerrar» o Escape, sin dejar ninguna resaltada.

#### Scenario: Ficha completa
- **WHEN** se pulsa "4375" (REPSOL, CALLE MAYOR, 1, Madrid) con Gasoleo A a 1.459 a 0.04 km
- **THEN** la ficha muestra enseguida «REPSOL», «CALLE MAYOR, 1», «Madrid», «1,459 €/l» y «0,0 km», aunque el detalle de `/api/stations/4375` aún no haya llegado o falle

#### Scenario: Ficha en una hoja inferior en el móvil
- **WHEN** en un iPhone (390×664) se toca el marcador de "4375"
- **THEN** la ficha aparece pegada al borde inferior de la pantalla, a todo el ancho, en lugar de la hoja de la lista; no hay ningún globo sobre el mapa, y el marcador de "4375" queda en la zona visible del mapa, por encima de la ficha

#### Scenario: Ficha con textos largos en horizontal
- **WHEN** en un iPhone en horizontal (750×342) se abre la ficha de una gasolinera con un rótulo de 80 caracteres y una dirección de 120
- **THEN** la ficha mide como mucho el 70 % del alto de la ventana, su contenido se desplaza dentro de ella si no cabe y «Cerrar» se ve entero sin desplazar nada

#### Scenario: Ficha en el panel lateral en el escritorio
- **WHEN** en una ventana de 1280×800 se pulsa "4375"
- **THEN** la ficha aparece en el panel lateral, encima de la lista, y no hay ningún globo sobre el mapa

#### Scenario: Datos vacíos
- **WHEN** se pulsa una gasolinera con `brand`, `address` y `municipality` `null`
- **THEN** la ficha muestra «Sin rótulo», «Dirección no disponible» y «Municipio no disponible»

#### Scenario: Cerrar con el botón
- **WHEN** la ficha de "1001" está abierta y se pulsa «Cerrar»
- **THEN** la ficha se cierra, ni la fila ni el marcador de "1001" quedan resaltados, la búsqueda no cambia y, en el móvil, vuelve la hoja de la lista plegada o desplegada como estaba

#### Scenario: Cerrar con Escape
- **WHEN** la ficha de "1001" está abierta y se pulsa Escape
- **THEN** pasa lo mismo que con «Cerrar»

### Requirement: Controles al alcance del pulgar
En el móvil, combustible, radio y «Volver a mi ubicación» SHALL estar en la
hoja inferior, en la mitad inferior de la pantalla, visibles con la hoja
plegada. Selectores, botones (también los de zoom), enlaces de acción como
«Cómo llegar» y filas de la lista miden al menos 44×44 px en móvil y escritorio. Solo quedan fuera los marcadores de
precio, cuya vía accesible es la lista, y los enlaces dentro de un texto.

#### Scenario: Controles en vertical
- **WHEN** en un iPhone (390×664) y en un Android (412×839) la página muestra resultados y la ubicación concedida
- **THEN** los selectores de combustible y radio y «Volver a mi ubicación» se ven enteros por debajo de la mitad de la pantalla

#### Scenario: Controles en horizontal
- **WHEN** en un iPhone en horizontal (750×342) la página muestra resultados
- **THEN** esos tres controles se ven enteros por debajo de la mitad de la pantalla

#### Scenario: Objetivos táctiles
- **WHEN** se miden en una ventana de 320×568, con la hoja plegada, desplegada y con una ficha abierta, y en una de 1280×800, con y sin ficha
- **THEN** los selectores, los botones que se ven en cada caso («Ver lista», «Ocultar lista», «Cerrar», «Cómo llegar», «Reintentar», también el del detalle de la ficha, la más barata, «Volver a mi ubicación», «Acercar» y «Alejar») y cada fila de la lista miden al menos 44 px de alto y 44 px de ancho

#### Scenario: Excepciones
- **WHEN** se miden los marcadores de precio y el enlace «OpenStreetMap contributors»
- **THEN** no se les exige 44 px, y cada gasolinera de un marcador tiene su fila en la lista, que sí los mide

### Requirement: Pruebas sin servicios externos
Los tests de la página SHALL ejecutarse sobre todo con emulación móvil
táctil: el iPhone en WebKit (el motor de Safari) y el Android en Chromium, y
al menos una parte en escritorio en Chromium, con la ubicación simulada y
las teselas sustituidas por una imagen local. Los casos normales usan la API
real con una base de prueba temporal; los errores, respuestas fijas de
`tests/fixtures/`; el detalle de la ficha, respuestas fijas salvo un test de
encaje. MUST NOT salir ninguna petición del equipo ni abrirse ninguna
aplicación de mapas: la navegación de «Cómo llegar» se intercepta y se cancela.

#### Scenario: Ejecución de los tests
- **WHEN** se ejecutan todos los tests de la página registrando las peticiones del navegador
- **THEN** ninguna petición llega a OpenStreetMap, a la API del Ministerio, a la API del VPS, a Apple Maps ni a Google Maps, y un test falla si la página lo intenta; los tests que pulsan «Cómo llegar» solo registran la dirección a la que se intenta navegar y la cancelan

#### Scenario: Encaje del detalle con la API real
- **WHEN** se ejecuta un test que abre la ficha de "4375" contra la app con una base de prueba con la estación "4375" del escenario «Estación con precios» de `prices-api`
- **THEN** la ficha muestra «L-D: 24H», «Gasoleo A · 1,459 €/l» y «Gasolina 95 E5 · 1,529 €/l», y `./data` no se usa

#### Scenario: Dispositivos del detalle
- **WHEN** se revisan los tests de `station-detail`
- **THEN** el conjunto cubre los cinco dispositivos (iPhone 13 en WebKit a 390×664 y a 750×342, Pixel 7 en Chromium, 320×568 táctil en Chromium y escritorio en Chromium a 1280×800), cada uno con su agente de usuario fijado en el test; cada escenario se ejecuta en el dispositivo que indica y, si no indica ninguno, según «Dispositivos de los tests»

#### Scenario: Dispositivos de los tests
- **WHEN** se revisan los tests de la página
- **THEN** por defecto se ejecutan con el iPhone 13 de Playwright en WebKit (390×664, táctil, móvil); los de horizontal, a 750×342 en WebKit; los de comportamiento común se repiten con el Pixel 7 en Chromium (412×839, táctil, móvil); los de tamaño mínimo, a 320×568 táctil en Chromium; y los de panel lateral, teclado y desplazamiento de la lista, en escritorio en Chromium (1280×800)

#### Scenario: Encaje con la API real
- **WHEN** se ejecuta el test de búsqueda en Madrid contra la app con una base de prueba con las estaciones "1001" a "1006" del escenario «Búsqueda en Madrid» de `prices-api`
- **THEN** la página muestra las gasolineras que da esa API, en su orden, y `./data` no se usa

### Requirement: Cómo abrir la web en el README
El README SHALL explicar cómo abrir la página en el Mac y por el túnel SSH
desde el VPS, qué hacer si el puerto 8000 del Mac ya está ocupado, que las
teselas necesitan internet, a quién llega la ubicación, cómo instalar los
navegadores de los tests y, como verificación opcional, cómo probarla en el
Simulador de iOS de Xcode. También SHALL explicar qué envía «Cómo llegar».

#### Scenario: Lectura del README
- **WHEN** se lee la sección de la web del README
- **THEN** incluye `http://127.0.0.1:8000/`, el comando del túnel con `<IP_DEL_VPS>`, cómo usar otro puerto local (por ejemplo 8001) si el 8000 está ocupado por la API del Mac, que el mapa necesita internet para las teselas de OpenStreetMap, y que la ubicación y el punto pinchado solo se envían a la propia API, redondeados a unos 100 m, y no se guardan, mientras que OpenStreetMap recibe las peticiones de las teselas de la zona que se ve

#### Scenario: Privacidad de «Cómo llegar»
- **WHEN** se lee la sección de privacidad del README
- **THEN** dice que «Cómo llegar» abre Apple Maps, Google Maps u OpenStreetMap según el dispositivo, que solo les envía las coordenadas de la gasolinera (un dato público) y nunca la ubicación de quien busca ni el punto pinchado, que solo ocurre al pulsarlo, y que esa aplicación puede usar su propia ubicación para calcular la ruta, según su política de privacidad

#### Scenario: Navegadores de los tests
- **WHEN** se lee la sección de tests del README
- **THEN** incluye `.venv/bin/playwright install chromium` y `.venv/bin/playwright install webkit`

#### Scenario: Simulador de iOS
- **WHEN** se lee la sección de la web del README
- **THEN** explica, como verificación opcional que no bloquea nada, cómo abrir el Simulador de iOS de Xcode, abrir Safari en él con `http://127.0.0.1:8000/` (el Simulador llega a `127.0.0.1` del Mac y, por él, al túnel), darle una ubicación simulada (Features → Location) y qué comprobar: la hoja inferior, la ficha con horario, precios y «Cómo llegar» (que abre Apple Maps), los controles abajo y que la muesca y la barra inferior no tapan nada, en vertical y en horizontal
