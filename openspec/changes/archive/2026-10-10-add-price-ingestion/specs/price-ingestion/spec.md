# Spec Delta

## Purpose

Descargar los precios actuales de todas las gasolineras de España desde la API
del Ministerio y guardarlos como una captura con fecha y hora, para construir
un histórico propio de precios que la API no ofrece.

## ADDED Requirements

### Requirement: Descarga única de precios en JSON
Cada ejecución de la ingesta SHALL hacer una única petición a
`https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/`
con la cabecera `Accept: application/json`. Seguir las redirecciones HTTP de
esa petición cuenta como la misma petición. La ingesta MUST NOT reintentar la
petición dentro de la misma ejecución, ni siquiera si falla.

#### Scenario: Ejecución normal
- **WHEN** se lanza la ingesta y la API responde con HTTP 200 y un JSON válido
- **THEN** se ha hecho una única petición, con la cabecera `Accept: application/json`

#### Scenario: Redirección
- **WHEN** la API responde con HTTP 301 hacia otra URL, y esa URL responde con HTTP 200 y un JSON válido
- **THEN** la ingesta sigue la redirección, procesa la respuesta y no hace ninguna otra petición

#### Scenario: Fallo sin reintento
- **WHEN** se lanza la ingesta y la API responde con HTTP 503
- **THEN** no se hace ninguna segunda petición y la ejecución termina con error

### Requirement: Tiempo límite de la descarga
La descarga SHALL tener un tiempo límite. Si la API no ha terminado de
responder al agotarse, la ingesta MUST abandonar la descarga sin reintentarla
y terminar con error, sin guardar nada.

#### Scenario: Tiempo agotado
- **WHEN** la API no termina de responder antes de que se agote el tiempo límite
- **THEN** la ejecución termina con error indicando que se agotó el tiempo, no se hace ninguna otra petición y la base de datos queda exactamente igual que antes

### Requirement: Conversión de números con coma decimal
La ingesta SHALL convertir los precios y las coordenadas que llegan como texto
con coma decimal a valores numéricos. Se ignora cualquier espacio en blanco al
principio y al final (espacios, tabuladores, saltos de línea, espacios no
separables), y se acepta cualquier número de decimales. Un número escrito con
punto decimal se considera formato inválido.

#### Scenario: Precio con coma decimal
- **WHEN** una estación trae `"Precio Gasoleo A": "1,459"`
- **THEN** se guarda el precio numérico 1.459 para el combustible "Gasoleo A"

#### Scenario: Coordenadas con coma decimal y signo negativo
- **WHEN** una estación trae `"Latitud": "40,416775"` y `"Longitud (WGS84)": "-3,703790"`
- **THEN** la estación queda con latitud 40.416775 y longitud -3.70379

#### Scenario: Espacios alrededor y más decimales
- **WHEN** una estación trae `"Precio Gasolina 95 E5": " 1,5290 "`
- **THEN** se guarda el precio numérico 1.529 para "Gasolina 95 E5"

#### Scenario: Tabuladores y saltos de línea alrededor
- **WHEN** una estación trae `"Precio Gasoleo A": "\t1,459\n"`
- **THEN** se guarda el precio numérico 1.459 para "Gasoleo A", sin aviso

#### Scenario: Punto decimal
- **WHEN** una estación trae `"Precio Gasoleo A": "1.459"`
- **THEN** ese precio se trata como formato inválido: no se guarda y se registra un aviso con la estación, "Gasoleo A" y "1.459" (ver "Precios inválidos")

### Requirement: Precio vacío o ausente significa que no vende ese combustible
Un precio vacío, con solo espacios, `null`, o un campo `Precio ...` que no
aparece en la estación SHALL interpretarse como "la estación no vende ese combustible":
la ingesta MUST NOT guardar ningún precio para ese combustible en esa captura,
MUST NOT guardarlo como 0 y MUST NOT generar ningún aviso.

#### Scenario: Combustible sin precio
- **WHEN** una estación trae `"Precio Gasoleo A": "1,459"` y `"Precio Hidrogeno": ""`
- **THEN** la captura guarda el precio de "Gasoleo A" para esa estación y no guarda ningún precio de "Hidrogeno" (ni 0 ni vacío)

#### Scenario: Precio con solo espacios
- **WHEN** una estación trae `"Precio Gasolina 98 E5": "   "`
- **THEN** se trata igual que un precio vacío y no se guarda ningún precio de "Gasolina 98 E5"

