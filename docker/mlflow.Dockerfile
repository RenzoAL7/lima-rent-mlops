# syntax=docker/dockerfile:1
# Servidor de MLflow (tracking + registry). Imagen propia para garantizar arm64.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# Solo las dependencias del extra "tracking": el servidor no necesita el código del proyecto.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra tracking
# Quita pruebas, cabeceras C y datos sin uso de las librerías (ver el script).
RUN --mount=type=bind,source=docker/podar-venv.sh,target=/podar-venv.sh \
    sh /podar-venv.sh /opt/venv

FROM python:3.12-slim-bookworm
RUN useradd --uid 1000 --no-create-home --home-dir /tmp app
COPY --link --from=build /opt/venv /opt/venv
# OCI Object Storage (API S3): estilo "path" y sin los checksums nuevos de boto3.
COPY docker/aws-config /etc/aws/config
# MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false: MLflow 3.x arranca por defecto un "job runner" (huey)
# con ~9 procesos extra y ~2 GB más de memoria. Aquí solo se usa tracking + registry, y con él
# el pod supera su límite de 768 Mi y muere por OOM al arrancar.
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp MLFLOW_DISABLE_AGENT_HINT=1 \
    MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false \
    AWS_CONFIG_FILE=/etc/aws/config \
    AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
USER 1000
EXPOSE 5000
# El destino de artefactos y la base de datos llegan por variables de entorno.
CMD ["sh", "-c", "exec mlflow server --host 0.0.0.0 --port 5000 --workers 1 \
     --backend-store-uri \"$MLFLOW_BACKEND_STORE_URI\" \
     --artifacts-destination \"$MLFLOW_ARTIFACTS_DESTINATION\" --serve-artifacts \
     --allowed-hosts \"$MLFLOW_ALLOWED_HOSTS\""]
# Al final: el commit cambia en cada construcción y no debe invalidar las capas de arriba.
ARG VCS_REF=dev
LABEL org.opencontainers.image.source=https://github.com/RenzoAL7/lima-rent-mlops \
      org.opencontainers.image.revision=$VCS_REF
