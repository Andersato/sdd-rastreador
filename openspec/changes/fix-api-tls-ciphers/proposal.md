# Proposal

## Why

La ingesta falla a menudo al conectar con la API del Ministerio, con
`UNEXPECTED_EOF_WHILE_READING` durante el saludo TLS, tanto sin Docker como
con Docker. La causa la ha diagnosticado el usuario:
- el servidor solo acepta TLS 1.2 con el cifrado `AES256-GCM-SHA384`, con
  intercambio de claves RSA y sin ECDHE;
- la lista de cifrados que Python ofrece por defecto no lo incluye;
- curl sí conecta;
- con `set_ciphers('DEFAULT')` la descarga responde HTTP 200 con 12 MB.

El fallo es intermitente. Una ejecución desde la imagen Docker conectó y
guardó la captura el 12-10-2026 a las 11:37 (ver `docs/container-checks.md`),
aunque su lista de cifrados por defecto tampoco incluye
`AES256-GCM-SHA384`. Puede que no todos los servidores que atienden esa
dirección tengan la misma configuración. Mientras siga fallando, no se
pueden guardar capturas de forma fiable, y la última comprobación de
`add-container-setup` (tarea 6.3) queda bloqueada. Ese cambio no se
archivará hasta resolver este.

**Que baste con `AES256-GCM-SHA384`:** el usuario lo ha comprobado ofreciendo
solo ese cifrado con TLS 1.2 desde `python:3.12-slim`. Resultado: HTTP 200
y 12 241 680 bytes.

## What Changes

- **Cifrados que se ofrecen:** al conectar por HTTPS, la ingesta ofrece los
  cifrados por defecto de Python más dos cifrados TLS 1.2 con intercambio
  RSA: `AES256-GCM-SHA384` y `AES128-GCM-SHA256`. No se añade ningún otro.
- **Alcance:** vale para cualquier conexión HTTPS de la ingesta, incluidas
  las URL dadas con `--url` y las redirecciones.
- **Lo que no cambia:**
  - la verificación del certificado y del nombre del servidor;
  - la versión mínima de TLS;
  - el mensaje de error;
  - el resto de la descarga: una sola petición, sin reintentos y con tiempo
    límite.
- **Con y sin Docker:** el cambio está en el código de la ingesta, así que
  sirve en los dos casos.

### Datos ya guardados

No afecta a los datos guardados ni a la estructura de la base de datos.

### Fuera de alcance

- Cualquier otro cambio en la ingesta o en Docker, incluido un mensaje
  nuevo para los errores de certificado.
- Reintentos, otras versiones de TLS o cifrados distintos de los dos
  indicados.
- Archivar `add-container-setup`: se hará cuando el usuario confirme una
  captura real con código 0.

## Capabilities

### New Capabilities
<!-- Ninguna. -->

### Modified Capabilities
- `price-ingestion`: se añaden dos requisitos: uno sobre los cifrados que se
  ofrecen al conectar con la API y otro sobre la verificación de su
  certificado. Los requisitos que ya existen no cambian.

## Impact

- **Código:** `src/ingestion/client.py`. La petición usa un contexto TLS
  propio.
- **Tests (sin red real):**
  - Comprobación de la configuración del contexto TLS: lista de cifrados,
    versión mínima TLS 1.2 y verificación del certificado y del nombre.
  - Un servidor TLS local en `127.0.0.1` para los casos esenciales:
    - conexión con `AES256-GCM-SHA384`;
    - conexión con `AES128-GCM-SHA256`;
    - certificado no reconocido;
    - nombre que no coincide.
  - Los cifrados débiles y TLS 1.0/1.1 se comprueban solo en la
    configuración, porque montar servidores así en OpenSSL 3 no es fiable.
- **Certificados de prueba:**
  - Se guardan en `tests/fixtures/tls/`: una autoridad de prueba y certificados
    para `127.0.0.1` y para `otro.example`.
  - Tienen una validez de unos 100 años, para que los tests no fallen al
    caducar.
  - Una nota en `tests/fixtures/tls/` explica cómo regenerarlos y que la clave
    privada solo sirve para los tests.
- **Dependencias:** ninguna nueva.
- **Comprobación real:** la lanza el usuario con `docker compose run --rm
  ingest` y con la ejecución sin Docker.