#### Scenario: Campo de precio ausente
- **WHEN** una estación trae `"Precio Gasoleo A": "1,459"` y no trae la clave `Precio Hidrogeno`
- **THEN** la captura guarda el precio de "Gasoleo A", no guarda ningún precio de "Hidrogeno" y no se genera ningún aviso

#### Scenario: Precio null
- **WHEN** una estación trae `"Precio Gasoleo A": "1,459"` y `"Precio Hidrogeno": null`
- **THEN** la captura guarda el precio de "Gasoleo A", no guarda ningún precio de "Hidrogeno" y no se genera ningún aviso

#### Scenario: Estación sin ningún precio
- **WHEN** una estación trae todos sus campos `Precio ...` vacíos
- **THEN** sus datos fijos se registran o actualizan, pero la captura no contiene ningún precio de esa estación

### Requirement: Combustibles guardados
La ingesta SHALL guardar el precio de cada campo de la estación cuyo nombre
empiece por `Precio `, identificando el combustible por el resto del nombre
(por ejemplo `Precio Gasolina 95 E5` → "Gasolina 95 E5"), tal y como lo
nombra la API.

#### Scenario: Varios combustibles en una estación
- **WHEN** una estación trae `"Precio Gasolina 95 E5": "1,529"`, `"Precio Gasoleo A": "1,459"` y `"Precio Gases licuados del petróleo": "0,899"`
- **THEN** la captura guarda tres precios para esa estación: "Gasolina 95 E5" = 1.529, "Gasoleo A" = 1.459 y "Gases licuados del petróleo" = 0.899

### Requirement: Precios inválidos
Un precio con formato inválido (incluido un valor que no es texto ni `null`,
como un número JSON), igual a 0 o negativo SHALL descartarse: la
ingesta MUST NOT guardar ese precio, MUST guardar el resto de precios y datos
de esa estación y MUST registrar un aviso que indique la estación, el
combustible y el valor recibido. Un precio inválido no impide guardar la
captura.

#### Scenario: Precio con formato inesperado
- **WHEN** la estación "4375" trae `"Precio Gasoleo A": "1,4a9"` y `"Precio Gasolina 95 E5": "1,529"`
- **THEN** la captura guarda "Gasolina 95 E5" = 1.529 para "4375", no guarda ningún precio de "Gasoleo A" para "4375" y se registra un aviso con "4375", "Gasoleo A" y "1,4a9"

#### Scenario: Precio que no es texto
- **WHEN** la estación "4375" trae `"Precio Gasoleo A": 1.459` (número JSON, no texto)
- **THEN** no se guarda ningún precio de "Gasoleo A" para "4375" y se registra un aviso con "4375", "Gasoleo A" y el valor recibido

#### Scenario: Precio cero
- **WHEN** la estación "4375" trae `"Precio Gasoleo A": "0,000"`
- **THEN** no se guarda ningún precio de "Gasoleo A" para "4375" (tampoco 0) y se registra un aviso

#### Scenario: Precio negativo
- **WHEN** la estación "4375" trae `"Precio Gasoleo A": "-1,459"`
- **THEN** no se guarda ningún precio de "Gasoleo A" para "4375" y se registra un aviso

### Requirement: Datos fijos de la estación separados de los precios
La ingesta SHALL guardar los datos fijos de cada estación (identificador del
Ministerio `IDEESS`, rótulo, dirección, municipio, provincia, latitud,
longitud y horario) separados de los precios, de modo que cada estación exista
una sola vez aunque aparezca en muchas capturas. Un dato fijo de texto vacío,
`null` o ausente se guarda vacío, y uno que llega como número se guarda
convertido a texto, ambos sin aviso. Los textos se guardan tal como llegan;
al `IDEESS` se le quitan los espacios en blanco de alrededor.

#### Scenario: Estación nueva
- **WHEN** la API trae la estación con `"IDEESS": "4375"`, `"Rótulo": "REPSOL"`, `"Dirección": "CALLE MAYOR, 1"`, `"Municipio": "Madrid"`, `"Provincia": "MADRID"`, `"Latitud": "40,416775"`, `"Longitud (WGS84)": "-3,703790"`, `"Horario": "L-D: 24H"` y no existe en la base de datos
- **THEN** se registra una estación con identificador "4375", rótulo "REPSOL", dirección "CALLE MAYOR, 1", municipio "Madrid", provincia "MADRID", latitud 40.416775, longitud -3.70379 y horario "L-D: 24H"

