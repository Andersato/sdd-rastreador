# Spec Delta

## Purpose

Completar la ficha de una gasolinera en la página del mapa con su horario,
los precios de todos sus combustibles y un enlace «Cómo llegar» a la
aplicación de mapas del dispositivo, pidiendo el detalle al servidor de
forma justa y sin enviar la ubicación de quien busca a nadie más.

## ADDED Requirements

### Requirement: Carga del detalle al abrir la ficha
Al abrir la ficha de una gasolinera, la página SHALL pedir
`GET /api/stations/{id}` con su identificador, salvo que ya tenga su detalle
de esta búsqueda. Mientras llega, la ficha MUST mostrar ya los datos de la
búsqueda y «Cargando horario…» en la zona del horario y los precios. Al
llegar, solo añade horario y precios: rótulo, dirección, municipio, precio y
distancia siguen siendo los de la búsqueda.

#### Scenario: Abrir la ficha
- **WHEN** en un iPhone la búsqueda en Madrid muestra "4375" (REPSOL, CALLE MAYOR, 1, Madrid, Gasoleo A a 1.459, 0.04 km) y se toca su marcador
- **THEN** se pide una vez `GET /api/stations/4375`, y antes de que llegue la ficha ya muestra «REPSOL», «CALLE MAYOR, 1», «Madrid», «1,459 €/l», «0,0 km» y «Cargando horario…»

#### Scenario: Llega el detalle
- **WHEN** la respuesta de `/api/stations/4375` es 200 con `schedule` «L-D: 24H» y `prices` `gasoleo-a` 1.459 €/l y `gasolina-95-e5` 1.529 €/l
- **THEN** «Cargando horario…» desaparece, se ven el horario «L-D: 24H» y los dos precios, y el rótulo, la dirección, el municipio, el precio y la distancia de la búsqueda no cambian

#### Scenario: Detalle con datos fijos distintos
- **WHEN** la búsqueda trae "4375" con rótulo «REPSOL» y el detalle trae `brand` «REPSOL BUTANO»
- **THEN** la ficha sigue mostrando «REPSOL»

#### Scenario: Identificador con caracteres especiales (solo con la API simulada)
- **WHEN** se abre la ficha de una gasolinera con `id` «12/3?x»
- **THEN** se pide `/api/stations/12%2F3%3Fx`, codificado como un solo segmento de la ruta

#### Scenario: Gasolinera de la búsqueda sin identificador válido
- **WHEN** se abre la ficha de una gasolinera de la búsqueda cuyo `id` es `null`, `""` o el número `4375`
- **THEN** no se pide ningún `/api/stations/…`, la zona del horario muestra «El servidor ha dado una respuesta inesperada» sin «Reintentar», y los datos de la búsqueda y «Cómo llegar» se ven con normalidad

### Requirement: Horario tal como lo publica el Ministerio
La ficha SHALL mostrar el `schedule` del detalle sin interpretarlo, partido
por «;» en tramos, uno por línea, en el mismo orden, sin espacios al
principio ni al final de cada tramo y sin tramos vacíos. Sin horario
(`null`, que no es texto o sin ningún tramo tras partirlo) dice «Horario no disponible». Textos largos
se parten sin scroll horizontal.

#### Scenario: Varios tramos
- **WHEN** el horario es «L-J: 06:00-22:30; V: 06:00-23:00; S: 06:45-23:00; D: 07:45-22:30»
- **THEN** la ficha muestra cuatro líneas, en este orden: «L-J: 06:00-22:30», «V: 06:00-23:00», «S: 06:45-23:00» y «D: 07:45-22:30»

#### Scenario: Un solo tramo
- **WHEN** el horario es «L-D: 24H»
- **THEN** la ficha muestra una sola línea «L-D: 24H»

#### Scenario: Dos franjas en un mismo día
- **WHEN** el horario es «L-V: 09:00-13:30 y 16:00-18:30; S: 09:00-13:30»
- **THEN** la ficha muestra dos líneas: «L-V: 09:00-13:30 y 16:00-18:30» y «S: 09:00-13:30»; « y » no parte el tramo

