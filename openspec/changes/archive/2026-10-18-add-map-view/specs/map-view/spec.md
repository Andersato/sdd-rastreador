# Spec Delta

## Purpose

Ofrecer una página web con un mapa para encontrar las gasolineras más
baratas cerca de un punto, a partir de la API de precios, sin guardar la
ubicación de quien la usa y sin depender de más servicios externos que las
teselas de OpenStreetMap.

## ADDED Requirements

### Requirement: Página servida en la raíz
La API SHALL servir la página en `GET /` y sus archivos (HTML, CSS,
JavaScript, favicon y Leaflet) desde la carpeta `web/`, en el mismo puerto
que la API. Servir la página MUST NOT abrir la base. Una ruta que no es de
`/api/` ni un archivo de `web/` da 404 `no_encontrado`, y nunca se sirve nada
de fuera de `web/` ni listados de carpetas. La página y sus archivos admiten
GET y HEAD.

#### Scenario: Abrir la página
- **WHEN** se pide `GET /`
- **THEN** la respuesta es 200 con `Content-Type` `text/html; charset=utf-8`, una página con `lang="es"` y el título «Gasolineras baratas cerca»

#### Scenario: HEAD de la página
- **WHEN** se pide `HEAD /`
- **THEN** la respuesta es 200 con el mismo `Content-Type` que `GET /` y sin cuerpo

#### Scenario: Favicon
- **WHEN** se pide `GET /favicon.ico`
- **THEN** la respuesta es 200 con una imagen

#### Scenario: Página sin base
- **WHEN** `./data` está vacía y se pide `GET /`
- **THEN** la respuesta es 200 con la página, y `GET /api/fuels` sigue respondiendo 503 `sin_base`

#### Scenario: Página con la base ocupada
- **WHEN** otro proceso mantiene la base con un bloqueo exclusivo de escritura y se pide `GET /`
- **THEN** la respuesta es 200 enseguida, sin esperar a la base

#### Scenario: Barra final en una ruta de la API
- **WHEN** la página se sirve en `/` y se pide `GET /api/fuels/`
- **THEN** la respuesta es la misma que antes de este cambio: una redirección 307 a `/api/fuels`

#### Scenario: Archivo inexistente
- **WHEN** se pide `GET /no-existe.js`
- **THEN** la respuesta es 404 JSON con el código `no_encontrado` y la atribución

#### Scenario: Carpeta
- **WHEN** se pide `GET /vendor/leaflet/`
- **THEN** la respuesta es 404 `no_encontrado`, sin ningún listado de archivos

#### Scenario: Intento de salir de web/
- **WHEN** se pide `GET /..%2Fsrc%2Fapi%2Fapp.py` o `GET /%2e%2e/requirements.txt`
- **THEN** la respuesta es 404 `no_encontrado` y no contiene nada de esos archivos

#### Scenario: Otro método en la página
- **WHEN** se pide `POST /`
- **THEN** la respuesta es 405 `metodo_no_permitido` con `Allow: GET, HEAD`

#### Scenario: HEAD en la API
- **WHEN** la página se sirve en `/` y se pide `HEAD /api/fuels`
- **THEN** la respuesta es 405 `metodo_no_permitido` con `Allow: GET`, como antes de este cambio

#### Scenario: La API sigue igual
- **WHEN** la página se sirve en `/` y se pide `GET /api/fuels`
- **THEN** la respuesta es la misma que sin la página, y `GET /api/openapi.json` sigue describiendo exactamente las cinco rutas de `/api/`

### Requirement: Sin recursos de terceros salvo las teselas
La página SHALL cargar todos sus scripts, estilos, iconos y fuentes desde
su propio origen, con Leaflet en una versión fija incluida en el repo junto
a su licencia. Las únicas peticiones a otro origen MUST ser las teselas de
`https://tile.openstreetmap.org/`. No hay analítica, CDN ni fuentes externas.

#### Scenario: Peticiones al usar la página
- **WHEN** se abre la página con la ubicación concedida en (40.416775, -3.703790), se hace la búsqueda y se pulsa una gasolinera, registrando todas las peticiones del navegador
- **THEN** cada petición va al origen de la página o a `https://tile.openstreetmap.org/{z}/{x}/{y}.png`

#### Scenario: Licencia de Leaflet
- **WHEN** se revisa la carpeta de Leaflet en `web/`
- **THEN** contiene su archivo de licencia y un archivo que indica la versión exacta incluida, y la página no usa otra copia de Leaflet

### Requirement: Teselas de OpenStreetMap según su política de uso
El mapa SHALL usar las teselas estándar de OpenStreetMap
(`https://tile.openstreetmap.org/{z}/{x}/{y}.png`) con zoom máximo 19,
pidiendo solo las de la zona que se ve, sin guardarlas aparte de la caché
normal del navegador (ni service workers ni Cache Storage) y enviando la
cabecera `Referer` con el origen de la página.

#### Scenario: Zoom máximo
- **WHEN** se acerca el mapa todo lo posible
- **THEN** el zoom se queda en 19 y no se pide ninguna tesela con `z` mayor que 19

#### Scenario: Solo lo que se ve
- **WHEN** se abre la página en una ventana de 1280×800 sin ubicación y se espera a que el mapa termine de cargar
- **THEN** todas las teselas pedidas tienen el mismo `z` y son como mucho 40

#### Scenario: Referer de las teselas
- **WHEN** se abre la página en `http://127.0.0.1:<puerto>/` y el mapa pide teselas
- **THEN** cada petición de tesela lleva `Referer` con `http://127.0.0.1:<puerto>/`, y la página no declara `Referrer-Policy: no-referrer` ni equivalente

#### Scenario: Sin almacén propio de teselas
- **WHEN** se ha usado la página y se revisa su origen en el navegador
- **THEN** no tiene ningún service worker registrado ni nada en Cache Storage

### Requirement: Atribuciones visibles
La página SHALL mostrar siempre, sin desplegar nada y sin que las tapen las
hojas inferiores, el texto «Ministerio de Industria, Comercio y Turismo -
Precios de carburantes en estaciones de servicio» y «© OpenStreetMap
contributors» con un enlace a `https://www.openstreetmap.org/copyright`,
también si la API falla.

#### Scenario: Atribuciones con datos
- **WHEN** se abre la página en un iPhone (390×664) y la búsqueda muestra gasolineras
- **THEN** se ven el texto exacto del Ministerio y «© OpenStreetMap contributors» enlazado a `https://www.openstreetmap.org/copyright`

#### Scenario: Atribuciones con la API caída
- **WHEN** la API no responde y se abre la página
- **THEN** las dos atribuciones siguen visibles

#### Scenario: Atribuciones en el móvil
- **WHEN** se abre la página en una ventana de 320×568, con la hoja de la lista desplegada o con una ficha abierta
- **THEN** las dos atribuciones se ven enteras, sin cortarse ni tapar los controles del mapa, y ninguna hoja las tapa

### Requirement: Coordenadas enviadas con 3 decimales
La página SHALL enviar a la API la latitud y la longitud del punto de
búsqueda redondeadas y escritas con 3 decimales (unos 100 m), con la longitud llevada al
intervalo de -180 a 180 si el mapa da otra. El marcador del punto y el
círculo se dibujan en ese punto redondeado.

#### Scenario: Redondeo
- **WHEN** el punto de búsqueda es (40.416775, -3.703790)
- **THEN** la petición lleva `lat=40.417&lon=-3.704`

#### Scenario: Pinchar en una copia del mundo
- **WHEN** se pincha en un punto que el mapa da como (40.0, 357.6), a la derecha de la copia principal del mundo
- **THEN** la petición lleva `lat=40.000&lon=-2.400` y no hay error de parámetro no válido