#### Scenario: Dato fijo de texto vacío o ausente
- **WHEN** la estación nueva "5120" trae `"Rótulo": ""`, `"Dirección": null` y no trae la clave `Horario`
- **THEN** se registra la estación "5120" con rótulo, dirección y horario vacíos, con sus precios, y sin ningún aviso

#### Scenario: Dato fijo de texto que llega como número
- **WHEN** la estación nueva "5120" trae `"Rótulo": 123`
- **THEN** se registra con rótulo "123", sin aviso

#### Scenario: Textos con espacios
- **WHEN** la estación nueva "5120" trae `"Rótulo": " GALP "`
- **THEN** se registra con rótulo " GALP ", tal cual

#### Scenario: Identificador con espacios
- **WHEN** existe la estación "4375" y una nueva ingesta trae `"IDEESS": " 4375 "`
- **THEN** se actualiza la estación "4375"; no se crea ninguna estación " 4375 "

### Requirement: Coordenadas inválidas
Una latitud o longitud vacía, ausente, `null`, que no es texto, con formato
inválido o fuera de rango (latitud -90 a 90 y longitud -180 a 180, extremos
incluidos) SHALL descartar las dos coordenadas de esa estación y MUST registrar
un aviso por cada campo con problema, con la estación, el campo y el valor
recibido (`(ausente)` si no venía). El
resto de sus datos y sus precios se guardan igualmente. Una estación nueva
queda sin coordenadas; una existente conserva las que ya tenía.

#### Scenario: Latitud con formato inválido en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": "abc"`, `"Longitud (WGS84)": "-3,703790"` y `"Precio Gasoleo A": "1,459"`
- **THEN** se registra "4375" sin latitud ni longitud, la captura guarda "Gasoleo A" = 1.459 para "4375" y se registra un aviso con "4375", "Latitud" y "abc"

#### Scenario: Latitud fuera de rango en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": "123,000000"` y `"Longitud (WGS84)": "-3,703790"`
- **THEN** se registra sin coordenadas, con sus precios, y se registra un aviso con "4375", "Latitud" y "123,000000"

#### Scenario: Longitud con formato inválido en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": "40,416775"` y `"Longitud (WGS84)": "-3,70x790"`
- **THEN** se registra sin coordenadas (tampoco la latitud), con sus precios, y se registra un aviso con "4375", "Longitud (WGS84)" y "-3,70x790"

#### Scenario: Longitud fuera de rango en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": "40,416775"` y `"Longitud (WGS84)": "-190,000000"`
- **THEN** se registra sin coordenadas, con sus precios, y se registra un aviso con "4375", "Longitud (WGS84)" y "-190,000000"

#### Scenario: Extremos del rango
- **WHEN** la estación nueva "9001" trae `"Latitud": "-90,000000"` y `"Longitud (WGS84)": "180,000000"`
- **THEN** se registra con latitud -90 y longitud 180, sin aviso

#### Scenario: Coordenada vacía en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": ""` y `"Longitud (WGS84)": "-3,703790"`
- **THEN** se registra sin coordenadas, con sus precios, y se registra un aviso con "4375" y "Latitud"

#### Scenario: Las dos coordenadas inválidas
- **WHEN** la estación nueva "4375" trae `"Latitud": "abc"` y no trae la clave `Longitud (WGS84)`
- **THEN** se registra sin coordenadas, con sus precios, y se registran dos avisos: uno con "4375", "Latitud" y "abc", y otro con "4375", "Longitud (WGS84)" y "(ausente)"

#### Scenario: Coordenada ausente en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": "40,416775"` y no trae la clave `Longitud (WGS84)`
- **THEN** se registra sin coordenadas (tampoco la latitud), con sus precios, y se registra un aviso con "4375", "Longitud (WGS84)" y "(ausente)"

#### Scenario: Coordenada null en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": null` y `"Longitud (WGS84)": "-3,703790"`
- **THEN** se registra sin coordenadas, con sus precios, y se registra un aviso con "4375" y "Latitud"

#### Scenario: Coordenada que no es texto en estación nueva
- **WHEN** la estación nueva "4375" trae `"Latitud": 40.416775` (número JSON) y `"Longitud (WGS84)": "-3,703790"`
- **THEN** se registra sin coordenadas, con sus precios, y se registra un aviso con "4375" y "Latitud"

