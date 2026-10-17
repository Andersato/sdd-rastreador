# Proposal

## Why

El histórico ya se recoge solo en el VPS cada 6 horas, pero solo se puede
consultar abriendo la base de datos a mano. Hace falta una API web de solo
lectura que responda a las preguntas básicas (qué gasolineras hay cerca y a
qué precio, qué vende una estación, cómo están las provincias) y que sea la
base de la futura interfaz con mapa y gráficos.

El encargo completo incluye también consultas sobre el histórico (evolución
de una estación, medias diarias, día de la semana más barato), que recorren
millones de filas y seguramente necesitan índices nuevos, es decir, una
migración de la base con histórico. Por la regla de mantener el alcance
pequeño, y con el acuerdo del usuario, el encargo se divide en dos cambios:

1. **`add-prices-api` (este cambio):** el servicio de la API y las consultas
   sobre la **última captura**, que con los índices actuales ya responden en
   milisegundos. No toca la estructura de la base.
2. **`add-price-stats` (siguiente cambio):** histórico de una estación (por
   captura o por día, con la media diaria de su provincia opcional), media
   diaria de España y por provincia, día de la semana más barato, y los
   índices o la migración que hagan falta, justificados con mediciones.

## What Changes

- **Servicio nuevo `api`** en `docker-compose.yml`, con la misma imagen que
  la recogida: `docker compose up -d` lo arranca junto al programador, con
  `restart: unless-stopped`, y funciona igual con la recogida activada o
  desactivada (en el Mac sirve la base local).
- **Dependencias nuevas, ya aprobadas por el usuario:** FastAPI y uvicorn
  (producción, versiones fijadas en un `requirements.txt` nuevo) y httpx
  (solo para tests, en `requirements-dev.txt`). La ingesta y las copias
  siguen sin depender de ellas.
- **Consultas (todas sobre la última captura):**
  - Salud del servicio: estado y fecha de la última captura.
  - Lista de combustibles: nombre, identificador corto (`gasoleo-a`),
    unidad (€/l o €/kg) y número de estaciones que lo venden.
  - Gasolineras cercanas a unas coordenadas para un combustible, dentro de
    un radio, ordenadas por precio y después por distancia, con radio y
    número de resultados máximos.
  - Ficha de una estación con sus precios actuales.
  - Precio medio por provincia de un combustible.
- **Todas las respuestas** de datos dicen de qué captura salen, y todas
  (también los errores) incluyen la atribución obligatoria al Ministerio.
  Documentación interactiva en `/api/docs`.
- **Limpieza al responder (la base no se toca):** coordenadas fuera de
  España se tratan como desconocidas, textos sin espacios de sobra, y nunca
  se mezclan combustibles con unidades distintas.
- **Acceso a la base solo de lectura:** la carpeta `data/` se monta en modo
  solo lectura, la API nunca escribe ni crea archivos en ella y, si la base
  está ocupada por una recogida, responde 503 con un mensaje claro.
- **Exposición mínima:** la API solo escucha en `127.0.0.1` del servidor
  (nunca en todas las interfaces, porque Docker se salta `ufw`) y se usa
  desde el Mac con un túnel SSH. No se abre ningún puerto en `ufw`.
- **Runbook del VPS:** pasos para arrancar la API, comprobar que solo escucha
  en `127.0.0.1` y abrir el túnel desde el Mac. Los comandos en el VPS los
  lanza el usuario; ningún agente se conecta al servidor.

## Decisiones confirmadas por el usuario

1. **Zonas de España** (rectángulos de latitud y longitud): Península
   35,9–43,9 N y 9,4 O–3,4 E; Baleares 38,6–40,1 N y 1,1–4,4 E; Canarias
   27,6–29,5 N y 18,2–13,3 O; Ceuta 35,86–35,93 N y 5,39–5,27 O; Melilla
   35,26–35,32 N y 2,98–2,92 O. Con los datos reales del 16/10/2026 dejan
   fuera 5 de 11.546 estaciones: 4 en (0, 0) y una con latitud y longitud
   intercambiadas (Tui). Incluyen parte de Portugal, Francia, Andorra y
   Marruecos, y se acepta.
2. **Estaciones con coordenadas fuera de esas zonas:** no salen en
   «cercanas»; en su ficha salen sin coordenadas; sí cuentan en la media por
   provincia.
3. **Catálogo fijo** con los 21 combustibles que tienen precios hoy. €/kg
   para Gas Natural Comprimido y Licuado, Biogas Natural Comprimido y
   Licuado e Hidrógeno; €/l para el resto. AdBlue entra como «aditivo».
   Amoniaco y Metanol quedan fuera hasta conocer su unidad con datos reales;
   lo que no está en el catálogo no se expone y la salud lo lista como «no
   expuesto».
4. **`fuel` obligatorio**, sin valor por defecto, y solo por su identificador
   corto (`gasoleo-a`); los 21 identificadores se fijan en la spec.