### Requirement: Ubicación y punto pinchado sin guardar
La página MUST NOT guardar la ubicación del navegador ni el punto pinchado
en `localStorage`, `sessionStorage`, cookies, IndexedDB ni en la URL. Sus
coordenadas solo se envían a la propia API; OpenStreetMap recibe, como en
cualquier mapa, las peticiones de las teselas de la zona que se ve.

#### Scenario: Nada guardado
- **WHEN** se ha buscado desde la ubicación (40.416775, -3.703790) y después pinchando en (41.3874, 2.1686)
- **THEN** ni `40.41`, ni `-3.70`, ni `41.38`, ni `2.16` aparecen en ningún valor de `localStorage`, `sessionStorage`, cookies o IndexedDB de la página, ni en su URL (ruta, parámetros o `#`)

#### Scenario: Solo a la propia API
- **WHEN** se registran todas las peticiones del escenario anterior
- **THEN** las coordenadas del punto solo aparecen en peticiones a `/api/stations/nearby` del origen de la página; a OpenStreetMap solo llegan peticiones de teselas `{z}/{x}/{y}.png`

### Requirement: Punto de búsqueda desde la ubicación del navegador
Al abrirse, la página SHALL pedir la ubicación al navegador. Si la concede
y aún no se ha pinchado un punto, usa ese punto: lo marca, dibuja el círculo
del radio, encuadra el círculo entero y busca. Desde entonces muestra un botón «Volver a mi ubicación»
que vuelve a buscar en esa ubicación, salvo si esa ubicación dio
`fuera_de_espana`.

#### Scenario: Ubicación concedida en Madrid
- **WHEN** el navegador concede la ubicación (40.416775, -3.703790), el combustible elegido es Gasoleo A y el radio 10 km
- **THEN** la página pide `GET /api/stations/nearby?lat=40.417&lon=-3.704&fuel=gasoleo-a&radius_km=10&limit=100` una sola vez, marca ese punto y el círculo de 10 km se ve entero en el mapa

#### Scenario: Volver a mi ubicación
- **WHEN** se buscó desde la ubicación en Madrid, después se pinchó en Barcelona y se pulsa «Volver a mi ubicación»
- **THEN** se busca de nuevo con `lat=40.417&lon=-3.704` y el círculo vuelve a Madrid

#### Scenario: Sin ubicación no hay botón
- **WHEN** el navegador deniega la ubicación
- **THEN** no se ve el botón «Volver a mi ubicación»

### Requirement: Espera de la ubicación
Mientras espera la ubicación, la página SHALL mostrar España peninsular y
Baleares con el texto «Buscando tu ubicación…» y dejar pinchar en el mapa.
Si se pincha antes de que llegue, gana el punto pinchado y la ubicación que
llegue después solo hace aparecer «Volver a mi ubicación». El texto se
quita al conceder, denegar o agotarse el tiempo.

#### Scenario: Mientras se espera
- **WHEN** se abre la página y el navegador aún no ha respondido a la petición de ubicación
- **THEN** se ven la Península y Baleares con «Buscando tu ubicación…» y no se ha pedido `/api/stations/nearby`

#### Scenario: Pinchar mientras se espera
- **WHEN** a los 3 s de abrir la página, sin ubicación aún, se pincha en (41.3874, 2.1686) y a los 5 s el navegador entrega (40.416775, -3.703790)
- **THEN** se busca una sola vez, con `lat=41.387&lon=2.169`, la búsqueda sigue en Barcelona, desaparece «Buscando tu ubicación…» y aparece «Volver a mi ubicación»

#### Scenario: Volver a una ubicación tardía fuera de España
- **WHEN** se pinchó en Barcelona mientras se esperaba, después llegó la ubicación (51.5074, -0.1278), se pulsa «Volver a mi ubicación» y la API responde 422 `fuera_de_espana`
- **THEN** se ve «Ese punto está fuera de España. Pincha en el mapa un punto de España.», el mapa muestra la Península y Baleares enteras, no hay marcador del punto, círculo ni resultados, y «Volver a mi ubicación» desaparece

#### Scenario: Pinchar fuera de España mientras se espera
- **WHEN** mientras se espera la ubicación se pincha en Rabat (34.0209, -6.8416), la API responde 422 `fuera_de_espana`, y después el navegador entrega (40.416775, -3.703790)
- **THEN** se sigue viendo el mensaje de fuera de España, no se busca en la ubicación y solo aparece «Volver a mi ubicación»

### Requirement: Sin ubicación del navegador
Si el navegador deniega la ubicación, no la tiene o no la entrega en 10 s
desde que la página la pide, la página SHALL mostrar España peninsular y
Baleares enteras, decir «Pincha en el mapa para elegir dónde buscar» y no
pedir cercanas hasta que se pinche o llegue la ubicación; ese texto se quita
al pinchar o al llegar la ubicación. Si ya se había pinchado un punto, solo
quita «Buscando tu ubicación…»: no mueve el mapa ni cambia la búsqueda.

#### Scenario: Ubicación denegada
- **WHEN** el navegador deniega el permiso de ubicación
- **THEN** el mapa muestra la Península y Baleares enteras, aparece «Pincha en el mapa para elegir dónde buscar» y no se hace ninguna petición a `/api/stations/nearby`

#### Scenario: Navegador sin ubicación
- **WHEN** el navegador no ofrece geolocalización
- **THEN** la página se comporta igual que con la ubicación denegada

#### Scenario: Ubicación que no llega
- **WHEN** el navegador no responde a la petición de ubicación, ni siquiera mostrando el permiso
- **THEN** a los 10 s desde que la página la pidió (con un margen de 1 s) la página se comporta igual que con la ubicación denegada

#### Scenario: Pinchar y que no llegue la ubicación
- **WHEN** a los 3 s se pincha en (41.3874, 2.1686) y a los 10 s la ubicación no ha llegado
- **THEN** el mapa sigue en Barcelona con sus resultados, desaparece «Buscando tu ubicación…», no aparece «Pincha en el mapa para elegir dónde buscar», no se hace otra petición y no se ve «Volver a mi ubicación»

#### Scenario: Pinchar y que después se deniegue
- **WHEN** a los 3 s se pincha en (41.3874, 2.1686) y a los 5 s el navegador deniega la ubicación
- **THEN** pasa lo mismo que en el escenario anterior

#### Scenario: Ubicación tardía sin pinchar
- **WHEN** la ubicación no llega en 10 s, el usuario no pincha, y a los 15 s el navegador entrega (40.416775, -3.703790)
- **THEN** la página usa esa ubicación igual que si hubiera llegado a tiempo, desaparece «Pincha en el mapa para elegir dónde buscar» y aparece «Volver a mi ubicación»

#### Scenario: Ubicación tardía después de pinchar
- **WHEN** la ubicación no llega en 10 s, el usuario pincha en (41.3874, 2.1686) y después el navegador entrega (40.416775, -3.703790)
- **THEN** la búsqueda sigue en Barcelona, no se hace otra petición por la ubicación tardía y aparece «Volver a mi ubicación»

### Requirement: Cambiar el punto pinchando en el mapa
Pinchar en el mapa SHALL mover el punto de búsqueda allí y buscar de nuevo
con el combustible y el radio elegidos, haya o no ubicación del navegador.
Pinchar en un marcador de gasolinera no cambia el punto.

#### Scenario: Pinchar en Barcelona
- **WHEN** la búsqueda está en Madrid y se pincha en (41.3874, 2.1686)
- **THEN** el marcador del punto y el círculo pasan a Barcelona, se pide `/api/stations/nearby` con `lat=41.387&lon=2.169` y la lista y los marcadores muestran solo las gasolineras de esa respuesta

#### Scenario: Pinchar en un marcador de gasolinera
- **WHEN** se pulsa el marcador de una gasolinera
- **THEN** se abre su ficha y no se hace ninguna petición

