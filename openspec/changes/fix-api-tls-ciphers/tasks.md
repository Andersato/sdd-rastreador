# Tasks

## 1. Certificados de prueba

- [ ] 1.1 Crear `tests/fixtures/tls/make_certs.sh` (design, decisión 4). Genera con `openssl` y archivos de extensiones:
  - `ca.pem`, sin guardar la clave de la autoridad;
  - `localhost.pem` y `localhost.key`, para `IP:127.0.0.1`;
  - `other.pem` y `other.key`, para `DNS:otro.example`;
  - `selfsigned.pem` y `selfsigned.key`, para `IP:127.0.0.1`.

  Todas las claves son RSA de 2048 bits, con las extensiones de design y validez de 36 500 días. Ejecutarlo y verificar:
  - con `openssl verify -x509_strict -CAfile ca.pem localhost.pem other.pem`, que los dos dan OK;
  - que `selfsigned.pem` no verifica contra `ca.pem`;
  - que `openssl x509 -noout -enddate` da una fecha de dentro de unos 100 años.
- [ ] 1.2 Escribir `tests/fixtures/tls/README.md` en español claro:
  - qué es cada archivo;
  - que las claves son solo de prueba y no protegen nada;
  - cómo regenerarlas (`sh tests/fixtures/tls/make_certs.sh`) y que después hay que ejecutar `pytest`.

  Verificar ejecutando el comando tal como está escrito.

## 2. Servidor TLS local en los tests

- [ ] 2.1 Añadir a `LocalServer` (`tests/http_server.py`) el parámetro opcional `tls=(certfile, keyfile, cipher)` (design, decisión 5): TLS 1.2 fijo, un solo cifrado y `url()` con `https://` cuando hay TLS. El saludo TLS se hace en el hilo de cada conexión. Sin `tls`, el comportamiento no cambia. Verificar en `tests/unit/test_http_server.py`:
  - con un cliente `ssl` que confía en `ca.pem`, el servidor responde con TLS 1.2 y el cifrado indicado (`AES256-GCM-SHA384` y `AES128-GCM-SHA256`);
  - un cliente que solo ofrece cifrados ECDHE no conecta;
  - el resto de ese archivo sigue pasando.

## 3. Contexto TLS de la ingesta

- [ ] 3.1 Añadir `tls_context()` a `src/ingestion/client.py` y pasarlo en `_download` a `urlopen(…, context=tls_context())`, creándolo en cada descarga (design, decisiones 1 y 2). Requisito «Cifrados ofrecidos al conectar con la API». Verificar que `pytest -m "not docker"` sigue pasando entero.
- [ ] 3.2 Tests de configuración en `tests/unit/test_tls_context.py`, comparando con `ssl.create_default_context()` en la misma máquina (escenarios «Se mantienen los cifrados por defecto», «Cifrados débiles no se ofrecen», «Versiones antiguas de TLS no se admiten» y «Verificación activa en la configuración»). Comprueban que:
  - la lista contiene todos los cifrados por defecto y los de más están entre `AES256-GCM-SHA384` y `AES128-GCM-SHA256`;
  - con 17 cifrados por defecto, los de más son exactamente esos dos;
  - no aparecen `AES256-SHA` ni `AES256-SHA256`;
  - los cifrados de TLS 1.3 son los mismos que por defecto;
  - `minimum_version` es igual que por defecto (TLS 1.2);
  - `security_level` es igual que por defecto;
  - `verify_mode == CERT_REQUIRED` y `check_hostname` es verdadero.

  Verificar que pasan.
- [ ] 3.3 Test en `tests/unit/test_tls_context.py` de que `SSL_CERT_FILE` no aparece en `Dockerfile`, `docker-compose.yml` ni en ningún archivo de `src/` o `container/`, ni siquiera en comentarios (design, decisión 6). Verificar que pasa, y que falla si se añade temporalmente la variable a una copia del texto leído.

## 4. Tests con el servidor TLS local

- [ ] 4.1 Tests funcionales en `tests/functional/test_scenarios_tls.py`. Usan `run_cli` con `--url https://127.0.0.1:<puerto>/api`, una base temporal y `env={"SSL_CERT_FILE": ca.pem}`, y la respuesta guardada `valid_two_stations.json`:
  - «Servidor que solo acepta AES256-GCM-SHA384» y «Servidor que solo acepta AES128-GCM-SHA256» → una única petición, captura con 2 estaciones y código 0;
  - «Certificado no reconocido» (`selfsigned`) y «Nombre del servidor que no coincide» (`other`) → código distinto de 0, la salida de error contiene `no se ha podido conectar con la API:` y `CERTIFICATE_VERIFY_FAILED`, y la base queda igual (`db_dump` antes y después, con una base que ya tiene 1 captura);
  - «URL sin TLS» → `--url http://127.0.0.1:<puerto>/api` con el servidor HTTP actual: una única petición y captura guardada.

  Verificar que pasan.
- [ ] 4.2 Test de redirección HTTPS → HTTPS en el mismo archivo (escenario «Redirección HTTPS a HTTPS»; design, decisiones 2 y 5). El servidor A, solo con `AES256-GCM-SHA384`, responde 301 hacia el servidor B, solo con `AES128-GCM-SHA256`, que devuelve `valid_two_stations.json`. Comprueba que A y B reciben una petición cada uno, que se guarda la captura y que el código es 0. Verificar que pasa.

## 5. Verificación final

- [ ] 5.1 Ejecutar `pytest` completo (con Docker en marcha) y `pytest -m "not docker"`. Verificar que todo pasa, que `data/prices.db` real no ha cambiado (mismo hash antes y después) y que no se ha creado `.env` en el repo.
- [ ] 5.2 Dar al usuario los comandos exactos de la comprobación real y esperar sus resultados, sin lanzarlos:
  - `docker compose build`, y después `docker compose run --rm ingest; echo "código: $?"`;
  - la ejecución sin Docker (`.venv/bin/python -m src.ingestion; echo "código: $?"`).

  Verificar con la salida que pase el usuario: código 0 y captura nueva. Con ese resultado se completa también la tarea 6.3 de `add-container-setup`.
