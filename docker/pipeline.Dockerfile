# syntax=docker/dockerfile:1
# Pipeline semanal: scraping, limpieza, entrenamiento, monitoreo. Solo arm64.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra pipeline
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --extra pipeline

FROM python:3.12-slim-bookworm
ARG VCS_REF=dev
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --home-dir /tmp app
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp MLFLOW_DISABLE_AGENT_HINT=1
LABEL org.opencontainers.image.source=https://github.com/RenzoAL7/lima-rent-mlops \
      org.opencontainers.image.revision=$VCS_REF
# MLflow escribe archivos temporales; en el clúster /tmp es un emptyDir.
WORKDIR /tmp
USER 1000
CMD ["lima-rent", "--help"]
