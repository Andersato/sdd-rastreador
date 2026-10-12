# Spec Delta

## ADDED Requirements

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
