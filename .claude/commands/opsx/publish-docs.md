---
description: Publica en Confluence la documentación de un cambio archivado de OpenSpec
argument-hint: [nombre-del-cambio]
---

Publica en Confluence la documentación del cambio archivado "$ARGUMENTS"
(si no se indica, usa el último cambio de openspec/changes/archive/).

Sigue al pie de la letra la sección "Documentación en Confluence" de CLAUDE.md.

Pasos:
1. Lee el cambio archivado (proposal.md, design.md y las specs delta) y
   las specs actuales de openspec/specs/ que haya modificado.
2. Crea o actualiza la página de cada funcionalidad afectada con la plantilla.
3. Si el cambio afecta a cómo se recogen, guardan o limpian los datos
   (fuente, frecuencia, combustibles, limitaciones), actualiza la página "Datos".
4. Añade a "Decisiones" las decisiones del design.md en lenguaje llano.
5. Añade una entrada al Changelog con la fecha y qué cambia para el usuario.
6. Actualiza el estado y los próximos pasos en "Visión del proyecto".
7. Si aparece un término técnico nuevo, añádelo al Glosario.

Al terminar, dame la lista de páginas creadas o actualizadas con su enlace.