### Requirement: Selector de combustible
La página SHALL ofrecer los combustibles válidos de `/api/fuels` con alguna
estación (`stations` mayor que 0), en el orden de la API, con nombre y
unidad. Se ignora un elemento al que le falte como texto cualquiera de
`slug`, `name` o `unit`, o cuyo `stations` no sea un número. Por defecto se
elige el primero. Cambiar de combustible busca si hay punto.

#### Scenario: Opciones del selector
- **WHEN** `/api/fuels` devuelve Gasoleo A (3 estaciones, €/l), Gasolina 95 E5 (2, €/l), Adblue (1, €/l), Hidrogeno (1, €/kg) y los otros 17 con 0
- **THEN** el selector tiene exactamente «Gasoleo A (€/l)», «Gasolina 95 E5 (€/l)», «Adblue (€/l)» e «Hidrogeno (€/kg)», en ese orden, con Gasoleo A elegido

#### Scenario: Cambiar a Hidrogeno
- **WHEN** hay una búsqueda en Madrid con Gasoleo A y se elige «Hidrogeno (€/kg)»
- **THEN** se pide `/api/stations/nearby` con `fuel=hidrogeno` y los precios se muestran en €/kg

#### Scenario: Cambiar sin punto
- **WHEN** no hay punto elegido (ubicación denegada y sin pinchar) y se cambia de combustible
- **THEN** no se hace ninguna petición

#### Scenario: Elementos no válidos
- **WHEN** `/api/fuels` devuelve Gasoleo A (3 estaciones) correcto, un elemento sin `slug` con 5 estaciones, otro con `unit` `null` con 2 y otro con `stations` `"4"`
- **THEN** el selector tiene solo «Gasoleo A (€/l)»

#### Scenario: Ningún combustible con estaciones
- **WHEN** `/api/fuels` devuelve los 21 combustibles con 0 estaciones
- **THEN** la página dice «No hay precios en la última captura» con «Reintentar» (que vuelve a pedir `/api/fuels`) y no pide cercanas

#### Scenario: Lista de combustibles que no se puede usar
- **WHEN** `/api/fuels` responde 200 pero `data` no es una lista, o ningún elemento es válido
- **THEN** la página dice «El servidor ha dado una respuesta inesperada» con un botón «Reintentar», y no pide cercanas

### Requirement: Selector de radio
La página SHALL ofrecer los radios 5, 10, 25 y 50 km, con 10 km por
defecto. Cambiar de radio, si hay punto, redibuja el círculo, lo encuadra y
busca de nuevo; sin punto no dibuja nada ni hace peticiones.

#### Scenario: Opciones del radio
- **WHEN** se abre la página por primera vez
- **THEN** el selector de radio tiene «5 km», «10 km», «25 km» y «50 km», con «10 km» elegido

#### Scenario: Cambiar a 50 km
- **WHEN** hay una búsqueda en Madrid a 10 km y se elige «50 km»
- **THEN** se pide `/api/stations/nearby` con `radius_km=50` y el círculo de 50 km se ve entero

#### Scenario: Cambiar sin punto
- **WHEN** no hay punto elegido y se elige «25 km»
- **THEN** no se dibuja ningún círculo ni se hace ninguna petición, y al pinchar después se busca con `radius_km=25`

### Requirement: Recordar la última elección
La página SHALL guardar en el navegador el combustible y el radio elegidos
y usarlos al volver a abrirla. Si no se puede leer o guardar, o lo guardado
ya no es una opción válida, MUST funcionar igual con los valores por defecto.

#### Scenario: Volver a abrir
- **WHEN** se elige «Gasolina 95 E5 (€/l)» y «25 km», se cierra la página y se vuelve a abrir
- **THEN** salen elegidos Gasolina 95 E5 y 25 km, y la primera búsqueda usa `fuel=gasolina-95-e5&radius_km=25`

#### Scenario: Almacenamiento bloqueado
- **WHEN** el navegador lanza un error al leer o al guardar en el almacenamiento de la página
- **THEN** la página funciona entera con Gasoleo A y 10 km, sin mensajes de error y sin errores sin capturar en la consola

#### Scenario: Combustible guardado que ya no se vende
- **WHEN** está guardado `hidrogeno` y `/api/fuels` da Hidrogeno con 0 estaciones
- **THEN** se elige el primero de la lista (Gasoleo A) y el radio guardado se respeta

#### Scenario: Valores guardados no válidos
- **WHEN** está guardado el combustible `diesel` y el radio `7`
- **THEN** se eligen Gasoleo A y 10 km

### Requirement: Peticiones a la API justas y sin respuestas viejas
La página SHALL pedir `/api/health` y `/api/fuels` una vez al abrirse, y
cada acción (ubicación, pinchar, cambiar combustible o radio, «Volver a mi
ubicación», «Reintentar») hace como mucho una petición a cada ruta que
necesita, con `limit=100`. MUST NOT repetir peticiones por su cuenta y solo
muestra la respuesta de la última acción.

#### Scenario: Página quieta
- **WHEN** la página muestra resultados y no se toca durante 5 minutos
- **THEN** no se hace ninguna petición a `/api/` en ese tiempo

#### Scenario: Abrir y ver la ficha
- **WHEN** se abre la página con ubicación concedida, se buscan cercanas y se abren las fichas de tres gasolineras
- **THEN** en total se ha pedido una vez `/api/health`, una vez `/api/fuels` y una vez `/api/stations/nearby`, y ninguna vez `/api/stations/{id}`

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

### Requirement: Lista de gasolineras
La página SHALL listar las gasolineras de la respuesta en el mismo orden que
la API (precio, distancia, identificador), cada una con su rótulo, su
distancia y su precio con unidad. Un rótulo vacío se muestra como «Sin
rótulo». Una estación sin precio o sin coordenadas numéricas no se muestra.

#### Scenario: Lista en Madrid
- **WHEN** la búsqueda con Gasoleo A a 5 km devuelve "1003" (CEPSA, 1.399, 3.4 km), "1001" (REPSOL, 1.459, 0.91 km) y "1002" (`brand` `null`, 1.459, 2.01 km)
- **THEN** la lista muestra, en ese orden, «CEPSA · 3,4 km · 1,399 €/l», «REPSOL · 0,9 km · 1,459 €/l» y «Sin rótulo · 2,0 km · 1,459 €/l», y hay tres marcadores de gasolineras, además del del punto

#### Scenario: Estación con datos que no sirven
- **WHEN** la respuesta trae "1001" con `price` `"1,459"` (texto) y "1003" con `latitude` `null`, además de "1002" correcta
- **THEN** solo se muestra "1002", en la lista y en el mapa, y no hay errores sin capturar en la consola

#### Scenario: Todas descartadas
- **WHEN** la respuesta tiene `total` 2 y las dos estaciones tienen `price` `null`
- **THEN** la página dice «El servidor ha dado una respuesta inesperada» con «Reintentar», sin lista ni marcadores

#### Scenario: Respuesta incompleta
- **WHEN** `/api/stations/nearby` responde 200 sin `data.stations`
- **THEN** la página dice «El servidor ha dado una respuesta inesperada» con «Reintentar», y no quedan marcadores de la búsqueda anterior

### Requirement: Recuento de gasolineras encontradas
Tras cada búsqueda con al menos una gasolinera mostrada, la página SHALL
decir cuántas se ven (tras descartar las que no sirven), en singular o
plural. Con `total` 0, con todas descartadas o con un error no hay
recuento, y el de la búsqueda anterior desaparece.

#### Scenario: Tres gasolineras
- **WHEN** la búsqueda muestra 3 gasolineras
- **THEN** se ve «3 gasolineras encontradas»