#### Scenario: Coordenada inválida en estación existente
- **WHEN** existe la estación "4375" con latitud 40.416775 y longitud -3.70379, y una nueva ingesta trae "4375" con `"Latitud": "abc"`, `"Longitud (WGS84)": "-3,703500"`, `"Rótulo": "CEPSA"` y `"Precio Gasoleo A": "1,459"`
- **THEN** "4375" conserva latitud 40.416775 y longitud -3.70379, su rótulo pasa a "CEPSA", la captura guarda "Gasoleo A" = 1.459 y se registra un aviso con "4375", "Latitud" y "abc"

#### Scenario: Coordenada vacía en estación existente
- **WHEN** existe la estación "4375" con latitud 40.416775 y longitud -3.70379, y una nueva ingesta trae "4375" con `"Latitud": "40,416900"` y `"Longitud (WGS84)": ""`
- **THEN** "4375" conserva latitud 40.416775 y longitud -3.70379, con sus precios de esta captura, y se registra un aviso con "4375" y "Longitud (WGS84)"

#### Scenario: Coordenada ausente en estación existente
- **WHEN** existe la estación "4375" con latitud 40.416775 y longitud -3.70379, y una nueva ingesta trae "4375" sin la clave `Latitud` y con `"Longitud (WGS84)": "-3,703500"`
- **THEN** "4375" conserva latitud 40.416775 y longitud -3.70379, con sus precios de esta captura, y se registra un aviso con "4375", "Latitud" y "(ausente)"

#### Scenario: Coordenada inválida en estación existente sin coordenadas
- **WHEN** existe la estación "4375" sin coordenadas y una nueva ingesta trae "4375" con `"Latitud": "abc"` y `"Longitud (WGS84)": "-3,703790"`
- **THEN** "4375" sigue sin coordenadas y se registra un aviso con "4375", "Latitud" y "abc"

#### Scenario: Coordenadas de Canarias
- **WHEN** la estación "8001" trae `"Latitud": "28,123546"` y `"Longitud (WGS84)": "-15,436257"`
- **THEN** se guarda con latitud 28.123546 y longitud -15.436257, sin aviso

### Requirement: Actualización de estaciones existentes sin duplicarlas
Si una estación con el mismo `IDEESS` ya existe, la ingesta SHALL sustituir
sus datos fijos de texto por los recibidos en esta ejecución, aunque vengan
vacíos, y MUST NOT crear una segunda estación. Excepción: las coordenadas
solo se sustituyen si las nuevas son válidas; si no, se conservan las
anteriores (ver "Coordenadas inválidas"). Los precios de capturas anteriores
MUST conservarse.

#### Scenario: Cambio de rótulo y horario
- **WHEN** existe la estación "4375" con rótulo "REPSOL" y horario "L-D: 24H", y una nueva ingesta trae "4375" con rótulo "CEPSA" y horario "L-S: 07:00-22:00"
- **THEN** sigue existiendo una única estación "4375", ahora con rótulo "CEPSA" y horario "L-S: 07:00-22:00", y sus precios de capturas anteriores siguen intactos

#### Scenario: Cambio de dirección y coordenadas
- **WHEN** existe la estación "4375" con dirección "CALLE MAYOR, 1", latitud 40.416775 y longitud -3.70379, y una nueva ingesta trae "4375" con `"Dirección": "CALLE MAYOR, 3"`, `"Latitud": "40,416900"` y `"Longitud (WGS84)": "-3,703500"`
- **THEN** sigue existiendo una única estación "4375", con dirección "CALLE MAYOR, 3", latitud 40.4169 y longitud -3.7035

#### Scenario: Dato fijo que llega vacío
- **WHEN** existe la estación "4375" con horario "L-D: 24H" y una nueva ingesta trae "4375" con `"Horario": ""`
- **THEN** la estación "4375" queda con horario vacío

#### Scenario: Las coordenadas no se vacían al actualizar
- **WHEN** existe la estación "4375" con horario "L-D: 24H", latitud 40.416775 y longitud -3.70379, y una nueva ingesta trae "4375" con `"Horario": ""`, `"Latitud": ""` y `"Longitud (WGS84)": "-3,703500"`
- **THEN** la estación "4375" queda con horario vacío pero conserva latitud 40.416775 y longitud -3.70379, y se registra un aviso solo por la latitud

#### Scenario: Estación que deja de aparecer
- **WHEN** existe la estación "4375" con precios en capturas anteriores y la nueva respuesta de la API no la incluye
- **THEN** la estación y sus precios anteriores no se borran ni se modifican, y la nueva captura no tiene precios de "4375"