#### Scenario: Abreviatura ambigua sin traducir
- **WHEN** el horario es «L: 24H»
- **THEN** la ficha muestra una sola línea «L: 24H» exactamente así, sin traducir «L» ni suponer que abre todos los días

#### Scenario: Tramos vacíos y espacios
- **WHEN** el horario es «L-V: 07:00-22:00;;  S: 08:00-14:00 ; »
- **THEN** la ficha muestra dos líneas: «L-V: 07:00-22:00» y «S: 08:00-14:00»

#### Scenario: Formato raro sin interpretar
- **WHEN** el horario es «L: 06:30-22:30; M-D: 06:30-14:29 y 14:30-22:30 (festivos cerrado)»
- **THEN** la ficha muestra «L: 06:30-22:30» y «M-D: 06:30-14:29 y 14:30-22:30 (festivos cerrado)» exactamente así, sin traducir abreviaturas, y no aparece ningún «Abierta» ni «Cerrada»

#### Scenario: Sin horario
- **WHEN** el detalle trae `schedule` `null`, «;», o el número `24`
- **THEN** la ficha dice «Horario no disponible» y muestra los precios con normalidad

#### Scenario: Horario largo en el móvil
- **WHEN** en una ventana de 320×568 el horario es un solo tramo de 200 caracteres sin espacios
- **THEN** no aparece scroll horizontal, el tramo se parte en varias líneas dentro de la ficha y «Cerrar» y «Cómo llegar» se siguen viendo enteros

### Requirement: Precios de todos los combustibles de la gasolinera
La ficha SHALL listar los precios de `prices` del detalle con nombre, precio
y unidad en el formato de `map-view` («Gasolina 95 E5 · 1,529 €/l»). El
combustible buscado va el primero, con el texto «Buscado» y destacado; los
demás, en el orden recibido. El buscado es el de `slug` igual al combustible
de la búsqueda. Se ignoran los elementos sin `slug`, `name` o
`unit` como texto, o sin `price` numérico finito mayor que 0.

#### Scenario: Buscado el primero
- **WHEN** se busca Gasolina 95 E5 y el detalle de "4375" trae `adblue` 0.899 €/l, `gasoleo-a` 1.459 €/l y `gasolina-95-e5` 1.529 €/l
- **THEN** la ficha lista, en este orden, «Gasolina 95 E5 · 1,529 €/l» con «Buscado», «Adblue · 0,899 €/l» y «Gasoleo A · 1,459 €/l», y solo la primera lleva «Buscado»

#### Scenario: Otra unidad
- **WHEN** el detalle trae `hidrogeno` 12.95 €/kg y `gasoleo-a` 1.459 €/l
- **THEN** se ven «Hidrogeno · 12,950 €/kg» y «Gasoleo A · 1,459 €/l»

#### Scenario: Destacado sin depender del color
- **WHEN** se revisa la ficha anterior
- **THEN** el elemento de Gasolina 95 E5 es el primero de la lista y contiene el texto «Buscado» en su contenido visible y en su nombre accesible, y ningún otro elemento lo contiene

#### Scenario: Sin precios
- **WHEN** el detalle trae `"prices": []`
- **THEN** la ficha dice «No hay precios de esta gasolinera en la última captura» y muestra el horario

#### Scenario: El buscado ya no aparece
- **WHEN** se busca Gasoleo A y el detalle solo trae `gasolina-95-e5` 1.529 €/l
- **THEN** la ficha lista «Gasolina 95 E5 · 1,529 €/l» sin «Buscado», y el precio de la búsqueda («1,459 €/l») sigue arriba

#### Scenario: Elementos no válidos
- **WHEN** `prices` trae `gasoleo-a` 1.459 €/l, uno sin `name`, uno con `price` `null`, uno con `price` `"1,5"` y uno con `price` 0
- **THEN** la ficha lista solo «Gasoleo A · 1,459 €/l», sin avisar de los descartados