#### Scenario: Una gasolinera
- **WHEN** la búsqueda muestra 1 gasolinera
- **THEN** se ve «1 gasolinera encontrada»

#### Scenario: Sin recuento
- **WHEN** había «3 gasolineras encontradas» y la búsqueda siguiente responde con `total` 0, con todas descartadas o con un 503
- **THEN** no se ve ningún recuento

### Requirement: Aviso de gasolineras descartadas
Si la página descarta alguna estación recibida por datos que no sirven y
aún muestra al menos una, SHALL decir cuántas no se muestran, en singular
o plural, sin sugerir otro radio. El aviso de la búsqueda anterior
desaparece.

#### Scenario: Con una descartada
- **WHEN** la búsqueda a 10 km responde con `total` 3 y 3 estaciones, y una no tiene coordenadas
- **THEN** se ve «2 gasolineras encontradas» y «1 gasolinera no se muestra por datos incompletos.», y no se ve el aviso de «Hay N gasolineras en este radio…»

#### Scenario: Con dos descartadas
- **WHEN** la respuesta tiene 5 estaciones y dos tienen `price` `null`
- **THEN** se ve «2 gasolineras no se muestran por datos incompletos.»

#### Scenario: El aviso de descartadas desaparece
- **WHEN** se veía «2 gasolineras no se muestran por datos incompletos.» y la búsqueda siguiente tiene todas las estaciones válidas, o `total` 0, o da un error
- **THEN** ya no se ve ese aviso

### Requirement: Aviso de más gasolineras de las mostradas
Si muestra al menos una gasolinera y `total` es mayor que el número de
estaciones recibidas de la API, la página SHALL decir cuántas ha recibido y
cuántas hay, y sugerir reducir el radio salvo si ya es 5 km. Las descartadas
se avisan aparte. El aviso de la búsqueda anterior desaparece.

#### Scenario: Más de 100 a 25 km
- **WHEN** la búsqueda a 25 km responde con `total` 342 y 100 estaciones válidas
- **THEN** se ven las 100 y el texto «Hay 342 gasolineras en este radio; se han pedido las 100 más baratas. Reduce el radio para ver menos y más cercanas.»

#### Scenario: Más de 100 a 5 km
- **WHEN** la búsqueda a 5 km responde con `total` 130 y 100 estaciones válidas
- **THEN** se ve «Hay 130 gasolineras en este radio; se han pedido las 100 más baratas.», sin sugerir otro radio

#### Scenario: Con estaciones descartadas
- **WHEN** la búsqueda a 25 km responde con `total` 342 y 100 estaciones, de las que 2 no tienen coordenadas
- **THEN** se ven «98 gasolineras encontradas», «Hay 342 gasolineras en este radio; se han pedido las 100 más baratas. Reduce el radio para ver menos y más cercanas.» y «2 gasolineras no se muestran por datos incompletos.»

#### Scenario: Todas recibidas y válidas
- **WHEN** la respuesta tiene `total` 3 y 3 estaciones válidas
- **THEN** no se ve ese aviso

#### Scenario: Ninguna se puede mostrar
- **WHEN** la respuesta tiene `total` 342 y 100 estaciones, todas con `price` `null`
- **THEN** solo se ve «El servidor ha dado una respuesta inesperada» con «Reintentar», sin aviso de «Hay N gasolineras en este radio…», de descartadas ni recuento

#### Scenario: El aviso anterior desaparece
- **WHEN** se veía «Hay 342 gasolineras en este radio; se han pedido las 100 más baratas…» y la búsqueda siguiente tiene `total` 3 y 3 estaciones, o `total` 0, o da un error
- **THEN** ya no se ve ese aviso

### Requirement: Formato de precios y distancias
Los precios SHALL mostrarse con coma decimal y tres decimales seguidos de
su unidad («1,459 €/l»), y las distancias con coma decimal y un decimal,
redondeando la mitad hacia arriba («3,4 km»).

#### Scenario: Precios
- **WHEN** se formatean los precios 1.459, 1.4 y 12.95 con sus unidades €/l, €/l y €/kg
- **THEN** se muestran «1,459 €/l», «1,400 €/l» y «12,950 €/kg»

#### Scenario: Distancias
- **WHEN** se formatean las distancias 0.91, 2.05, 3.4, 0 y 50
- **THEN** se muestran «0,9 km», «2,1 km», «3,4 km», «0,0 km» y «50,0 km»

### Requirement: Colores por tercios
Con N gasolineras mostradas y al menos dos precios distintos, las del
precio mínimo SHALL ser «más barata» y las del máximo «más cara». Cada otra
es «más barata» si menos de N/3 son más baratas que ella y no menos de N/3
más caras; «más cara» al revés; si no, «intermedia». Las de igual precio van
juntas. Con un solo precio, todas son «precio único».

#### Scenario: Seis precios distintos
- **WHEN** se muestran precios 1.400, 1.410, 1.420, 1.430, 1.440 y 1.450
- **THEN** 1.400 y 1.410 son «más barata», 1.420 y 1.430 «intermedia», y 1.440 y 1.450 «más cara»

#### Scenario: Una gasolinera extrema
- **WHEN** se muestran precios 1.400, 1.410, 1.420, 1.430, 1.440, 1.450 y 2.500
- **THEN** 1.400, 1.410 y 1.420 son «más barata», 1.430 «intermedia», y 1.440, 1.450 y 2.500 «más cara»

#### Scenario: Empates en Madrid
- **WHEN** se muestran precios 1.299, 1.399, 1.459 y 1.459
- **THEN** 1.299 y 1.399 son «más barata» y las dos de 1.459 «más cara»

#### Scenario: Empate que ocupa el centro
- **WHEN** se muestran precios 1.400, 1.500, 1.500, 1.500 y 1.600
- **THEN** 1.400 es «más barata», las tres de 1.500 «intermedia» y 1.600 «más cara»

#### Scenario: Mayoría en el precio mínimo
- **WHEN** se muestran precios 1.400, 1.400, 1.400, 1.400 y 1.500
- **THEN** las cuatro de 1.400 son «más barata» y 1.500 «más cara»

#### Scenario: Mayoría en el precio máximo
- **WHEN** se muestran precios 1.400, 1.500, 1.500, 1.500 y 1.500
- **THEN** 1.400 es «más barata» y las cuatro de 1.500 «más cara»

#### Scenario: Dos gasolineras
- **WHEN** se muestran precios 1.399 y 1.459
- **THEN** 1.399 es «más barata» y 1.459 «más cara»

#### Scenario: Todas al mismo precio
- **WHEN** se muestran tres gasolineras a 1.459
- **THEN** las tres son «precio único» y la leyenda dice «Todas a 1,459 €/l»

#### Scenario: Una sola gasolinera
- **WHEN** se muestra una sola gasolinera a 1.399
- **THEN** es «precio único» y la leyenda dice «Todas a 1,399 €/l»

### Requirement: Marcadores con el precio en texto y leyenda
Cada marcador SHALL mostrar el precio en texto con el color de su tercio, y
una leyenda SHALL explicar los colores (tercios de las mostradas, con el
precio mínimo y el máximo siempre en sus extremos) y dar el precio más bajo
y el más alto, de modo que el color nunca sea la única pista. En el
escritorio se ve siempre; en el móvil, al desplegar la hoja de la lista.

#### Scenario: Marcadores y leyenda
- **WHEN** se muestran 4 gasolineras de Gasoleo A a 1.299, 1.399, 1.459 y 1.459
- **THEN** cada marcador muestra su precio («1,299», «1,399», «1,459», «1,459»), y la leyenda muestra los tres colores con «Más barata», «Intermedia» y «Más cara», el texto «Colores por tercios de las 4 gasolineras mostradas; el precio mínimo y el máximo siempre en sus extremos» y «De 1,299 a 1,459 €/l»