### Requirement: Captura con fecha y hora
Cada ingesta correcta SHALL crear una captura nueva que registre el instante
de la descarga y la fecha que indica la API en el campo `Fecha` (formato
`dd/mm/aaaa hh:mm:ss`, hora de Madrid; se aceptan día, mes y hora de un
dígito). Todos los precios guardados en esa
ejecución MUST quedar asociados a esa captura. Se crea una captura nueva
aunque la `Fecha` coincida con la de una captura anterior.

#### Scenario: Registro de la captura
- **WHEN** la ingesta descarga los datos en el instante 2026-10-10T17:05:30Z (19:05:30 en Madrid) y la API devuelve `"Fecha": "10/10/2026 19:05:23"`
- **THEN** se crea una captura cuyo instante de descarga es 2026-10-10T17:05:30Z, sea cual sea la zona horaria de la máquina, con fecha de la fuente 10/10/2026 19:05:23 (hora de Madrid), y todos los precios de la ejecución apuntan a ella

#### Scenario: Dos ejecuciones con la misma Fecha de la API
- **WHEN** la ingesta se ejecuta correctamente a las 08:00 y a las 08:05, y en ambas la API devuelve `"Fecha": "10/10/2026 07:50:12"`
- **THEN** existen dos capturas distintas con la misma fecha de la fuente, y los precios de la primera no se modifican al guardar la segunda

#### Scenario: Fecha con números de un dígito
- **WHEN** la API devuelve `"Fecha": "1/2/2026 9:05:23"`
- **THEN** la captura se guarda con fecha de la fuente 01/02/2026 09:05:23 (hora de Madrid), sin aviso

#### Scenario: Fecha de la API ausente o con otro formato
- **WHEN** la respuesta no trae el campo `Fecha`, o trae `"Fecha": null`, `"Fecha": "2026-10-10 19:05"` o una fecha imposible como `"Fecha": "31/02/2026 10:00:00"`
- **THEN** la captura se guarda igualmente con el instante de descarga y sin fecha de la fuente, con todos sus precios, y se registra un aviso

### Requirement: Primera ejecución
Si la base de datos todavía no existe, la ingesta SHALL crearla con la
estructura necesaria y guardar la captura con normalidad.

#### Scenario: Base de datos inexistente
- **WHEN** no existe el archivo de la base de datos y la API devuelve 2 estaciones válidas
- **THEN** se crea la base de datos, se registran las 2 estaciones y se guarda una captura con sus precios

### Requirement: Ubicación de la base de datos
Por defecto, la ingesta SHALL usar el archivo `data/prices.db` dentro de la
carpeta del proyecto, sea cual sea la carpeta desde la que se lance. La opción
`--db <ruta>` MUST permitir usar otro archivo. Si la carpeta del archivo no
existe, se crea.

#### Scenario: Lanzada desde otra carpeta
- **WHEN** el proyecto está en `/Users/ana/sdd-rastreador` y la ingesta se lanza sin `--db` desde `/tmp`
- **THEN** la captura se guarda en `/Users/ana/sdd-rastreador/data/prices.db`, el mismo archivo que si se lanzara desde la carpeta del proyecto, y no se crea nada en `/tmp`

#### Scenario: Ruta indicada con --db
- **WHEN** la ingesta se lanza con `--db /tmp/pruebas/otra.db` y `/tmp/pruebas` no existe
- **THEN** se crea `/tmp/pruebas`, la captura se guarda en `/tmp/pruebas/otra.db` y `data/prices.db` del proyecto no se toca

### Requirement: Base de datos con estructura desconocida
Si la base de datos existe pero su estructura tiene una versión que la
ingesta no reconoce (por ejemplo, creada por una versión futura del
programa), la ingesta SHALL terminar con error sin modificarla.

#### Scenario: Versión de estructura desconocida
- **WHEN** la base de datos existe con la versión de estructura 7 y contiene capturas anteriores
- **THEN** la ejecución termina con un error que indica que la versión de la base de datos no es compatible, con código distinto de 0, y la base de datos queda exactamente igual que antes

### Requirement: Respuestas inválidas no guardan nada
Si la descarga falla o la respuesta en su conjunto es inválida, la ingesta
SHALL terminar con error sin dejar ningún cambio en la base de datos: ni
captura, ni precios, ni altas o actualizaciones de estaciones. Los datos
guardados antes MUST quedar intactos.

