# syntax=docker/dockerfile:1
# API de predicción. Solo arm64: se construye en el Mac (Apple Silicon) o en un runner ARM.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

# Etapa 1: uv arma el entorno virtual. Su caché vive en un mount y no llega a la imagen.
FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
# Primero solo las dependencias (capa cacheable), después el código.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra api
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --extra api

# Etapa 2: solo Python y el entorno virtual; sin uv ni código fuente.
FROM python:3.12-slim-bookworm
ARG VCS_REF=dev
# libgomp1: OpenMP, que LightGBM necesita en Linux.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --home-dir /tmp app
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp
LABEL org.opencontainers.image.source=https://github.com/RenzoAL7/lima-rent-mlops \
      org.opencontainers.image.revision=$VCS_REF
USER 1000
EXPOSE 8080
CMD ["uvicorn", "lima_rent_mlops.serving.api:app", "--host", "0.0.0.0", "--port", "8080"]
