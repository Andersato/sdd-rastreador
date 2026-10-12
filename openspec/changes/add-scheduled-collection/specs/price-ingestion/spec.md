# Spec Delta

## ADDED Requirements

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
un mensaje, sin pedir nada a la API ni tocar la base.

#### Scenario: Segunda ingesta mientras otra descarga
- **WHEN** una ingesta sobre `/tmp/a/prices.db` está esperando la respuesta de la API y se lanza otra sobre el mismo archivo
- **THEN** la segunda termina en menos de 2 segundos con código distinto de 0 y un mensaje que indica que ya hay otra ingesta en curso, sin hacer ninguna petición a la API, y la primera termina con normalidad y guarda su captura

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