#### Scenario: Leyenda en el móvil
- **WHEN** en un iPhone se muestran esas 4 gasolineras con la hoja plegada, y después se despliega
- **THEN** plegada no se ve la leyenda y cada marcador sigue mostrando su precio; desplegada, la leyenda se ve completa

#### Scenario: Sin color
- **WHEN** se ve la página en escala de grises
- **THEN** cada gasolinera se puede identificar y comparar por el precio escrito en su marcador y en la lista

### Requirement: Lista y mapa sincronizados
Pulsar una gasolinera de la lista SHALL resaltarla en la lista y en el mapa,
mover el mapa si no se ve y abrir su ficha. Pulsar su marcador SHALL
resaltarla igual y abrir su ficha; en el escritorio, además, desplaza la
lista hasta ella. Solo hay una resaltada a la vez.

#### Scenario: Pulsar en la lista
- **WHEN** en un iPhone se despliega la lista y se toca «REPSOL · 0,9 km · 1,459 €/l»
- **THEN** esa fila y el marcador de "1001" quedan resaltados, el marcador queda en la zona visible del mapa y se abre su ficha

#### Scenario: Pulsar un marcador en el escritorio
- **WHEN** en una ventana de 1280×800 hay 40 gasolineras en la lista, la última no se ve, y se pulsa su marcador
- **THEN** la lista se desplaza hasta que su fila se ve, esa fila y el marcador quedan resaltados y se abre su ficha

#### Scenario: Tocar un marcador en el móvil
- **WHEN** en un iPhone, con la lista plegada, se toca el marcador de "1002"
- **THEN** se abre su ficha, el marcador queda resaltado y su fila queda marcada como resaltada en la lista

#### Scenario: Cambiar de seleccionada
- **WHEN** "1001" está resaltada y se pulsa "1002"
- **THEN** solo "1002" queda resaltada y la ficha es la de "1002"

#### Scenario: Nueva búsqueda
- **WHEN** "1001" está resaltada y se pincha en otro punto del mapa, se cambia de combustible o de radio, o se pulsa «Volver a mi ubicación»
- **THEN** en cada caso no queda ninguna resaltada y la ficha se cierra

### Requirement: Ficha sencilla de la gasolinera
La ficha SHALL mostrar rótulo, dirección, municipio, precio y distancia de la
respuesta de cercanas, sin hacer peticiones. En el móvil es una hoja inferior
en el sitio de la de la lista, nunca un globo sobre el mapa, de como mucho el
70 % del alto, con «Cerrar» siempre a la vista; en el escritorio, va en el
panel lateral. Se cierra con «Cerrar» o Escape, sin dejar ninguna resaltada.

#### Scenario: Ficha completa
- **WHEN** se pulsa "4375" (REPSOL, CALLE MAYOR, 1, Madrid) con Gasoleo A a 1.459 a 0.04 km
- **THEN** la ficha muestra «REPSOL», «CALLE MAYOR, 1», «Madrid», «1,459 €/l» y «0,0 km», y no se hace ninguna petición

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

### Requirement: Textos de la API mostrados como texto
Todo texto que llega de la API (rótulos, direcciones, municipios, nombres de
combustible y mensajes de error) SHALL mostrarse literalmente, nunca
interpretado como HTML ni como código.

#### Scenario: Rótulo con etiquetas
- **WHEN** el rótulo de una gasolinera es `<img src=x onerror=alert(1)>`
- **THEN** la lista y la ficha muestran ese texto tal cual y no se ejecuta nada

#### Scenario: Mensaje de error con etiquetas
- **WHEN** `/api/fuels` responde 503 `sin_capturas` con el mensaje `<b>sin datos</b>`
- **THEN** el mensaje se ve con las etiquetas escritas, sin negrita

### Requirement: Textos de la página sin la palabra API
Los textos propios de la página que ve el usuario (mensajes, avisos,
botones, etiquetas y leyenda) SHALL estar en español claro y MUST NOT usar
la palabra «API»; para referirse al servicio dicen «el servidor». Solo el
detalle que llega del servidor tras «Detalle:» se muestra tal cual.

#### Scenario: Recorrido por todos los estados
- **WHEN** se recorren los estados de los escenarios de esta spec (resultados, sin resultados, fuera de España, ocupado, sin datos, caído, respuesta inesperada, datos desactualizados) y se recoge el texto visible propio de la página, sin los datos de las gasolineras ni lo que sigue a «Detalle:»
- **THEN** en ningún caso aparece la palabra «API», en mayúsculas o minúsculas

### Requirement: Accesibilidad básica
La página SHALL poder usarse con teclado y lector de pantalla: selectores con
etiqueta visible, lista, botones y hoja inferior manejables con el teclado,
avisos y resultados anunciados, foco que entra en la ficha al abrirla y
vuelve al cerrarla, y texto de los marcadores con contraste de al menos
4,5:1.

#### Scenario: Etiquetas de los selectores
- **WHEN** se revisan los selectores
- **THEN** el de combustible tiene la etiqueta visible «Combustible» y el de radio «Radio», asociadas a cada uno

#### Scenario: Lista con el teclado
- **WHEN** en una ventana de 1280×800 se llega a la fila de "1001" con el tabulador y se pulsa Intro
- **THEN** pasa lo mismo que al pulsarla, y el foco pasa a la ficha

#### Scenario: Botón de la hoja inferior
- **WHEN** en un iPhone se revisa el botón que despliega la lista
- **THEN** dice «Ver lista» con `aria-expanded="false"` y, al pulsarlo, «Ocultar lista» con `aria-expanded="true"`, y se puede usar con el teclado

#### Scenario: Foco al cerrar
- **WHEN** la ficha se abrió desde la fila de "1001" y se pulsa Escape
- **THEN** la ficha se cierra y el foco vuelve a la fila de "1001"

#### Scenario: Foco al cerrar una ficha abierta desde un marcador
- **WHEN** la ficha de "1001" se abrió pulsando su marcador y se pulsa «Cerrar»
- **THEN** el foco pasa a la fila de "1001" si la lista se ve (escritorio o lista desplegada) y, si está plegada, al botón «Ver lista»

#### Scenario: Foco al cerrar una ficha abierta desde la más barata
- **WHEN** con la hoja plegada se abrió la ficha de "1003" desde «Más barata: CEPSA · 3,4 km · 1,399 €/l» y se pulsa «Cerrar»
- **THEN** el foco vuelve al botón «Más barata: …»

#### Scenario: Avisos anunciados
- **WHEN** llega una búsqueda con 3 gasolineras, o un error, o el aviso de datos desactualizados
- **THEN** el texto correspondiente («3 gasolineras encontradas», el mensaje de error o el aviso) está en una zona que los lectores de pantalla anuncian al cambiar

#### Scenario: Contraste de los marcadores
- **WHEN** se mide el contraste del texto de un marcador sobre el color de cada tercio y de «precio único»
- **THEN** es de al menos 4,5:1 en los cuatro casos, también resaltado

### Requirement: Captura de los precios en hora de Madrid
La página SHALL decir de qué captura son los precios mostrados, con
`capture.downloaded_at` de la respuesta de cercanas pasada a hora de
Madrid, sea cual sea la zona horaria del navegador.

#### Scenario: Horario de verano
- **WHEN** la respuesta tiene `capture.downloaded_at` `2026-10-16T07:26:37Z` y el navegador está en la zona horaria de Nueva York
- **THEN** la página dice «Precios de la captura del 16/10/2026 a las 09:26 (hora de Madrid)»

#### Scenario: Horario de invierno
- **WHEN** la respuesta tiene `capture.downloaded_at` `2026-11-02T05:17:03Z` y el navegador está en la zona horaria UTC
- **THEN** la página dice «Precios de la captura del 02/11/2026 a las 06:17 (hora de Madrid)»

