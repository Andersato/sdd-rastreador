# Design

## Context

Ver proposal.md (Why) y la spec delta de `price-ingestion`.

**Cómo se descarga hoy.** `src/ingestion/client.py` llama a
`urlopen(request, timeout=…)` sin contexto TLS. Python usa entonces su
contexto por defecto, cuya lista de cifrados de TLS 1.2 son 14 cifrados, todos
con ECDHE. A eso se suman los 3 de TLS 1.3, 17 en total.

**Medido en las dos plataformas** (`.venv` con OpenSSL 3.6.3 e imagen con
OpenSSL 3.0.22):
- la lista no incluye `AES256-GCM-SHA384` ni `AES128-GCM-SHA256`;
- el nivel de seguridad del contexto es 2;
- después de `set_ciphers` con la lista ampliada, el nivel sigue en 2 y quedan
  19 cifrados.

**Cómo es la API.** Solo acepta TLS 1.2 con `AES256-GCM-SHA384`. El usuario
lo comprobó ofreciendo solo ese cifrado: HTTP 200 y 12 241 680 bytes.

**Tests actuales.** Usan `tests/http_server.py` (HTTP sin TLS en
`127.0.0.1`) y `tests/helpers.run_cli`, que lanza la CLI como subproceso y
acepta `env=`.

## Goals / Non-Goals

**Goals:**
- Que la ingesta conecte con un servidor que solo acepta TLS 1.2 con
  intercambio RSA.
- No debilitar nada más: verificación, versión mínima, nivel de seguridad y
  TLS 1.3 quedan igual.
- Probarlo sin red real, con un servidor TLS local y certificados de prueba.

**Non-Goals:**
- Fijar los cifrados solo para el dominio del Ministerio: se aplican a toda
  conexión HTTPS de la ingesta (decisión de la spec).
- Cambiar mensajes de error, reintentos, Docker o la imagen.

## Decisions

### 1. Contexto TLS propio, creado en cada descarga
**Qué se hace.** `client.py` gana una función `tls_context()` que:
1. crea el contexto con `ssl.create_default_context()`. Usa las autoridades
   de confianza por defecto, la verificación del certificado
   (`CERT_REQUIRED`) y la comprobación del nombre (`check_hostname`), y no
   lleva `cafile` propio ni `certifi`;
2. toma de ese mismo contexto los nombres de sus cifrados de TLS 1.2 (los de
   `get_ciphers()` cuyo `protocol` no es `TLSv1.3`);
3. llama a `set_ciphers(f"@SECLEVEL={nivel}:" + base + ":AES256-GCM-SHA384:AES128-GCM-SHA256")`,
   con `nivel = max(2, context.security_level)`.

`_download` pasa ese contexto a `urlopen(…, context=tls_context())`.

**Por qué se toma la lista del propio contexto:**
- Así se mantienen exactamente los cifrados por defecto de cada versión de
  Python y OpenSSL, sin copiarlos a mano.
- `ssl._DEFAULT_CIPHERS` es privado, y en Python 3.12 la cadena por defecto
  vive en C.

**Nivel de seguridad: `max(2, nivel de la máquina)`.**
- **Qué es:** el nivel de seguridad de OpenSSL decide qué cifrados y tamaños
  de clave se admiten. La cadena que se pasa a `set_ciphers` lo fija de forma
  explícita.
- **Nunca baja la política de la máquina:** si el sistema tiene una política
  más estricta (nivel 3 o más), se respeta.
- **Nunca queda por debajo de 2:** si una versión de OpenSSL trajera un nivel
  por defecto menor, no se usa.
- **Hoy:** el nivel por defecto es 2 en las dos plataformas, así que el
  resultado es 2.
- **Tests:**
  - el nivel del contexto es igual al del contexto por defecto;
  - con un contexto por defecto simulado de nivel 3, se mantiene 3;
  - con uno de nivel 1, sube a 2.
- **Por qué no `@SECLEVEL=2` fijo:** era la versión anterior de esta decisión.
  El code-reviewer señaló que en una máquina de nivel 3 bajaría la política, y
  el usuario decidió cambiarlo.

**TLS 1.3 no cambia.** `set_ciphers` solo afecta a TLS 1.2 e inferiores. Los
cifrados de TLS 1.3 siguen siendo los de por defecto, y la versión mínima
sigue en TLS 1.2 (no se toca `minimum_version`).

**Orden.** Los cifrados por defecto, con ECDHE, van primero y los dos de RSA
al final. Con un servidor que admite ECDHE se sigue usando un cifrado con
secreto hacia adelante, salvo que el servidor imponga su propio orden.

