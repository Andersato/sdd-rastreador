# price-ingestion Specification

## Purpose

Descargar los precios actuales de todas las gasolineras de España desde la API
del Ministerio y guardarlos como una captura con fecha y hora, para construir
un histórico propio de precios que la API no ofrece.

## Requirements

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

### Requirement: Cifrados ofrecidos al conectar con la API
En cualquier conexión HTTPS (la URL por defecto, la de `--url` y las de las
redirecciones), la ingesta SHALL ofrecer los cifrados que Python ofrece por
defecto más `AES256-GCM-SHA384` y `AES128-GCM-SHA256` (TLS 1.2 con
intercambio RSA). MUST NOT ofrecer ningún otro cifrado ni bajar la versión
mínima de TLS de 1.2. Los cifrados de TLS 1.3 no cambian. Las URL `http://`
no usan TLS.

#### Scenario: Servidor que solo acepta AES256-GCM-SHA384
- **WHEN** se lanza la ingesta con `--url https://127.0.0.1:<puerto>/api` contra un servidor que solo acepta TLS 1.2 con `AES256-GCM-SHA384`, con un certificado para `127.0.0.1` firmado por una autoridad de confianza, y que responde HTTP 200 con un JSON válido de 2 estaciones
- **THEN** la ingesta hace una única petición, guarda la captura con las 2 estaciones y termina con código 0

#### Scenario: Servidor que solo acepta AES128-GCM-SHA256
- **WHEN** se lanza la ingesta con `--url https://127.0.0.1:<puerto>/api` contra un servidor que solo acepta TLS 1.2 con `AES128-GCM-SHA256`, con un certificado para `127.0.0.1` firmado por una autoridad de confianza, y que responde HTTP 200 con un JSON válido de 2 estaciones
- **THEN** la ingesta hace una única petición, guarda la captura con las 2 estaciones y termina con código 0

#### Scenario: Redirección HTTPS a HTTPS
- **WHEN** se lanza la ingesta con `--url https://127.0.0.1:<puerto A>/api` contra un servidor A que solo acepta TLS 1.2 con `AES256-GCM-SHA384` y responde HTTP 301 hacia un servidor B en `https://127.0.0.1:<puerto B>/api`, que solo acepta TLS 1.2 con `AES128-GCM-SHA256` y responde HTTP 200 con un JSON válido de 2 estaciones (ambos con certificado para `127.0.0.1` firmado por una autoridad de confianza)
- **THEN** A y B reciben una petición cada uno, se guarda la captura con las 2 estaciones y la ejecución termina con código 0

#### Scenario: Se mantienen los cifrados por defecto
- **WHEN** se compara la lista de cifrados que ofrece la ingesta con la lista por defecto de Python en la misma máquina
- **THEN** la de la ingesta contiene todos los de la lista por defecto, y los que tiene de más están entre `AES256-GCM-SHA384` y `AES128-GCM-SHA256`

Nota: con Python 3.12 y OpenSSL 3.0.22 (imagen Docker) o 3.6.3 (`.venv`), la lista por defecto tiene 17 cifrados y no incluye ninguno de los dos, así que los de más son exactamente esos dos.

#### Scenario: Cifrados débiles no se ofrecen
- **WHEN** se consulta la lista de cifrados que ofrece la ingesta
- **THEN** no incluye `AES256-SHA` ni `AES256-SHA256` (CBC con intercambio RSA), ni ningún otro cifrado que no esté en la lista por defecto de Python, salvo los dos añadidos

#### Scenario: Versiones antiguas de TLS no se admiten
- **WHEN** se consulta la versión mínima de TLS de la conexión de la ingesta
- **THEN** es TLS 1.2. Lo que se comprueba es esa versión mínima configurada; como consecuencia, la ingesta no puede conectar con un servidor que solo acepte TLS 1.0 o TLS 1.1

#### Scenario: URL sin TLS
- **WHEN** se lanza la ingesta con `--url http://127.0.0.1:<puerto>/api` y el servidor responde HTTP 200 con un JSON válido de 2 estaciones
- **THEN** la descarga se hace sin TLS, con una única petición, y se guarda la captura

### Requirement: Verificación del certificado de la API
La ingesta SHALL seguir verificando el certificado del servidor contra las
autoridades de confianza que Python usa por defecto, y comprobando que el
nombre del certificado coincide con el del servidor. Si cualquiera de las dos
comprobaciones falla, la descarga MUST fallar con el mensaje de error de
conexión actual y sin guardar nada.

#### Scenario: Verificación activa en la configuración
- **WHEN** se consulta la configuración de la conexión segura de la ingesta
- **THEN** exige un certificado válido y comprueba el nombre del servidor

#### Scenario: Certificado no reconocido
- **WHEN** el servidor acepta `AES256-GCM-SHA384` pero presenta un certificado autofirmado, de una autoridad en la que no se confía
- **THEN** la ejecución termina con código distinto de 0, la salida de error contiene `no se ha podido conectar con la API:` y `CERTIFICATE_VERIFY_FAILED`, y la base de datos queda exactamente igual que antes