#### Scenario: Fecha que no se entiende
- **WHEN** la respuesta tiene `capture.downloaded_at` `"ayer"` o no tiene `capture`
- **THEN** la página muestra las gasolineras y dice «Fecha de la captura desconocida»

### Requirement: Aviso de datos desactualizados
Si `/api/health` responde con `status` `desactualizada`, la página SHALL
mostrar un aviso visible con `capture.downloaded_at` en hora de Madrid. Con
otro estado, o si la salud falla, no muestra ese aviso ni bloquea la página.

#### Scenario: Datos desactualizados
- **WHEN** `/api/health` responde 200 con `status` `desactualizada` y `capture.downloaded_at` `2026-10-16T07:26:37Z`
- **THEN** se ve «Los precios pueden no estar al día: la última captura es del 16/10/2026 a las 09:26 (hora de Madrid)» y la búsqueda funciona igual

#### Scenario: Datos al día
- **WHEN** `/api/health` responde con `status` `ok` o `configuracion_no_valida`
- **THEN** no se ve ningún aviso de desactualización

#### Scenario: Salud que falla
- **WHEN** `/api/health` responde 503 `api_ocupada` o no responde
- **THEN** no se ve aviso de desactualización, no se repite la petición y el resto de la página funciona según las demás respuestas

### Requirement: API o base ocupadas
Si `/api/fuels` o `/api/stations/nearby` responde 503 `api_ocupada`,
`base_ocupada` o `consulta_demasiado_larga`, la página SHALL decir «El
servidor está ocupado; inténtalo en unos segundos» y ofrecer «Reintentar»,
desactivado hasta que pasen los segundos de `Retry-After` (5 si falta o no
es un entero de 1 a 60).

#### Scenario: Base ocupada con Retry-After
- **WHEN** `/api/stations/nearby` responde 503 `base_ocupada` con `Retry-After: 5`
- **THEN** se ve «El servidor está ocupado; inténtalo en unos segundos», «Reintentar» está desactivado durante 5 s (con un margen de 0,5 s) y después se activa; no se repite la petición sola

#### Scenario: Reintentar
- **WHEN** tras el 503 anterior se activa y se pulsa «Reintentar», y esta vez la respuesta es 200
- **THEN** se hace una sola petición con los mismos parámetros y se muestran las gasolineras

#### Scenario: API ocupada con otro Retry-After
- **WHEN** `/api/fuels` responde 503 `api_ocupada` con `Retry-After: 12`
- **THEN** «Reintentar» está desactivado durante 12 s

#### Scenario: Consulta demasiado larga
- **WHEN** `/api/stations/nearby` responde 503 `consulta_demasiado_larga` sin `Retry-After`
- **THEN** se ve «El servidor está ocupado; inténtalo en unos segundos» y «Reintentar» está desactivado durante 5 s

#### Scenario: Retry-After raro
- **WHEN** la respuesta 503 `base_ocupada` no tiene `Retry-After`, o tiene `0`, `abc`, `3600` o una fecha
- **THEN** «Reintentar» está desactivado durante 5 s

### Requirement: Sin datos en la base
Con cualquier otro 503 en JSON (`sin_base`, `sin_capturas`, `base_ilegible`,
`base_no_compatible`, `recogida_a_medias` u otro código), la página SHALL
decir «No hay datos disponibles.» seguido de «Detalle: » y el
`message` recibido, con «Reintentar» sin retardo.

#### Scenario: Base sin capturas
- **WHEN** `/api/fuels` responde 503 `sin_capturas` con el mensaje «todavía no hay capturas guardadas»
- **THEN** se ve «No hay datos disponibles. Detalle: todavía no hay capturas guardadas» con «Reintentar» activo

#### Scenario: 503 sin mensaje
- **WHEN** `/api/fuels` responde 503 con un código desconocido y sin `error.message`
- **THEN** se ve «No hay datos disponibles.» con «Reintentar» activo

### Requirement: Sin gasolineras en el radio
Si la búsqueda responde con `total` 0, la página SHALL decir que no hay
gasolineras con ese combustible en ese radio, sugerir un radio mayor si lo
hay, y no dejar marcadores ni lista de la búsqueda anterior.

#### Scenario: Sin resultados a 10 km
- **WHEN** la búsqueda con Hidrogeno a 10 km responde 200 con `total` 0
- **THEN** se ve «No hay gasolineras con Hidrogeno a menos de 10 km. Prueba con un radio mayor.», el círculo sigue dibujado y no hay marcadores de gasolineras

#### Scenario: Sin resultados a 50 km
- **WHEN** la búsqueda con Hidrogeno a 50 km responde con `total` 0
- **THEN** se ve «No hay gasolineras con Hidrogeno a menos de 50 km.», sin sugerir otro radio

### Requirement: Punto fuera de España
Si la búsqueda responde 422 `fuera_de_espana`, la página SHALL decir «Ese
punto está fuera de España. Pincha en el mapa un punto de España.» y quitar
el marcador del punto, el círculo y los resultados anteriores; si venía de
la ubicación del navegador, además, muestra la vista de España.

#### Scenario: Pinchar en Rabat
- **WHEN** se pincha en (34.0209, -6.8416) y la API responde 422 `fuera_de_espana`
- **THEN** se ve el mensaje, no hay marcador del punto, círculo, lista ni marcadores de gasolineras, y al pinchar después en Madrid se busca con normalidad

#### Scenario: Ubicación en Londres
- **WHEN** el navegador concede la ubicación (51.5074, -0.1278) y la API responde 422 `fuera_de_espana`
- **THEN** se ve el mensaje, el mapa muestra la Península y Baleares enteras y no se ve «Volver a mi ubicación»

#### Scenario: Punto de Portugal dentro de la zona de la Península
- **WHEN** se pincha en Lisboa (38.7223, -9.1393) con Gasoleo A a 10 km y la API responde 200 con `total` 0
- **THEN** se ve «No hay gasolineras con Gasoleo A a menos de 10 km. Prueba con un radio mayor.», como en cualquier punto sin resultados

### Requirement: API caída o respuesta inesperada
Si la API no responde en 15 s, falla la red, responde algo que no es JSON
(también en un 503) o da un error JSON no cubierto por los requisitos
anteriores, la página SHALL dar un mensaje claro con «Reintentar» (sin
retardo), sin mostrar detalles técnicos ni dejar resultados viejos.

#### Scenario: API caída al abrir
- **WHEN** las peticiones a `/api/fuels` fallan por red
- **THEN** se ve «No se puede conectar con el servidor. Comprueba que está en marcha y que el túnel está abierto.» con «Reintentar», y el mapa y las atribuciones siguen visibles

#### Scenario: API que no contesta
- **WHEN** `/api/stations/nearby` no contesta
- **THEN** a los 15 s (con un margen de 1 s) se ve «No se puede conectar con el servidor. Comprueba que está en marcha y que el túnel está abierto.» con «Reintentar»

#### Scenario: Respuesta que no es JSON
- **WHEN** `/api/stations/nearby` responde 502 con una página HTML
- **THEN** se ve «El servidor ha dado una respuesta inesperada» con «Reintentar», sin el HTML recibido

#### Scenario: 503 que no es JSON
- **WHEN** `/api/fuels` responde 503 con una página HTML de un proxy
- **THEN** se ve «El servidor ha dado una respuesta inesperada» con «Reintentar», no «No hay datos disponibles»

#### Scenario: Error interno
- **WHEN** `/api/stations/nearby` responde 500 `error_interno`
- **THEN** se ve «El servidor ha dado un error. Inténtalo más tarde.» con «Reintentar»