**Por qué en cada descarga y no al importar el módulo:**
- Es barato: se hace una vez por ejecución.
- Los tests pueden cambiar la autoridad de confianza (variable de entorno
  de OpenSSL, decisión 6) en cada proceso.
- Si cambian las autoridades del sistema, no queda un contexto viejo en
  memoria.

**Alternativas descartadas:**
- `set_ciphers("DEFAULT")`: es lo que probó el usuario, pero abre la lista de
  OpenSSL entera (CBC, SHA-1 y más), mucho más de lo necesario.
- Escribir a mano la lista completa: se desfasaría con cada versión de Python
  u OpenSSL.
- Un contexto aparte solo para el dominio del Ministerio: añade lógica de
  enrutado, y la spec pide el mismo comportamiento para `--url` y las
  redirecciones.

### 2. Redirecciones
`urlopen(context=…)` crea un opener con un único `HTTPSHandler(context=ctx)`,
y ese opener sigue las redirecciones. Toda conexión HTTPS de la misma
descarga, también tras un 301, usa el mismo contexto. Las URL `http://` no
usan el contexto. Un test lo comprueba con una redirección entre dos
servidores HTTPS que solo aceptan uno de los dos cifrados nuevos cada uno
(decisión 5).

### 3. Por qué es aceptable y qué se pierde
**Qué se pierde: el secreto hacia adelante.** Con `AES256-GCM-SHA384` y
`AES128-GCM-SHA256`, la clave de la sesión se cifra con la clave RSA del
certificado del servidor. Si algún día esa clave privada se filtrara, quien
hubiera grabado el tráfico podría descifrar las sesiones pasadas. Con ECDHE no
pasaría.

**Por qué es aceptable aquí:**
- Los datos son públicos: el Ministerio publica esos precios para todo el
  mundo.
- La ingesta no envía credenciales, cookies ni datos personales: solo un GET
  con `Accept: application/json`.
- La autenticidad y la integridad no cambian. Se sigue verificando el
  certificado y el nombre, y AES-GCM protege la integridad. Nadie puede
  hacerse pasar por la API ni alterar los precios sin que la descarga falle.
- Solo se usan estos cifrados si el servidor no acepta ninguno con ECDHE.
- No se añade ningún cifrado débil: ni CBC, ni SHA-1, ni 3DES, ni RC4.

### 4. Certificados de prueba en `tests/fixtures/tls/`
**Archivos** (PEM):
- `ca.pem`: autoridad de prueba.
- `localhost.pem` y `localhost.key`: certificado para `127.0.0.1`, firmado
  por la autoridad.
- `other.pem` y `other.key`: para `otro.example`, firmado por la autoridad.
- `selfsigned.pem` y `selfsigned.key`: autofirmado, para `127.0.0.1`. Lleva
  las mismas extensiones de servidor que `localhost` (`CA:FALSE`, SAN
  `IP:127.0.0.1`), para que falle solo porque no lo firma una autoridad de
  confianza.

**Requisitos, para que sigan valiendo con verificaciones estrictas**
(`VERIFY_X509_STRICT`, activo por defecto desde Python 3.13):
- Claves RSA de 2048 bits, porque los dos cifrados usan intercambio RSA.
- Autoridad: `basicConstraints=critical,CA:TRUE`,
  `keyUsage=critical,keyCertSign,cRLSign` y SKID.
- Certificados de servidor:
  - `subjectAltName=IP:127.0.0.1` (o `DNS:otro.example`): no basta con el CN;
  - `basicConstraints=CA:FALSE`;
  - `keyUsage=critical,digitalSignature,keyEncipherment`, donde
    `keyEncipherment` es necesario para el intercambio RSA;
  - `extendedKeyUsage=serverAuth`;
  - SKID y AKID.
- Validez de 36 500 días, unos 100 años.

**Generación:**
- Un script `tests/fixtures/tls/make_certs.sh` los genera con el comando
  `openssl`, usando archivos de extensiones (`-extfile`) para no depender de
  `-addext`.
- La clave de la autoridad no se guarda: regenerar crea una autoridad nueva y
  todos los certificados.
- `tests/fixtures/tls/README.md` explica:
  - que las claves son solo de prueba y no protegen nada;
  - cómo regenerarlas (`sh tests/fixtures/tls/make_certs.sh`);
  - que hay que volver a ejecutar los tests después.

### 5. Servidor TLS local en los tests
- **Parámetro nuevo de `LocalServer`:** `tls=(certfile, keyfile, cipher)`,
  opcional. Sin él, el servidor funciona igual que ahora (HTTP).
