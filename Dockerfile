# Imagen de la ingesta de precios: solo el código necesario para ejecutarla.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Usuario sin privilegios por defecto (sin Compose); Compose lo sustituye por
# el UID/GID del usuario del host.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY src/ /app/src/
COPY container/ /app/container/

USER 10001:10001
ENTRYPOINT ["python", "/app/container/entrypoint.py"]