#### Scenario: Nombre del servidor que no coincide
- **WHEN** el servidor acepta `AES256-GCM-SHA384` y presenta un certificado firmado por una autoridad de confianza, pero emitido para `otro.example` en lugar de `127.0.0.1`
- **THEN** la ejecución termina con código distinto de 0, la salida de error contiene `no se ha podido conectar con la API:` y `CERTIFICATE_VERIFY_FAILED`, y la base de datos queda exactamente igual que antes

### Requirement: Respuesta con demasiadas pocas estaciones
Si la última captura guardada tiene al menos 1 estación con precio, la
ingesta SHALL comparar con esa cifra las estaciones con al menos un precio
válido de la respuesta. Si son menos del 80 %, MUST terminar con error sin
guardar nada, indicando las dos cifras, el porcentaje y la opción
`--accept-short-response`. Si no hay capturas, o la última no tiene ninguna
estación con precio, no se compara.

#### Scenario: Respuesta corta
- **WHEN** la última captura tiene precios de 12.000 estaciones y la API devuelve una respuesta válida con 9.000 estaciones con precios
- **THEN** la ejecución termina con código distinto de 0, el mensaje indica 9.000 estaciones frente a 12.000 de la última captura ("75,0 %") y menciona `--accept-short-response`, no se hace ninguna otra petición y la base de datos queda exactamente igual que antes

#### Scenario: Justo el 80 %
- **WHEN** la última captura tiene precios de 12.000 estaciones y la respuesta trae 9.600 estaciones con precios
- **THEN** la captura se guarda con normalidad y la ejecución termina con código 0

#### Scenario: Una estación por debajo del 80 %
- **WHEN** la última captura tiene precios de 12.000 estaciones y la respuesta trae 9.599 estaciones con precios
- **THEN** la ejecución termina con código distinto de 0, no se guarda nada y el porcentaje se muestra como "79,9 %" (truncado a un decimal, nunca redondeado a "80,0 %")

#### Scenario: Más estaciones que la última vez
- **WHEN** la última captura tiene precios de 12.000 estaciones y la respuesta trae 12.150
- **THEN** la captura se guarda con normalidad

#### Scenario: Estaciones sin precio no cuentan
- **WHEN** la última captura tiene precios de 10 estaciones y la respuesta trae 10 estaciones, 3 de ellas con todos sus precios vacíos
- **THEN** cuentan 7 estaciones ("70,0 %"), la ejecución termina con código distinto de 0 y no se guarda nada

#### Scenario: Primera captura
- **WHEN** la base de datos no existe, o existe sin capturas, y la API devuelve una respuesta válida con 2 estaciones con precios
- **THEN** no se hace la comparación y la captura se guarda con normalidad

#### Scenario: Última captura sin ninguna estación con precio
- **WHEN** la última captura no tiene ningún precio y la respuesta trae 2 estaciones con precios
- **THEN** no se hace la comparación y la captura se guarda con normalidad

#### Scenario: Ingesta tras un guardado interrumpido
- **WHEN** la base tiene 1 captura con precios de 10 estaciones, queda un `prices.db-journal` de un guardado interrumpido y la API devuelve una respuesta válida con 10 estaciones con precios
- **THEN** la ingesta compara con la captura buena (10 estaciones), guarda la nueva y la base queda con 2 capturas completas, la primera intacta

#### Scenario: Una respuesta rechazada no cambia la referencia
- **WHEN** la última captura tiene precios de 12.000 estaciones, una ejecución se rechaza con 9.000 y la siguiente trae 9.500
- **THEN** la siguiente también se compara con 12.000 ("79,1 %") y se rechaza

Nota: los escenarios de los demás requisitos de `price-ingestion` suponen una
respuesta que no es corta respecto a la captura anterior (o que no hay
captura anterior). Los tests que preparan una captura previa deben usar
respuestas con al menos el 80 % de sus estaciones con precio.

### Requirement: Aceptar a mano una respuesta corta
La opción `--accept-short-response` SHALL hacer que la ingesta guarde la
captura aunque sea corta, con un aviso que indica las dos cifras y el
porcentaje y que cuenta en "Avisos" del resumen. Si la respuesta no es corta
o no hay referencia, se guarda normal y sin ese aviso. Las capturas
siguientes se comparan con la nueva.

#### Scenario: Aceptación manual
- **WHEN** la última captura tiene precios de 12.000 estaciones y se lanza la ingesta con `--accept-short-response` contra una respuesta válida, sin otros avisos, con 9.000 estaciones con precios
- **THEN** se guarda la captura, el resumen muestra "Avisos: 1" y ese aviso con 9.000, 12.000 y "75,0 %", y la ejecución termina con código 0

#### Scenario: La nueva captura pasa a ser la referencia
- **WHEN** después de esa captura aceptada se lanza la ingesta sin la opción y la respuesta trae 8.800 estaciones con precios
- **THEN** se compara con 9.000 ("97,7 %") y se guarda con normalidad

#### Scenario: Opción con una respuesta que no es corta
- **WHEN** la última captura tiene precios de 12.000 estaciones y se lanza con `--accept-short-response` una respuesta con 11.900
- **THEN** se guarda con normalidad y sin ningún aviso por la opción

