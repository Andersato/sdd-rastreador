# Proposal

## Why

La API del Ministerio solo ofrece los precios actuales de las gasolineras: si
no los guardamos nosotros, se pierden. Sin un histórico propio no hay nada que
consultar, comparar ni dibujar en mapas o gráficos, así que la ingesta es la
base de todo lo demás del proyecto.

## What Changes

- Nuevo script de ingesta que, al ejecutarse manualmente, hace **una** petición
  a la API del Ministerio (EstacionesTerrestres) pidiendo JSON y descarga los
  precios de todas las gasolineras de España. Sin reintentos y con tiempo límite.
- Normalización de los datos recibidos:
  - Precios y coordenadas con coma decimal ("1,459", "-3,712345") pasan a número.
  - Un precio vacío o ausente significa "no vende ese combustible": no se
    guarda ningún precio para ese combustible (nunca 0).
- Guardado en SQLite separando:
  - **Datos fijos de la estación**: rótulo, dirección, municipio, provincia,
    coordenadas y horario. Si la estación ya existe, se actualizan sus datos
    sin duplicarla.
  - **Capturas**: cada ejecución correcta crea una captura con su fecha y hora,
    y los precios de cada estación y combustible quedan asociados a ella.
- Dos niveles de error:
  - **Respuesta inválida en su conjunto** (fallo de red, tiempo agotado,
    estado final distinto de 200, no es JSON, raíz que no es objeto,
    `ResultadoConsulta` distinto de OK, `ListaEESSPrecio` ausente, vacía o que
    no es lista, estación que no es objeto, `IDEESS` ausente, vacío, que no es
    texto o duplicado, base de datos con versión desconocida, fallo al
    escribir): no se guarda nada.
  - **Dato inválido en una estación** (precio mal formado, que no es texto,
    cero o negativo; coordenada vacía, ausente, `null`, que no es texto,
    inválida o fuera de rango; `Fecha` de la API inválida): se descarta solo
    ese dato, se guarda el resto y se avisa.
- La base de datos está siempre en `data/prices.db` dentro del proyecto, se
  lance desde donde se lance; `--db` permite usar otra.
- Resumen al terminar (estaciones, precios, avisos) y código de salida.
- La base de datos SQLite no se sube al repositorio (`.gitignore`).

## Decisiones

1. **Datos inválidos en una estación no anulan la captura.** Un precio mal
   formado, cero o negativo no se guarda; el resto sí, y se avisa. Así un
   error puntual del Ministerio no hace perder el día entero de datos.
2. **Coordenada vacía o inválida**: se descartan las coordenadas recibidas,
   se guardan los precios y se avisa. Una estación nueva queda sin
   coordenadas (el mapa la filtrará); una existente conserva las que tenía.
   Rango válido: latitud -90 a 90, longitud -180 a 180 (no se limita a España).
3. **Se guardan todos los combustibles** que trae la API (cualquier campo
   `Precio ...`), con el nombre tal y como lo da la API.
4. **La captura registra dos fechas**: el instante de la descarga y el campo
   `Fecha` de la API. Si `Fecha` falta o tiene otro formato, la captura se
   guarda sin ella y se avisa.
5. **Cada ejecución correcta crea una captura nueva**, aunque la `Fecha` de la
   API coincida con la de la captura anterior.
6. **El identificador de la estación es `IDEESS`.** Si falta, está vacío, no
   es texto o se repite en una misma respuesta, no se guarda nada.
7. **Los datos fijos de texto se sustituyen por los más recientes**, aunque
   lleguen vacíos, sin aviso. Excepción: las coordenadas solo se sustituyen
   si las nuevas son válidas (decisión 2).
8. **Formatos y espacios**: en números se ignora cualquier espacio en blanco
   alrededor (también tabuladores y saltos de línea) y se acepta cualquier
   número de decimales; el punto decimal ("1.459") es inválido. Al `IDEESS` se
   le quitan los espacios de alrededor; el resto de textos se guardan tal cual
   (un número se convierte a texto).
9. **Una sola petición por ejecución**: seguir una redirección cuenta como la
   misma petición; lo prohibido son los reintentos.
10. **Tiempo límite**: la spec define qué pasa al agotarse; el valor (120 s)
    se fija en design.md.
11. **Ejecución con avisos termina con código 0**; el resumen indica cuántos
    avisos hubo y los muestra (uno por campo con problema).
12. **Precio `null`** = ausente, sin aviso. **Coordenada ausente o `null`** =
    vacía, con aviso.
13. **`Fecha`** acepta día, mes y hora de un dígito ("1/2/2026 9:05:23").
14. **Ruta de la base de datos** calculada desde la carpeta del proyecto, no
    desde la carpeta actual, para que la recogida programada futura use la
    misma base. `--db` permite otra ruta.
15. **Base de datos con versión de estructura desconocida**: error sin
    tocarla.

## Fuera de alcance

- Ejecución programada (cron o similar): de momento el script se lanza a mano.
- Protección ante respuestas sospechosamente cortas (p. ej. 40 estaciones en
  lugar de unas 12.000). Candidato para `add-scheduled-collection`.
- API web (src/api/), interfaz (web/) y mapas o gráficos.
- Alertas o notificaciones.
- Histórico de los cambios en los datos fijos de una estación (solo se guarda
  su versión más reciente).
- Reintentos automáticos ante fallos de la API.
- Evitar dos ejecuciones simultáneas (se lanza a mano).
- Conversión de unidades: algunos combustibles (GNC, GNL, hidrógeno) se
  venden por kg y el resto por litro; se guardan tal cual.
- Carga de otros tipos de estación (marítimas, postes de recarga, etc.).

## Capabilities

### New Capabilities
- `price-ingestion`: descarga de los precios de la API del Ministerio,
  normalización, registro de estaciones y guardado de cada captura con su
  fecha y hora, de forma atómica.

### Modified Capabilities
- Ninguna (es la primera capacidad del proyecto).

## Impact

- Código nuevo en `src/ingestion/` (sin dependencias de `src/api/` ni de `web/`).
- Nueva base de datos SQLite local con el esquema inicial (estaciones,
  capturas y precios). No hay datos previos que migrar ni preservar.
- Tests nuevos con respuestas guardadas en `tests/fixtures/`; los tests nunca
  llaman a la API real.
- Dependencias: ninguna nueva en producción (la descarga usa la librería
  estándar de Python). Solo `pytest` para desarrollo, en
  `requirements-dev.txt`, confirmado por el usuario.
- Python 3.12 en un entorno virtual propio.
- Uso de la API: una sola petición por ejecución.