#### Scenario: Fallo de conexión
- **WHEN** no se puede conectar con la API (por ejemplo, el servidor rechaza la conexión o no se resuelve el nombre)
- **THEN** la ejecución termina con error y la base de datos queda exactamente igual que antes

#### Scenario: Error HTTP
- **WHEN** la API responde con HTTP 500
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Respuesta final distinta de 200
- **WHEN** la API (tras seguir las redirecciones) responde con HTTP 204 o HTTP 206
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Cuerpo vacío
- **WHEN** la API responde con HTTP 200 y el cuerpo vacío
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Respuesta que no es JSON
- **WHEN** la API responde con HTTP 200 pero el cuerpo es XML o HTML
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: JSON cortado
- **WHEN** la API responde con HTTP 200 y un JSON que se corta a mitad de la lista de estaciones
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Raíz que no es un objeto
- **WHEN** la API responde con HTTP 200 y el JSON `[]` o `"OK"`
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Resultado de consulta no correcto
- **WHEN** la API responde con `"ResultadoConsulta": "ERROR"`
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Resultado de consulta ausente
- **WHEN** la respuesta no trae el campo `ResultadoConsulta`
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Lista de estaciones ausente
- **WHEN** la respuesta no trae el campo `ListaEESSPrecio`
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Lista de estaciones vacía
- **WHEN** la respuesta trae `"ListaEESSPrecio": []`
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Lista de estaciones que no es una lista
- **WHEN** la respuesta trae `"ListaEESSPrecio": {"IDEESS": "4375"}` o `"ListaEESSPrecio": "sin datos"`
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Estación que no es un objeto
- **WHEN** `ListaEESSPrecio` contiene una estación válida y el elemento `"4375"` (un texto, no un objeto)
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Estación sin identificador
- **WHEN** una de las estaciones de la respuesta no tiene `IDEESS`, lo tiene vacío o con solo espacios (`"   "`)
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Identificador que no es texto
- **WHEN** una de las estaciones trae `"IDEESS": 4375` (número JSON) o `"IDEESS": null`
- **THEN** la ejecución termina con error y no se guarda nada

#### Scenario: Identificador duplicado
- **WHEN** dos estaciones de la misma respuesta traen `"IDEESS": "4375"`
- **THEN** la ejecución termina con error indicando el identificador duplicado y no se guarda nada

#### Scenario: Identificador duplicado con espacios
- **WHEN** una estación trae `"IDEESS": " 4375 "` y otra de la misma respuesta trae `"IDEESS": "4375"`
- **THEN** se consideran el mismo identificador "4375": la ejecución termina con error indicando "4375" y no se guarda nada

#### Scenario: Error de escritura en la base de datos
- **WHEN** se produce un error de escritura en la base de datos durante el guardado de la captura
- **THEN** la ejecución termina con error y la base de datos queda exactamente igual que antes (mismas estaciones, capturas y precios)

#### Scenario: Error de escritura en la primera ejecución
- **WHEN** no existe el archivo de la base de datos y se produce un error de escritura durante el guardado de la captura
- **THEN** la ejecución termina con error y no queda ningún archivo de base de datos

### Requirement: Resultado de la ejecución
Al terminar, la ingesta SHALL informar del resultado. Si es correcta, informa
del número de estaciones procesadas, nuevas y actualizadas, de precios
guardados y de avisos, mostrando cada aviso, y termina con código de salida 0
aunque haya avisos. Si falla, informa del motivo y termina con un código de
salida distinto de 0.

#### Scenario: Resumen de ejecución correcta
- **WHEN** la base de datos ya tiene la estación "4375", y la API devuelve "4375" y otras 2 estaciones nuevas, con 2, 0 y 4 precios válidos y ninguno inválido
- **THEN** la ingesta informa de 3 estaciones procesadas (2 nuevas y 1 actualizada), 6 precios guardados y 0 avisos, y termina con código 0

#### Scenario: Ejecución correcta con avisos
- **WHEN** la API devuelve 2 estaciones, una con `"Precio Gasoleo A": "1,4a9"` y otra con `"Latitud": "abc"`
- **THEN** la captura se guarda, la ingesta informa de 2 avisos mostrando cada uno y termina con código 0

#### Scenario: Informe de ejecución fallida
- **WHEN** la API responde con HTTP 503
- **THEN** la ingesta informa de que la descarga ha fallado con HTTP 503 y termina con un código distinto de 0