#### Scenario: Opción sin capturas anteriores
- **WHEN** la base de datos no existe y se lanza con `--accept-short-response` una respuesta válida con 2 estaciones
- **THEN** se guarda con normalidad y sin ningún aviso por la opción

### Requirement: Formato de las cifras en los mensajes
En los mensajes de respuesta corta, las cifras de estaciones SHALL mostrarse
con punto de miles ("12.000") y el porcentaje con un decimal, coma decimal y
truncado, seguido de " %" ("79,9 %").

#### Scenario: Cifras pequeñas
- **WHEN** la última captura tiene precios de 10 estaciones y la respuesta trae 7
- **THEN** el mensaje muestra "7", "10" y "70,0 %"

### Requirement: Una sola ingesta a la vez por base de datos
La ingesta SHALL impedir que dos ejecuciones sobre la misma carpeta de base
de datos trabajen a la vez dentro del mismo sistema (dos contenedores que
comparten `./data`, o dos procesos con `.venv`). No cubre una ejecución con
`.venv` a la vez que una en contenedor; el README advierte de no hacerlo. La
segunda MUST terminar sin esperar a la primera, con código distinto de 0 y
un mensaje ("ya hay otra ingesta o copia en curso"), sin pedir nada a la API
ni tocar la base.

#### Scenario: Segunda ingesta mientras otra descarga
- **WHEN** una ingesta sobre `/tmp/a/prices.db` está esperando la respuesta de la API y se lanza otra sobre el mismo archivo
- **THEN** la segunda termina en menos de 2 segundos con código distinto de 0 y el mensaje "ya hay otra ingesta o copia en curso", sin hacer ninguna petición a la API, y la primera termina con normalidad y guarda su captura

#### Scenario: Carpetas distintas
- **WHEN** una ingesta sobre `/tmp/a/prices.db` está en curso y se lanza otra sobre `/tmp/b/prices.db`
- **THEN** las dos se ejecutan con normalidad

#### Scenario: Ingesta anterior muerta a la fuerza
- **WHEN** una ingesta se mata con `kill -9` mientras espera la respuesta de la API y después se lanza otra sobre la misma base
- **THEN** la nueva no queda bloqueada: se ejecuta con normalidad

#### Scenario: El bloqueo no deja archivos
- **WHEN** `/tmp/a` contiene solo `prices.db` y termina una ingesta sobre ella, correcta o fallida
- **THEN** `/tmp/a` sigue conteniendo solo `prices.db`

#### Scenario: Primera ejecución con base inexistente
- **WHEN** `/tmp/a` existe vacía y se lanzan a la vez dos ingestas sobre `/tmp/a/prices.db` contra un servidor que responde correctamente tras 1 segundo
- **THEN** una guarda la primera captura y la otra termina con el mensaje de ingesta en curso, y el servidor recibe una sola petición

### Requirement: Señal de parada tratada como Ctrl+C
Al recibir SIGTERM, la ingesta SHALL comportarse igual que con Ctrl+C:
deshacer la transacción en curso, borrar sus archivos temporales y terminar
con código distinto de 0. La base MUST quedar con las capturas anteriores
intactas (o también con la nueva completa, si ya se había confirmado) y sin
ningún diario ni temporal en su carpeta.

#### Scenario: Señal de parada durante el guardado
- **WHEN** la base tiene 1 captura y la ingesta recibe SIGTERM mientras guarda la segunda (respuesta de 20.000 estaciones)
- **THEN** la ejecución termina con código distinto de 0, la base contiene la primera captura intacta (o las dos completas, si la segunda ya se había confirmado) y en su carpeta solo queda `prices.db`, sin `prices.db-journal` ni `prices.db.tmp-*`

#### Scenario: Señal de parada durante la primera captura
- **WHEN** la carpeta está vacía y la ingesta recibe SIGTERM mientras guarda la primera captura (respuesta de 20.000 estaciones)
- **THEN** la ejecución termina con código distinto de 0 y la carpeta queda vacía, o solo con `prices.db` completo si la captura ya se había confirmado

#### Scenario: Señal de parada durante la descarga
- **WHEN** la ingesta está esperando la respuesta de la API y recibe SIGTERM
- **THEN** termina en menos de 2 segundos con código distinto de 0, sin hacer ninguna otra petición, y la base y su carpeta quedan exactamente igual que antes

### Requirement: Bloqueo compartido con la copia de seguridad
La copia de seguridad de `database-backup` SHALL usar el mismo bloqueo
mientras vuelca la base: una ingesta que lo encuentra cogido por una copia
se comporta igual que con otra ingesta. Diferencia intencionada con "Una
sola ingesta a la vez por base de datos": la copia es la única que espera a
que se libere (como mucho 10 minutos).

#### Scenario: Ingesta durante una copia
- **WHEN** una copia de seguridad está volcando la base (tiene cogido el bloqueo de `./data`) y se lanza `docker compose run --rm ingest`
- **THEN** la ingesta termina en menos de 2 segundos con código distinto de 0 y el mensaje "ya hay otra ingesta o copia en curso", sin hacer ninguna petición a la API, y la copia termina con normalidad