#### Scenario: Ningún precio válido
- **WHEN** `prices` trae dos elementos, uno sin `name` y otro con `price` `null`
- **THEN** la ficha trata la respuesta como inesperada (requisito «Errores del detalle»): «El servidor ha dado una respuesta inesperada» con «Reintentar», sin horario ni «No hay precios…»

#### Scenario: Precio del buscado distinto en una captura más nueva
- **WHEN** se busca Gasoleo A, la búsqueda trae "4375" a 1.459 con `capture.downloaded_at` `2026-10-16T07:26:37Z`, y su detalle trae `gasoleo-a` 1.479 con `capture.downloaded_at` `2026-10-16T08:26:40Z`
- **THEN** arriba la ficha sigue mostrando «1,459 €/l», la lista muestra el primero «Gasoleo A · 1,479 €/l» con «Buscado», y se ve el aviso «Horario y precios de una captura más reciente: del 16/10/2026 a las 10:26 (hora de Madrid)»

#### Scenario: Precios no es una lista
- **WHEN** el detalle trae `prices` `null` o un objeto, o `data` no tiene `prices`
- **THEN** la ficha trata la respuesta como inesperada (requisito «Errores del detalle»)

### Requirement: Captura del detalle más nueva que la de la búsqueda
Si `capture.downloaded_at` del detalle y el de la búsqueda son fechas válidas
y la del detalle es posterior, la ficha SHALL decir «Horario y precios de una
captura más reciente: del DD/MM/AAAA a las HH:MM (hora de Madrid)». En
cualquier otro caso (iguales, la del detalle anterior, o alguna que falta o
no se entiende) no dice nada más.

#### Scenario: Captura nueva entre la búsqueda y la ficha
- **WHEN** la búsqueda tiene `capture.downloaded_at` `2026-10-16T07:26:37Z` y el detalle `2026-10-16T08:26:40Z`, con el navegador en la zona horaria UTC
- **THEN** la ficha dice «Horario y precios de una captura más reciente: del 16/10/2026 a las 10:26 (hora de Madrid)»

#### Scenario: Misma captura
- **WHEN** las dos tienen `capture.downloaded_at` `2026-10-16T07:26:37Z`
- **THEN** la ficha no muestra ese aviso

#### Scenario: Captura del detalle desconocida
- **WHEN** el detalle no trae `capture` o trae `downloaded_at` «ayer»
- **THEN** la ficha no muestra ese aviso y muestra horario y precios

#### Scenario: Captura del detalle anterior
- **WHEN** la búsqueda tiene `capture.downloaded_at` `2026-10-16T08:26:40Z` y el detalle `2026-10-16T07:26:37Z` (por ejemplo, tras restaurar una copia de la base)
- **THEN** la ficha no muestra ese aviso y muestra horario y precios

#### Scenario: Búsqueda sin fecha de captura
- **WHEN** la página dice «Fecha de la captura desconocida» y el detalle trae `capture.downloaded_at` `2026-10-16T08:26:40Z`
- **THEN** la ficha no muestra ese aviso

### Requirement: Una petición por gasolinera y búsqueda
La página SHALL hacer como mucho una petición de detalle por gasolinera y
búsqueda, más una por cada pulsación de «Reintentar» del detalle: reabrir
una ficha reutiliza su respuesta, la que está en camino o su error. Al
lanzarse cualquier búsqueda nueva (también la que provoca la ubicación del
navegador) se olvidan los detalles y se descartan los que estén en camino.

#### Scenario: Reabrir la misma ficha
- **WHEN** se abre la ficha de "4375", llega su detalle, se cierra y se vuelve a abrir desde la lista
- **THEN** se ha pedido `/api/stations/4375` una sola vez, y al reabrirla horario y precios se ven sin «Cargando horario…»

