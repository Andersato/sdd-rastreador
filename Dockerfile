# Imagen de la ingesta de precios: solo el código necesario para ejecutarla,
# más supercronic para el programador.

# Etapa aparte: descarga supercronic y comprueba su suma. A la imagen final
# solo pasa el binario. Versión y sumas fijadas (ver design.md, D9).
FROM python:3.12-slim-bookworm AS supercronic
ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.49
ARG SUPERCRONIC_SHA256_AMD64=a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1
ARG SUPERCRONIC_SHA256_ARM64=02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5
COPY container/fetch_supercronic.py /tmp/fetch_supercronic.py
RUN TARGETARCH="$TARGETARCH" SUPERCRONIC_VERSION="$SUPERCRONIC_VERSION" \
    SUPERCRONIC_SHA256_AMD64="$SUPERCRONIC_SHA256_AMD64" \
    SUPERCRONIC_SHA256_ARM64="$SUPERCRONIC_SHA256_ARM64" \
    python /tmp/fetch_supercronic.py /supercronic

FROM python:3.12-slim-bookworm

# PYTHONPATH: los scripts de container/ importan el paquete `src`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Usuario sin privilegios por defecto (sin Compose); Compose lo sustituye por
# el UID/GID del usuario del host.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

COPY --from=supercronic --chmod=755 /supercronic /usr/local/bin/supercronic

WORKDIR /app
COPY src/ /app/src/
COPY container/ /app/container/

USER 10001:10001
ENTRYPOINT ["python", "/app/container/entrypoint.py"]