#### Scenario: Otros errores de la API
- **WHEN** `/api/stations/nearby` responde 422 `combustible_desconocido`, o 404, 405 o 429 con un error JSON
- **THEN** se ve «El servidor ha dado un error. Inténtalo más tarde.» con «Reintentar» activo, sin el mensaje ni el código de la API

#### Scenario: Reintentar tras combustible desconocido
- **WHEN** `/api/stations/nearby` respondió 422 `combustible_desconocido` y se pulsa «Reintentar»
- **THEN** se pide una vez `/api/fuels` y, si responde bien, una vez `/api/stations/nearby` con el combustible elegido si sigue en la lista, o con el primero si no

### Requirement: Diseño mobile first
Las hojas de estilo SHALL tener como base el diseño de móvil (de 320 a 430
px de ancho) y añadir el de escritorio con media queries `min-width`, como
mejora progresiva; MUST NOT usar media queries `max-width`. Por debajo de
1024 px de ancho se usa el diseño de móvil; desde 1024 px, el de escritorio.

#### Scenario: Hojas de estilo
- **WHEN** se revisan las hojas de estilo de `web/` (sin contar la de Leaflet)
- **THEN** todas las media queries de ancho son `min-width` y ninguna es `max-width`

#### Scenario: Móvil en horizontal y tableta
- **WHEN** se abre la página con resultados en ventanas de 750×342 (iPhone en horizontal) y de 820×1180
- **THEN** se usa el diseño de móvil: mapa a pantalla completa y hoja inferior

#### Scenario: Escritorio
- **WHEN** se abre la página con resultados en una ventana de 1280×800
- **THEN** se usa el diseño de escritorio: panel lateral y mapa

### Requirement: Mapa a pantalla completa en el móvil
En el diseño de móvil el mapa SHALL ocupar toda la pantalla, sin scroll de
la página, con la hoja inferior y las atribuciones encima. Los encuadres se
hacen sobre la zona visible del mapa: la que no tapan la hoja ni la caja de
atribuciones (los botones de zoom, estrechos y a un lado, no se descuentan).
En esta spec, que algo «se ve entero» en el mapa quiere decir dentro de esa
zona.

#### Scenario: iPhone y Android
- **WHEN** se abre la página con resultados en un iPhone (390×664) y en un Android (412×839)
- **THEN** el mapa cubre la ventana entera, la página no tiene scroll vertical ni horizontal, y el círculo del radio se ve entero entre la caja de atribuciones y la hoja plegada

#### Scenario: Teléfono pequeño
- **WHEN** se abre la página con resultados en una ventana de 320×568
- **THEN** el ancho del documento no pasa de 320 px, el mapa cubre la ventana y la zona visible del mapa ocupa al menos el 40 % de su alto con la hoja plegada

#### Scenario: Textos largos en el móvil
- **WHEN** en una ventana de 320×568 una gasolinera tiene un rótulo de 80 caracteres sin espacios
- **THEN** no aparece scroll horizontal, ni plegada ni desplegada, y el precio de esa fila se sigue viendo entero

### Requirement: Hoja inferior de la lista en el móvil
En el móvil, la lista SHALL ir en una hoja inferior con un botón para
desplegarla y plegarla. Plegada muestra los controles, la pista de
ubicación, el mensaje o error con «Reintentar», el aviso de datos
desactualizados, el recuento y la más barata (que abre su ficha). Desplegada
muestra además la captura, «Hay N…», las descartadas, la leyenda y la lista,
con su propio scroll y como mucho el 70 % del alto. En el móvil, lo que va en
la hoja desplegada se comprueba con ella desplegada.

#### Scenario: Plegada con resultados
- **WHEN** en un iPhone la búsqueda de Madrid a 5 km muestra "1003" (CEPSA, 1.399, 3.4 km), "1001" y "1002"
- **THEN** la hoja plegada muestra «3 gasolineras encontradas» y, en la misma fila, el botón «Ver lista», y debajo «Más barata: CEPSA · 3,4 km · 1,399 €/l»; no se ven las filas de la lista, la captura ni la leyenda

#### Scenario: Desplegar
- **WHEN** con 40 gasolineras se pulsa «Ver lista»
- **THEN** se ven la captura, la leyenda y las filas, la hoja mide como mucho el 70 % del alto de la ventana, la lista se desplaza dentro de la hoja sin mover la página, y el botón dice «Ocultar lista»

#### Scenario: Plegar
- **WHEN** la lista está desplegada y se pulsa «Ocultar lista»
- **THEN** la hoja vuelve a mostrar solo lo de la hoja plegada

#### Scenario: Tocar la más barata
- **WHEN** con la hoja plegada se toca «Más barata: CEPSA · 3,4 km · 1,399 €/l»
- **THEN** se abre la ficha de "1003" y su marcador queda resaltado

#### Scenario: Sin lista que mostrar
- **WHEN** no hay punto elegido, la búsqueda no da resultados o da un error
- **THEN** no se ven el botón «Ver lista» ni la línea de la más barata, y los avisos siguen en la hoja

#### Scenario: Desplegada entre búsquedas
- **WHEN** la lista está desplegada y se cambia el radio, y la búsqueda nueva da resultados
- **THEN** la lista sigue desplegada, con las gasolineras nuevas

#### Scenario: Se pliega al quedarse sin lista
- **WHEN** la lista está desplegada, una búsqueda da `total` 0 o un error, y la siguiente da resultados
- **THEN** tras la primera la hoja queda plegada, y tras la segunda sigue plegada con «Ver lista»

### Requirement: Panel lateral en el escritorio
Desde 1024 px de ancho, los controles, los avisos, la ficha, la captura, la
leyenda y la lista SHALL ir en un panel lateral izquierdo, con su propio
scroll, y el mapa ocupa el resto; no hay botón «Ver lista» ni línea de la
más barata.

#### Scenario: Escritorio con resultados
- **WHEN** se abre la página con 40 gasolineras en una ventana de 1280×800
- **THEN** el panel y el mapa están uno al lado del otro, los dos se ven sin desplazar la página, la lista se desplaza dentro del panel y no se ve «Ver lista»

### Requirement: Controles al alcance del pulgar
En el móvil, combustible, radio y «Volver a mi ubicación» SHALL estar en la
hoja inferior, en la mitad inferior de la pantalla, visibles con la hoja
plegada. Selectores, botones (también los de zoom) y filas de la lista miden
al menos 44×44 px en móvil y escritorio. Solo quedan fuera los marcadores de
precio, cuya vía accesible es la lista, y los enlaces dentro de un texto.

#### Scenario: Controles en vertical
- **WHEN** en un iPhone (390×664) y en un Android (412×839) la página muestra resultados y la ubicación concedida
- **THEN** los selectores de combustible y radio y «Volver a mi ubicación» se ven enteros por debajo de la mitad de la pantalla

#### Scenario: Controles en horizontal
- **WHEN** en un iPhone en horizontal (750×342) la página muestra resultados
- **THEN** esos tres controles se ven enteros por debajo de la mitad de la pantalla

#### Scenario: Objetivos táctiles
- **WHEN** se miden en una ventana de 320×568, con la hoja plegada, desplegada y con una ficha abierta, y en una de 1280×800, con y sin ficha
- **THEN** los selectores, los botones que se ven en cada caso («Ver lista», «Ocultar lista», «Cerrar», «Reintentar», la más barata, «Volver a mi ubicación», «Acercar» y «Alejar») y cada fila de la lista miden al menos 44 px de alto y 44 px de ancho

#### Scenario: Excepciones
- **WHEN** se miden los marcadores de precio y el enlace «OpenStreetMap contributors»
- **THEN** no se les exige 44 px, y cada gasolinera de un marcador tiene su fila en la lista, que sí los mide

### Requirement: Sin depender de hover
Ninguna función SHALL depender de pasar el puntero por encima: todo se hace
tocando o pulsando, también con el teclado. Las reglas `:hover` de las
hojas de estilo, si las hay, solo cambian la apariencia y van dentro de
`@media (hover: hover)`.