#### Scenario: Reabrir mientras llega
- **WHEN** se abre "4375", su detalle tarda 2 s, se cierra la ficha al primer segundo y se reabre
- **THEN** no se hace otra petición, se ve «Cargando horario…» y, al llegar, el detalle aparece en la ficha

#### Scenario: Tres fichas
- **WHEN** se abren y cierran las fichas de "1001", "1002" y "1003", y después otra vez la de "1001"
- **THEN** se han pedido `/api/stations/1001`, `/api/stations/1002` y `/api/stations/1003` una vez cada una, y ninguna más

#### Scenario: Nueva búsqueda
- **WHEN** llegó el detalle de "4375", se cambia el radio a 25 km, la búsqueda vuelve a traer "4375" y se abre su ficha
- **THEN** se pide `/api/stations/4375` otra vez, una sola

#### Scenario: Respuesta de una búsqueda anterior
- **WHEN** se abre "4375", su detalle tarda 2 s, y antes de que llegue se pincha en otro punto cuya búsqueda vuelve a traer "4375" y se abre su ficha
- **THEN** se hace una petición nueva de `/api/stations/4375` y la ficha muestra solo la respuesta de esta última, aunque la anterior llegue después

#### Scenario: Página quieta con la ficha abierta
- **WHEN** la ficha de "4375" muestra su detalle y no se toca nada durante 5 minutos
- **THEN** no se hace ninguna petición a `/api/` en ese tiempo

### Requirement: Sin respuestas de otra ficha
La ficha abierta SHALL mostrar solo el detalle de su gasolinera. Si se abre
otra ficha antes de que llegue una respuesta, esa respuesta se guarda para
su gasolinera pero MUST NOT aparecer en la ficha nueva.

#### Scenario: Cambiar de ficha antes de la respuesta
- **WHEN** se abre "1001", su detalle tarda 2 s (horario «L-D: 24H»), antes se abre "1002", cuyo detalle llega enseguida (horario «L-S: 07:00-21:00»), y después llega el de "1001"
- **THEN** la ficha de "1002" muestra solo «L-S: 07:00-21:00» y sus precios, en ningún momento «L-D: 24H», y al volver a abrir "1001" se ve «L-D: 24H» sin otra petición

#### Scenario: Respuesta con otro identificador
- **WHEN** se pide `/api/stations/1001` y la respuesta 200 trae `data.id` «1002», el número `1001` o no trae `id`
- **THEN** en los tres casos la ficha de "1001" la trata como inesperada y no muestra su horario ni sus precios

#### Scenario: Cerrar antes de la respuesta
- **WHEN** se abre "1001", se cierra antes de que llegue su detalle y la lista queda a la vista
- **THEN** al llegar no se abre ninguna ficha ni cambia la lista

### Requirement: Límite de tiempo del detalle
Una petición de detalle que no responde en 15 s SHALL darse por fallida,
como en el resto de la página.

#### Scenario: Detalle que no contesta
- **WHEN** `/api/stations/4375` no contesta
- **THEN** a los 15 s (con un margen de 1 s) «Cargando horario…» se sustituye por «No se puede conectar con el servidor. Comprueba que está en marcha y que el túnel está abierto.» con «Reintentar», y los datos de la búsqueda siguen en la ficha

### Requirement: Errores del detalle
Si el detalle falla, la ficha SHALL seguir con los datos de la búsqueda y
«Cómo llegar», y mostrar en la zona del horario el mensaje y los criterios
que `map-view` da para ese fallo, con un «Reintentar» que solo pide el
detalle. 404 `estacion_no_encontrada` y otros errores JSON que no son 503:
«El servidor ha dado un error. Inténtalo más tarde.». No cambia la búsqueda.

#### Scenario: Ocupado con Retry-After
- **WHEN** `/api/stations/4375` responde 503 `base_ocupada` con `Retry-After: 5`
- **THEN** la ficha muestra «El servidor está ocupado; inténtalo en unos segundos» con «Reintentar» desactivado durante 5 s (con un margen de 0,5 s), y la petición no se repite sola