- **Contexto del servidor:**
  - `PROTOCOL_TLS_SERVER`, `minimum_version = maximum_version = TLSv1_2`;
  - `set_ciphers(cipher)` con un solo cifrado;
  - el socket se envuelve al aceptar cada conexión con
    `wrap_socket(…, server_side=True, do_handshake_on_connect=False)`;
  - el saludo TLS (`do_handshake()`) se hace en el hilo de cada conexión, no
    en el bucle principal del servidor. Así un cliente lento o que falla no
    bloquea a los demás.
- **`url()`:** devuelve `https://127.0.0.1:<puerto>…` cuando hay TLS.
- **Qué se prueba con el servidor:** la CLI se lanza con `run_cli`,
  `--url https://127.0.0.1:<puerto>/api` y una base temporal.
  - Para que confíe en la autoridad de prueba, se pasa
    `env={"SSL_CERT_FILE": "<ruta de tests/fixtures/tls/ca.pem>"}`. OpenSSL lee
    esa variable al cargar las autoridades por defecto
    (`create_default_context()` → `load_default_certs()`).
  - En el escenario de certificado autofirmado, la variable apunta a `ca.pem`:
    la autoridad de prueba no firmó ese certificado, así que falla igualmente.
- **Bloqueo de red:** los tests de dentro del proceso (cliente directo)
  conectan a `127.0.0.1`, que `tests/conftest.py` ya permite.
- **Redirección HTTPS → HTTPS:**
  - el servidor A (solo `AES256-GCM-SHA384`) responde 301 hacia el servidor B
    (solo `AES128-GCM-SHA256`, mismo certificado `localhost`);
  - B responde el JSON válido;
  - se comprueba que la captura se guarda y que A y B reciben una petición
    cada uno. Seguir la redirección cuenta como la misma petición, según
    «Descarga única de precios en JSON».

### 6. `SSL_CERT_FILE` solo en los tests
- La variable solo aparece en los tests, siempre pasada al subproceso con
  `run_cli(env=…)`.
- Nunca se fija en `Dockerfile`, `docker-compose.yml`, `container/`, el
  código de `src/` ni la documentación de uso. Si se fijara, la ingesta real
  confiaría en la autoridad de prueba.
- El código y los comentarios de `src/` y `container/` no nombran la
  variable, ni siquiera para explicarla. La explicación vive en este design y
  en los tests.
- Un test unitario lee `Dockerfile`, `docker-compose.yml` y los archivos de
  `src/` y `container/`, y comprueba que ninguno contiene `SSL_CERT_FILE`. Así un cambio
  futuro que la añada por error rompe los tests.

## Risks / Trade-offs

- **[Riesgo] Pérdida de secreto hacia adelante con la API.** → Aceptado por
  la decisión 3 (datos públicos, sin credenciales). Se revisará si la API
  vuelve a admitir ECDHE o si algún día se envían datos privados.
- **[Riesgo] Otra versión de OpenSSL cambia la lista o el nivel por
  defecto.** → La lista se toma del propio contexto y el nivel es
  `max(2, nivel por defecto)`. Los tests comparan con el contexto por defecto
  de la misma máquina, no con valores escritos a mano.
- **[Compromiso] En una máquina con nivel de seguridad 3 o más, la conexión
  con la API puede seguir fallando.** Ese nivel exige claves RSA de al menos
  3072 bits, y la API usa intercambio RSA. → Es intencionado: se respeta la
  política de la máquina antes que conectar. En las máquinas del proyecto (Mac
  e imagen Docker) el nivel es 2.
- **[Riesgo] Los certificados de prueba dejan de valer con un Python más
  estricto.** → Se generan con las extensiones que exige `VERIFY_X509_STRICT`.
  Si aun así fallan, se regeneran con el script.
- **[Riesgo] Alguien exporta `SSL_CERT_FILE` en su terminal al lanzar la
  ingesta real.** → Afectaría también a curl y a cualquier programa con
  OpenSSL. Queda fuera de este cambio, y la decisión 6 impide fijarla en el
  proyecto.
- **[Riesgo] La imagen Docker existente no tiene el arreglo.** → El README
  ya pide `docker compose build` tras cada cambio del código. La comprobación
  real del usuario empieza por ahí (tasks, grupo 5).

## Migration Plan

- No hay migración de datos.
- Después de implementar:
  1. `docker compose build`.
  2. El usuario lanza `docker compose run --rm ingest` y la ingesta sin
     Docker, y pasa los resultados.
  3. Con código 0 se completa también la tarea 6.3 de `add-container-setup`.
- **Vuelta atrás:** quitar `context=` de `urlopen` y la función
  `tls_context()`. Con eso la ingesta vuelve a los cifrados por defecto y la
  API vuelve a fallar.