5. **Cercanas:** radio de 5 km por defecto y 50 como máximo; 20 resultados
   por defecto y 100 como máximo; distancia en línea recta; un punto de
   búsqueda imposible da «parámetro no válido» y uno fuera de España,
   `fuera_de_espana`.
6. **Varias capturas con la misma `Fecha`:** aquí se usa la última guardada.
   Para las estadísticas, en `add-price-stats`, se propondrá contarlas una
   sola vez.
7. **Salud:** «desactualizada» si la última captura tiene más de dos veces
   `CAPTURE_INTERVAL_HOURS` más 1 h (13 h por defecto); la API recibe esa
   variable y, si no es válida, la salud lo dice. 503 si no hay base, no se
   puede leer, está ocupada o no tiene capturas.
8. **Fecha de la fuente en el cambio de hora:** en la hora repetida de
   octubre se usa el desfase más cercano al instante de descarga; en la hora
   que no existe de marzo, `null`.
9. **Rutas bajo `/api/`**, incluida la documentación (`/api/docs` y
   `/api/openapi.json`); la raíz queda para la web. Errores en español con
   formato común, 405 para métodos distintos de GET.
10. **Log de la API:** una línea por petición con las coordenadas de las
    búsquedas redondeadas a 2 decimales (para no guardar ubicaciones exactas
    cuando la web sea pública), en 3 archivos de 10 MB como mucho.
11. **Objetivos de tiempo de respuesta:** menos de 1 s para cada consulta de
    este cambio con un año de datos (unas 1.460 capturas), medido en el Mac
    con una base sintética fuera de `data/` y en el VPS con la base real.
    Para `add-price-stats`: histórico de una estación de un año < 1 s, media
    diaria de 31 días de España < 3 s, día de la semana de un año < 10 s.
12. **La API no puede hacer fallar una recogida:** la recogida espera hasta
    5 s para guardar mientras alguien lee; por eso ninguna petición de la API
    lee la base más de 2 s seguidos: si llega, se corta y responde 503.
13. **Usuario 0 (root) en `.env`:** la API no arranca y lo dice en su log;
    Docker la reintenta. No se queda en marcha como el programador, para no
    tener nunca un servidor web ejecutándose como root.
14. **Base de versión 0 o vacía:** 503 `sin_capturas`; archivo que no es una
    base: 503 `base_ilegible`.

## Capabilities

### New Capabilities
- `prices-api`: API web de solo lectura sobre la base de precios: servicio,
  acceso a la base, formato común de las respuestas, limpieza al responder,
  catálogo de combustibles y las consultas sobre la última captura.

### Modified Capabilities
- `ingestion-container`: la imagen incluye además FastAPI y uvicorn (sin
  dependencias de desarrollo como httpx), `docker compose build` construye
  también la que usa el servicio `api`, y la ingesta y las copias se
  ejecutan sin cargar FastAPI ni uvicorn.
- `scheduled-collection`: `docker compose up -d` deja en marcha dos
  contenedores (programador y API) en lugar de uno solo.
- `server-deployment`: el runbook incluye el arranque de la API, la
  comprobación de que solo escucha en `127.0.0.1` y el túnel SSH desde el
  Mac, sin abrir puertos en `ufw`.

## Fuera de alcance

- Las consultas de histórico y estadísticas (van en `add-price-stats`).
  Nota para ese cambio: las consultas largas (medias diarias, día de la
  semana) no podrán leer la base en vivo más de 2 s sin hacer perder
  capturas; tendrán que usar índices, una copia de la base o tablas de
  resumen. Se probará primero con índices y se consultará al usuario antes
  de añadir tablas de resumen.
- Índices nuevos y cualquier migración de la base de datos.
- Interfaz web, gráficos y mapa.
- HTTPS, dominio y cualquier acceso desde internet sin túnel.
- Usuarios, claves de acceso y límites de peticiones.
- Alertas.
- Guardar solo los precios que cambian.
- Corregir datos en la base (coordenadas, textos): la limpieza es solo al
  responder.

## Datos ya guardados

Este cambio no modifica la estructura ni el contenido de la base: la API la
abre en solo lectura sobre un montaje de solo lectura. El histórico existente
queda intacto.

## Impact

- Código nuevo en `src/api/`; programa de arranque de la API en `container/`.
- `docker-compose.yml` (servicio `api`), `Dockerfile` (instalar
  `requirements.txt`), `requirements.txt` nuevo y `requirements-dev.txt`.
- Tests unitarios y de API con bases de datos de prueba generadas en
  carpetas temporales; tests de Docker para el servicio y el puerto.
- README y `docs/vps-deployment.md`.
- Tests existentes que esperan un único contenedor tras `docker compose up -d`.
- Al archivar: actualizar el Purpose de `openspec/specs/ingestion-container/`,
  que hoy solo habla de la ingesta, para que incluya la API.