#### Scenario: Consulta demasiado larga
- **WHEN** `/api/stations/4375` responde 503 `consulta_demasiado_larga` sin `Retry-After`
- **THEN** la ficha muestra «El servidor está ocupado; inténtalo en unos segundos» con «Reintentar» desactivado durante 5 s

#### Scenario: Ocupado con otro Retry-After o uno raro
- **WHEN** `/api/stations/4375` responde 503 `api_ocupada` con `Retry-After: 12`, o 503 `base_ocupada` con `Retry-After: abc`
- **THEN** «Reintentar» del detalle está desactivado durante 12 s en el primer caso y 5 s en el segundo

#### Scenario: Reintentar con éxito
- **WHEN** tras el error anterior se activa y se tocan dos veces seguidas «Reintentar», y esta vez la respuesta tarda 1 s y es 200
- **THEN** se hace una sola petición, a `/api/stations/4375`, ninguna a `/api/stations/nearby` ni a `/api/fuels`; mientras llega se ve otra vez «Cargando horario…» sin «Reintentar», y después la ficha muestra el horario y los precios

#### Scenario: Sin datos
- **WHEN** `/api/stations/4375` responde 503 `sin_capturas` con el mensaje «todavía no hay capturas guardadas»
- **THEN** la ficha muestra «No hay datos disponibles. Detalle: todavía no hay capturas guardadas» con «Reintentar» activo

#### Scenario: Red caída
- **WHEN** la petición de `/api/stations/4375` falla por red
- **THEN** la ficha muestra «No se puede conectar con el servidor. Comprueba que está en marcha y que el túnel está abierto.» con «Reintentar»

#### Scenario: Respuesta que no es JSON
- **WHEN** `/api/stations/4375` responde 502 con una página HTML, o 200 con `data` que no es un objeto
- **THEN** la ficha muestra «El servidor ha dado una respuesta inesperada» con «Reintentar», sin el HTML recibido

#### Scenario: 503 que no es JSON
- **WHEN** `/api/stations/4375` responde 503 con una página HTML de un proxy
- **THEN** la ficha muestra «El servidor ha dado una respuesta inesperada» con «Reintentar», no «No hay datos disponibles»

#### Scenario: Gasolinera no encontrada
- **WHEN** `/api/stations/4375` responde 404 `estacion_no_encontrada`
- **THEN** la ficha muestra «El servidor ha dado un error. Inténtalo más tarde.» con «Reintentar», sin el mensaje ni el código recibidos

#### Scenario: Error interno
- **WHEN** `/api/stations/4375` responde 500 `error_interno`
- **THEN** la ficha muestra «El servidor ha dado un error. Inténtalo más tarde.» con «Reintentar»

#### Scenario: El resto de la página sigue igual
- **WHEN** el detalle de "4375" ha fallado y se cierra la ficha
- **THEN** la lista, los marcadores, el recuento y los avisos de la búsqueda son los mismos que antes de abrirla, y no aparece ningún mensaje de error fuera de la ficha

#### Scenario: Reabrir una ficha con error
- **WHEN** el detalle de "4375" falló por red, se cierra la ficha y se vuelve a abrir
- **THEN** no se hace otra petición y la ficha muestra el mismo mensaje con «Reintentar»

#### Scenario: Reabrir mientras «Reintentar» espera
- **WHEN** el detalle de "4375" respondió 503 `base_ocupada` con `Retry-After: 5`, a los 2 s se cierra la ficha y se reabre enseguida
- **THEN** no se hace otra petición, se ve «El servidor está ocupado; inténtalo en unos segundos» y «Reintentar» sigue desactivado hasta que se cumplen los 5 s desde el error (unos 3 s más, con un margen de 0,5 s), no 5 s desde la reapertura

