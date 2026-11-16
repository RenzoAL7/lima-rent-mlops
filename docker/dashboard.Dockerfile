# syntax=docker/dockerfile:1
# Dashboard Lima Rent MLOps (Streamlit). Solo arm64. Mismas etapas que api.Dockerfile.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

FROM python:3.12-slim-bookworm AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra dashboard
RUN --mount=type=bind,source=docker/podar-venv.sh,target=/podar-venv.sh \
    sh /podar-venv.sh /opt/venv

FROM deps AS app
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-deps --prefix /opt/app .

FROM python:3.12-slim-bookworm
RUN useradd --uid 1000 --no-create-home --home-dir /tmp app
COPY --link --from=deps /opt/venv /opt/venv
COPY --link --from=app /opt/app /opt/venv
# Streamlit necesita un script de entrada en disco y lee .streamlit/config.toml de la carpeta
# donde arranca; las páginas importan el paquete ya instalado en /opt/venv.
COPY src/lima_rent_mlops/dashboard /app/dashboard
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app/dashboard
USER 1000
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
ARG VCS_REF=dev
LABEL org.opencontainers.image.source=https://github.com/RenzoAL7/lima-rent-mlops \
      org.opencontainers.image.revision=$VCS_REF
