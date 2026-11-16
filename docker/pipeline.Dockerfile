# syntax=docker/dockerfile:1
# Pipeline semanal: scraping, limpieza, entrenamiento, monitoreo. Solo arm64.
# Mismas etapas que api.Dockerfile.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

FROM python:3.12-slim-bookworm AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra pipeline
RUN --mount=type=bind,source=docker/podar-venv.sh,target=/podar-venv.sh \
    sh /podar-venv.sh /opt/venv

FROM deps AS app
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-deps --prefix /opt/app .

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --home-dir /tmp app
COPY --link --from=deps /opt/venv /opt/venv
COPY --link --from=app /opt/app /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp MLFLOW_DISABLE_AGENT_HINT=1
# MLflow escribe archivos temporales; en el clúster /tmp es un emptyDir.
WORKDIR /tmp
USER 1000
CMD ["lima-rent", "--help"]
ARG VCS_REF=dev
LABEL org.opencontainers.image.source=https://github.com/RenzoAL7/lima-rent-mlops \
      org.opencontainers.image.revision=$VCS_REF