#### Scenario: Textos sin la palabra API
- **WHEN** se recorren en la ficha los estados de carga, detalle correcto, sin horario, sin precios, captura más reciente y cada error de este requisito, y se recoge el texto visible propio de la página sin los datos de la gasolinera ni lo que sigue a «Detalle:»
- **THEN** en ningún caso aparece la palabra «API», en mayúsculas o minúsculas

### Requirement: Textos del detalle como texto
El horario, los nombres de los combustibles y el mensaje de error del
detalle SHALL mostrarse literalmente, nunca interpretados como HTML ni como
código.

#### Scenario: Horario con etiquetas
- **WHEN** el horario es `<img src=x onerror=alert(1)>; L-D: 24H`
- **THEN** la ficha muestra en dos líneas `<img src=x onerror=alert(1)>` y «L-D: 24H» tal cual, y no se ejecuta nada

#### Scenario: Nombre de combustible con etiquetas
- **WHEN** un precio trae `name` `<b>Gasoleo A</b>`
- **THEN** se ve con las etiquetas escritas, sin negrita

### Requirement: Enlace «Cómo llegar» según el dispositivo
La ficha SHALL tener un enlace «Cómo llegar» a la ruta hasta la gasolinera
en Google Maps si el agente de usuario contiene «Android»; si no, en Apple
Maps si contiene «iPhone», «iPad», «iPod» o «Macintosh»; si no, en
OpenStreetMap (sin distinguir mayúsculas). Usa las coordenadas de la
búsqueda, cada número con su escritura más corta (40.4400 → `40.44`), en
otra pestaña y sin clave ni cuenta.

#### Scenario: iPhone
- **WHEN** en el iPhone 13 en WebKit (agente de usuario con «iPhone») se abre la ficha de "1003" (40.4400, -3.7300)
- **THEN** «Cómo llegar» enlaza a `https://maps.apple.com/?daddr=40.44,-3.73`

#### Scenario: Mac
- **WHEN** en escritorio (1280×800) con un agente de usuario de Safari en Mac («Macintosh») se abre la ficha de "1003"
- **THEN** «Cómo llegar» enlaza a `https://maps.apple.com/?daddr=40.44,-3.73`

#### Scenario: iPad que se presenta como Mac
- **WHEN** el agente de usuario es el de un iPad con iPadOS («Macintosh», sin «iPad») y se abre la ficha de "1003"
- **THEN** «Cómo llegar» enlaza a Apple Maps

#### Scenario: Android
- **WHEN** en el Pixel 7 en Chromium (agente de usuario con «Android») se abre la ficha de "1003"
- **THEN** «Cómo llegar» enlaza a `https://www.google.com/maps/dir/?api=1&destination=40.44,-3.73`

#### Scenario: Otros dispositivos
- **WHEN** a 320×568 y en escritorio (1280×800), los dos en Chromium con un agente de usuario de Chrome en Linux, se abre la ficha de "1003"
- **THEN** «Cómo llegar» enlaza a `https://www.openstreetmap.org/directions?route=%3B40.44%2C-3.73`

#### Scenario: Coordenadas con muchos decimales
- **WHEN** en el iPhone se abre la ficha de "4375" (40.416775, -3.70379)
- **THEN** «Cómo llegar» enlaza a `https://maps.apple.com/?daddr=40.416775,-3.70379`

#### Scenario: Otra pestaña y sin claves
- **WHEN** se revisa el enlace «Cómo llegar» de cualquier ficha
- **THEN** es un enlace normal con `target="_blank"` y `rel="noopener noreferrer"`, y su dirección no lleva ninguna clave, token ni identificador de cuenta

#### Scenario: Disponible aunque falle el detalle
- **WHEN** se abre la ficha de "1003" y `/api/stations/1003` está cargando o ha fallado
- **THEN** «Cómo llegar» ya se ve y enlaza a la ruta de "1003"

#### Scenario: El enlace cambia con la ficha
- **WHEN** se abre la ficha de "1003" y después la de "4375"
- **THEN** «Cómo llegar» enlaza a la ruta de "4375", no a la de "1003"