#### Scenario: Hojas de estilo sin hover
- **WHEN** se revisan las hojas de estilo de `web/` (sin contar la de Leaflet)
- **THEN** no hay ninguna regla `:hover` fuera de `@media (hover: hover)`

#### Scenario: Todo con toques
- **WHEN** en un Android emulado con pantalla táctil y sin ratón se toca el mapa en Madrid, se toca «Ver lista», se toca una fila, se toca «Cerrar», se toca un marcador y se cambia el radio
- **THEN** cada paso hace lo mismo que con clics: busca, despliega, abre y cierra la ficha y vuelve a buscar

### Requirement: Vertical y horizontal
La página SHALL funcionar en vertical y en horizontal, y al girar el
dispositivo conserva la búsqueda, la ficha abierta y el estado de la hoja.

#### Scenario: Girar con la ficha abierta
- **WHEN** en un iPhone en vertical (390×664) con resultados y la ficha de "1001" abierta se pasa a horizontal (750×342) y otra vez a vertical
- **THEN** en los dos giros la ficha sigue abierta y entera, «Cerrar» se ve, no aparece scroll de la página, no se hace ninguna petición nueva, y el marcador de "1001" sigue en la zona visible del mapa

#### Scenario: Girar con la lista desplegada
- **WHEN** con la lista desplegada en vertical se pasa a horizontal
- **THEN** la lista sigue desplegada, mide como mucho el 70 % del alto de la ventana y se desplaza dentro de la hoja

### Requirement: Alto de la pantalla y zonas seguras
La página SHALL declarar `<meta name="viewport" content="width=device-width,
initial-scale=1, viewport-fit=cover">` sin impedir el zoom, usar alturas en
`dvh` (nunca `100vh`) y respetar `env(safe-area-inset-*)` en la hoja
inferior, la ficha, la caja de atribuciones y el zoom, para la muesca y la
barra inferior de iOS, en vertical y en horizontal.

#### Scenario: Meta viewport
- **WHEN** se revisa `index.html`
- **THEN** tiene exactamente esa etiqueta `viewport`, sin `maximum-scale` ni `user-scalable=no`

#### Scenario: Alturas
- **WHEN** se revisan las hojas de estilo de `web/` (sin contar la de Leaflet)
- **THEN** no aparece ninguna medida en `vh` sin `d`; `body` y el mapa tienen `height: 100dvh`, y la hoja desplegada y la ficha tienen `max-height: 70dvh`

#### Scenario: Zonas seguras
- **WHEN** se revisan las hojas de estilo
- **THEN** la hoja de la lista y la ficha usan `env(safe-area-inset-bottom)`, `env(safe-area-inset-left)` y `env(safe-area-inset-right)` en su relleno, y la esquina superior izquierda del mapa (caja de atribuciones y zoom), `env(safe-area-inset-top)` y `env(safe-area-inset-left)` en su margen

#### Scenario: En el motor de Safari
- **WHEN** se abre la página en el iPhone emulado con WebKit (390×664)
- **THEN** WebKit admite `dvh` y `env()` (`CSS.supports`), `body` y el mapa miden lo mismo que la ventana (`window.innerHeight`) y la hoja plegada toca el borde inferior

### Requirement: Peso de la página
Lo que la página descarga de su propio servidor al abrirse, sin contar las
respuestas de `/api/`, SHALL sumar como mucho 300 KB. De su propio servidor
no carga fuentes web ni más imágenes que el favicon. Las teselas de
OpenStreetMap no cuentan.

#### Scenario: Peso al abrir
- **WHEN** se abre la página en un iPhone emulado, sin caché, y se suman los bytes de los cuerpos recibidos del propio servidor fuera de `/api/` hasta que la página muestra la búsqueda
- **THEN** la suma es de 300 KB o menos, y del propio servidor no hay peticiones de fuentes ni de imágenes salvo `favicon.ico`

### Requirement: Pruebas sin servicios externos
Los tests de la página SHALL ejecutarse sobre todo con emulación móvil
táctil: el iPhone en WebKit (el motor de Safari) y el Android en Chromium, y
al menos una parte en escritorio en Chromium, con la ubicación simulada y
las teselas sustituidas por una imagen local. Los casos normales usan la API
real con una base de prueba temporal; los errores, respuestas fijas de
`tests/fixtures/`. MUST NOT salir ninguna petición del equipo.

#### Scenario: Ejecución de los tests
- **WHEN** se ejecutan todos los tests de la página registrando las peticiones del navegador
- **THEN** ninguna petición llega a OpenStreetMap, a la API del Ministerio ni a la API del VPS, y un test falla si la página lo intenta

#### Scenario: Dispositivos de los tests
- **WHEN** se revisan los tests de la página
- **THEN** por defecto se ejecutan con el iPhone 13 de Playwright en WebKit (390×664, táctil, móvil); los de horizontal, a 750×342 en WebKit; los de comportamiento común se repiten con el Pixel 7 en Chromium (412×839, táctil, móvil); los de tamaño mínimo, a 320×568 táctil en Chromium; y los de panel lateral, teclado y desplazamiento de la lista, en escritorio en Chromium (1280×800)

#### Scenario: Encaje con la API real
- **WHEN** se ejecuta el test de búsqueda en Madrid contra la app con una base de prueba con las estaciones "1001" a "1006" del escenario «Búsqueda en Madrid» de `prices-api`
- **THEN** la página muestra las gasolineras que da esa API, en su orden, y `./data` no se usa

### Requirement: Web incluida en la imagen
La imagen Docker SHALL incluir la carpeta `web/` con Leaflet y su licencia,
de modo que `docker compose up -d` sirva la página en `127.0.0.1:8000`, sin
publicar ningún puerto nuevo.

#### Scenario: Página desde el contenedor
- **WHEN** se lanza `docker compose up -d` con `./data` vacía y se pide `GET http://127.0.0.1:8000/`
- **THEN** la respuesta es 200 con la página, y `docker compose config` sigue publicando solo `127.0.0.1:8000`

### Requirement: Cómo abrir la web en el README
El README SHALL explicar cómo abrir la página en el Mac y por el túnel SSH
desde el VPS, qué hacer si el puerto 8000 del Mac ya está ocupado, que las
teselas necesitan internet, a quién llega la ubicación, cómo instalar los
navegadores de los tests y, como verificación opcional, cómo probarla en el
Simulador de iOS de Xcode.

#### Scenario: Lectura del README
- **WHEN** se lee la sección de la web del README
- **THEN** incluye `http://127.0.0.1:8000/`, el comando del túnel con `<IP_DEL_VPS>`, cómo usar otro puerto local (por ejemplo 8001) si el 8000 está ocupado por la API del Mac, que el mapa necesita internet para las teselas de OpenStreetMap, y que la ubicación y el punto pinchado solo se envían a la propia API, redondeados a unos 100 m, y no se guardan, mientras que OpenStreetMap recibe las peticiones de las teselas de la zona que se ve

#### Scenario: Navegadores de los tests
- **WHEN** se lee la sección de tests del README
- **THEN** incluye `.venv/bin/playwright install chromium` y `.venv/bin/playwright install webkit`

#### Scenario: Simulador de iOS
- **WHEN** se lee la sección de la web del README
- **THEN** explica, como verificación opcional que no bloquea nada, cómo abrir el Simulador de iOS de Xcode, abrir Safari en él con `http://127.0.0.1:8000/` (el Simulador llega a `127.0.0.1` del Mac y, por él, al túnel), darle una ubicación simulada (Features → Location) y qué comprobar: la hoja inferior, la ficha, los controles abajo y que la muesca y la barra inferior no tapan nada, en vertical y en horizontal

