# syntax=docker/dockerfile:1
# Dashboard AlquiLima (Streamlit). Solo arm64.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra dashboard
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --extra dashboard

FROM python:3.12-slim-bookworm
ARG VCS_REF=dev
RUN useradd --uid 1000 --no-create-home --home-dir /tmp app
COPY --from=build /opt/venv /opt/venv
# Streamlit necesita un script de entrada en disco y lee .streamlit/config.toml de la carpeta
# donde arranca; las páginas importan el paquete ya instalado en /opt/venv.
COPY src/lima_rent_mlops/dashboard /app/dashboard
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp
LABEL org.opencontainers.image.source=https://github.com/RenzoAL7/lima-rent-mlops \
      org.opencontainers.image.revision=$VCS_REF
WORKDIR /app/dashboard
USER 1000
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