### Requirement: «Cómo llegar» sin la ubicación de quien busca
El enlace «Cómo llegar» SHALL llevar solo las coordenadas de la gasolinera.
MUST NOT llevar la ubicación del navegador, el punto pinchado, el punto de
búsqueda ni la dirección de la página, y la página no pide nada a Apple,
Google u OpenStreetMap (fuera de las teselas) hasta que se pulsa.

#### Scenario: Sin la ubicación
- **WHEN** el navegador concede la ubicación (40.416775, -3.703790), la búsqueda trae "1003" (40.4400, -3.7300) y se abre su ficha
- **THEN** el enlace no contiene `40.41`, `-3.70`, `40.417` ni `-3.704`, y sí `40.44,-3.73`

#### Scenario: Sin el punto pinchado
- **WHEN** se pincha en (41.3874, 2.1686) y se abre la ficha de una gasolinera de Barcelona en (41.3900, 2.1700)
- **THEN** el enlace contiene `41.39,2.17` y no contiene `41.387`, `41.38`, `2.169` ni `2.16`

#### Scenario: Pulsar «Cómo llegar»
- **WHEN** en el iPhone se pulsa «Cómo llegar» en la ficha de "1003", con la navegación a `maps.apple.com` interceptada y cancelada por el test
- **THEN** se intenta abrir exactamente `https://maps.apple.com/?daddr=40.44,-3.73` en una pestaña nueva, sin cabecera `Referer`, y la página del mapa sigue igual, con la ficha abierta

#### Scenario: Sin peticiones hasta pulsar
- **WHEN** se abren y cierran fichas sin pulsar «Cómo llegar», registrando las peticiones
- **THEN** ninguna va a `maps.apple.com`, `www.google.com` ni `www.openstreetmap.org`

### Requirement: Ficha completa mobile first
En el móvil la ficha SHALL seguir siendo la hoja inferior de `map-view` y,
en el escritorio, el panel lateral. «Cerrar» y «Cómo llegar» van en la fila
de acciones fija al pie de la ficha, siempre a la vista; horario y precios
se desplazan dentro de la ficha. «Cómo llegar», «Cerrar» y el «Reintentar»
del detalle miden al menos 44×44 px.

#### Scenario: Ficha completa en un iPhone
- **WHEN** en un iPhone (390×664) se abre la ficha de "4375" con horario de cuatro tramos y cinco precios
- **THEN** la ficha mide como mucho el 70 % del alto, horario y precios se desplazan dentro de ella, «Cómo llegar» y «Cerrar» se ven enteros en la mitad inferior de la pantalla sin desplazar nada, no hay globo sobre el mapa y el marcador de "4375" queda en la zona visible del mapa

#### Scenario: En horizontal
- **WHEN** en un iPhone en horizontal (750×342) se abre esa misma ficha
- **THEN** la ficha mide como mucho el 70 % del alto, «Cómo llegar» y «Cerrar» se ven enteros sin desplazar nada, no aparece scroll de la página, las dos atribuciones se ven enteras sin que la ficha las tape y el marcador de "4375" queda en la zona visible del mapa

#### Scenario: Teléfono pequeño
- **WHEN** en una ventana de 320×568 se abre la ficha de una gasolinera con rótulo de 80 caracteres, horario de cuatro tramos y cinco precios
- **THEN** no aparece scroll horizontal, cada precio, al desplazarse hasta él dentro de la ficha, se ve entero sin cortarse en horizontal, «Cómo llegar» y «Cerrar» se ven enteros y las dos atribuciones se ven enteras sin que la ficha las tape

#### Scenario: Android
- **WHEN** en el Pixel 7 (412×839) se toca un marcador, se espera el detalle y se toca «Cerrar»
- **THEN** la ficha se abre con horario y precios y se cierra igual que con clics

