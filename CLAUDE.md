# Precios de Gasolineras

Web que recoge a diario los precios de las gasolineras de España, construye
un histórico propio y permite consultarlo con mapas y gráficos. Proyecto
creado para aprender Spec-Driven Development con OpenSpec y a trabajar con
datos reales.

## Stack
- Python + FastAPI para el backend; SQLite como base de datos.
- Frontend en HTML + JavaScript, con Leaflet (mapas) y Chart.js (gráficos).
- pytest para tests unitarios y de API; Playwright para tests funcionales.
- Estructura:
  - src/ingestion/: descarga, limpieza y guardado de precios (sin dependencias
    de la API web ni de la UI).
  - src/api/: endpoints de FastAPI.
  - web/: interfaz.
- Código y nombres en inglés; specs y documentación en español.

## Fuente de datos
- API REST oficial del Ministerio:
  https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/
- La API solo da precios actuales: el histórico lo construimos nosotros
  guardando una captura en cada ejecución. Cada captura lleva su fecha y hora.
- Pedir JSON con la cabecera `Accept: application/json` (por defecto da XML).
- Los precios y coordenadas vienen como texto con coma decimal ("1,459");
  conviértelos a número en la ingesta. Un precio vacío significa "no vende
  ese combustible", no 0.
- Atribución obligatoria al mostrar o publicar los datos: "Ministerio de
  Industria, Comercio y Turismo - Precios de carburantes en estaciones de
  servicio".

## Flujo de trabajo (SDD con OpenSpec)
- No implementes nada que no esté en una spec o en un cambio de openspec/changes/.
- Ciclo de cada cambio:
  1. /opsx:propose genera SOLO proposal.md y las specs. Detente ahí.
  2. Lanza el agente spec-reviewer sobre proposal y specs.
  3. El usuario responde las decisiones y se corrigen los artefactos.
  4. Solo cuando el usuario confirme la spec, genera design.md y tasks.md.
  5. Lanza de nuevo el spec-reviewer para comprobar la coherencia de todo.
  6. /opsx:apply → agente test-writer → agente code-reviewer →
     /opsx:archive → /publish-doc.
- No generes design.md ni tasks.md sin que el usuario haya confirmado la spec.
- No ejecutes /opsx:apply hasta que el spec-reviewer dé "Lista para
  implementar" y el usuario lo confirme.
- No ejecutes /opsx:archive hasta que el code-reviewer dé "Listo para archivar".
- Si algo de la spec es ambiguo, pregunta en vez de suponer.
- Si un test falla con un ejemplo de la spec, no modifiques el test:
  averigua si el error está en el código o en la spec y pregúntame.
- Después de generar design.md y tasks.md, detente y espera a que el
  usuario confirme antes de implementar. Solo /opsx:apply inicia la
  implementación.

## Normas
- No hagas commits ni push; los hago yo.
- No refactorices código fuera del alcance de la tarea sin preguntarme.
- No añadas dependencias nuevas sin consultarme.
- Los tests nunca llaman a la API real: usa respuestas guardadas en
  tests/fixtures/. Si necesitas una respuesta real nueva, pídemela.
- Nunca borres ni modifiques datos históricos de la base de datos.
  Cualquier migración que les afecte debe consultarse antes.
- No subas la base de datos al repo (debe estar en .gitignore).
- Sé respetuoso con la API: nada de bucles de peticiones; como mucho
  la frecuencia de recogida definida en la spec.

## Documentación en Confluence
- Espacio: "Precios de Gasolineras" (key: PG).
- Público: cualquier persona, aunque no sea del equipo ni programe.
  Escribe en español claro, sin jerga; si un término técnico es
  inevitable, añádelo al Glosario.
- Estructura del espacio:
  - Visión del proyecto: qué es, estado actual y próximos pasos.
  - Glosario.
  - Datos: de dónde salen, cada cuánto se recogen y sus limitaciones.
  - Funcionalidades: una página por cada spec de openspec/specs/.
  - Decisiones: decisiones de design.md explicadas en lenguaje llano.
  - Changelog.
- Cada página de funcionalidad sigue esta plantilla:
  1. En pocas palabras (2-3 frases).
  2. Cómo funciona, con ejemplos concretos.
  3. Criterios decididos (qué se considera "cerca", "más barato", etc.).
  4. Qué no hace todavía.
  5. Especificación técnica completa, en un bloque desplegable al final.
- Tras cada /opsx:archive: actualiza la funcionalidad afectada, añade
  sus decisiones a "Decisiones", añade una entrada al Changelog
  ("qué cambia para el usuario", en lenguaje llano) y actualiza el
  estado en "Visión del proyecto".
- Las specs del repo son la fuente de verdad; Confluence es solo un reflejo.
