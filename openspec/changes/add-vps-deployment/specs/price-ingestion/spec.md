# Spec Delta

## ADDED Requirements

### Requirement: Bloqueo compartido con la copia de seguridad
La copia de seguridad de `database-backup` SHALL usar el mismo bloqueo
mientras vuelca la base: una ingesta que lo encuentra cogido por una copia
se comporta igual que con otra ingesta. Diferencia intencionada con "Una
sola ingesta a la vez por base de datos": la copia es la única que espera a
que se libere (como mucho 10 minutos).

#### Scenario: Ingesta durante una copia
- **WHEN** una copia de seguridad está volcando la base (tiene cogido el bloqueo de `./data`) y se lanza `docker compose run --rm ingest`
- **THEN** la ingesta termina en menos de 2 segundos con código distinto de 0 y el mensaje "ya hay otra ingesta o copia en curso", sin hacer ninguna petición a la API, y la copia termina con normalidad

## MODIFIED Requirements

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