#### Scenario: Escritorio
- **WHEN** en una ventana de 1280×800 se pulsa "4375"
- **THEN** la ficha completa aparece en el panel lateral, encima de la lista, con «Cómo llegar» y «Cerrar» visibles y sin globo sobre el mapa

#### Scenario: Objetivos táctiles
- **WHEN** se miden «Cómo llegar», «Cerrar» y el «Reintentar» del detalle a 320×568 y a 1280×800
- **THEN** cada uno mide al menos 44 px de alto y 44 px de ancho

#### Scenario: Girar con el detalle cargado
- **WHEN** en un iPhone en vertical con la ficha de "4375" y su detalle cargado se pasa a horizontal y otra vez a vertical
- **THEN** la ficha sigue abierta con horario y precios, «Cómo llegar» y «Cerrar» se ven, y no se hace ninguna petición

#### Scenario: Zonas seguras
- **WHEN** se revisan las hojas de estilo
- **THEN** la fila de acciones de la ficha queda dentro del relleno con `env(safe-area-inset-bottom)`, `env(safe-area-inset-left)` y `env(safe-area-inset-right)`, y no se usa `vh` sin `d`

### Requirement: Accesibilidad de la ficha completa
Una zona de estado del detalle SHALL anunciar a los lectores de pantalla solo
un texto corto («Cargando horario…», «Ficha cargada» o el
mensaje de error), sin leer horario ni precios. La ficha no atrapa el foco.
Tras «Reintentar» del detalle, el foco pasa a esa zona. El nombre accesible
de «Cómo llegar» nombra el destino; el texto visible es solo «Cómo llegar».

#### Scenario: Llega el detalle
- **WHEN** se abre la ficha de "4375" con el teclado y llega su detalle
- **THEN** el foco sigue en «Cerrar», y la zona de estado, que los lectores anuncian al cambiar, dice primero «Cargando horario…» y después «Ficha cargada»; el horario y los precios no están dentro de esa zona

#### Scenario: Ficha cargada sin horario ni precios
- **WHEN** el detalle de "4375" llega con `schedule` `null` y `"prices": []`
- **THEN** la zona de estado dice «Ficha cargada», y la ficha muestra «Horario no disponible» y «No hay precios de esta gasolinera en la última captura» fuera de esa zona

#### Scenario: Reabrir una ficha ya cargada
- **WHEN** llegó el detalle de "4375", se cierra la ficha y se vuelve a abrir
- **THEN** no se hace ninguna petición y la zona de estado dice «Ficha cargada» desde que se abre, sin pasar por «Cargando horario…»

#### Scenario: Error anunciado
- **WHEN** el detalle de "4375" falla por red
- **THEN** la zona de estado dice «No se puede conectar con el servidor. Comprueba que está en marcha y que el túnel está abierto.»

#### Scenario: Orden con el tabulador
- **WHEN** en una ventana de 1280×800, con la ficha de "4375" abierta y su detalle con error, el foco está en «Cerrar» y se pulsa Tab, y después Mayús+Tab dos veces
- **THEN** con Tab se llega a «Cómo llegar»; con Mayús+Tab se vuelve a «Cerrar» y después a «Reintentar»; y un Tab más desde «Cómo llegar» saca el foco de la ficha

#### Scenario: Foco tras «Reintentar»
- **WHEN** se pulsa «Reintentar» del detalle con el teclado
- **THEN** el foco pasa a la zona de estado del detalle (que dice «Cargando horario…»), no a `body`, y se queda ahí cuando llega la respuesta

#### Scenario: Nombre de «Cómo llegar»
- **WHEN** se revisa el enlace en el iPhone, en el Pixel 7 y en escritorio con un agente de usuario de Chrome en Linux
- **THEN** su texto visible es «Cómo llegar» y su nombre accesible es, respectivamente, «Cómo llegar con Apple Maps (se abre en otra pestaña)», «Cómo llegar con Google Maps (se abre en otra pestaña)» y «Cómo llegar con OpenStreetMap (se abre en otra pestaña)»
