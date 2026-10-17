# Spec Delta

## ADDED Requirements

### Requirement: API en el VPS solo por túnel SSH
El runbook SHALL describir cómo actualizar el VPS a la versión con la API,
comprobar que la API responde dentro del servidor, que su puerto solo
escucha en `127.0.0.1` y que `ufw` sigue igual, y cómo usarla desde el Mac
con un túnel SSH. MUST NOT indicar abrir ningún puerto en `ufw` ni publicar
la API en otra dirección.

#### Scenario: Actualización a la versión con la API
- **WHEN** se sigue el procedimiento de actualización para esta versión
- **THEN** tras `docker compose up -d` indica comprobar que `docker compose ps` muestra el programador y la API en marcha, que `curl -s http://127.0.0.1:8000/api/health` en el VPS devuelve `status` `ok`, que `sudo ss -tlnp` solo muestra `127.0.0.1:8000` para ese puerto, y que `sudo ufw status` sigue mostrando solo OpenSSH

#### Scenario: Salud justo después de arrancar
- **WHEN** el `curl` de la salud justo después de `docker compose up -d` devuelve `base_ocupada` (el programador recién arrancado está guardando una captura) o `status` `desactualizada`
- **THEN** el runbook indica repetirlo pasados unos segundos o tras la siguiente captura, y solo investigar si sigue igual

#### Scenario: Túnel desde el Mac
- **WHEN** se lee el paso de uso desde el Mac
- **THEN** da el comando `ssh -N -L 8000:127.0.0.1:8000 deploy@<IP_DEL_VPS>`, explica que mientras está abierto la API se usa en `http://127.0.0.1:8000/api/docs` del Mac, cómo cerrarlo (Ctrl+C), y que si el puerto 8000 del Mac está ocupado (por ejemplo, por la API local) se usa otro puerto local como `-L 8001:127.0.0.1:8000`

#### Scenario: Sin secretos
- **WHEN** se revisa el runbook
- **THEN** usa el marcador `<IP_DEL_VPS>` y no contiene la dirección real del servidor ni claves

#### Scenario: Puerto expuesto por error
- **WHEN** `sudo ss -tlnp` muestra `0.0.0.0:8000` o `[::]:8000`
- **THEN** el runbook indica parar la API con `docker compose stop api` en ese momento y revisar los puertos del servicio `api` en `docker-compose.yml`, sin tocar `ufw`
