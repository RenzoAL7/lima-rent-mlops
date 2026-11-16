# syntax=docker/dockerfile:1
# API de predicción. Solo arm64: se construye en el Mac (Apple Silicon) o en un runner ARM.
FROM ghcr.io/astral-sh/uv:0.12.18 AS uv

# Etapa 1: dependencias. Solo se reconstruye cuando cambia uv.lock; la caché de uv vive en un
# mount y no llega a la imagen.
FROM python:3.12-slim-bookworm AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra api
# Quita pruebas, cabeceras C y datos sin uso de las librerías (ver el script).
RUN --mount=type=bind,source=docker/podar-venv.sh,target=/podar-venv.sh \
    sh /podar-venv.sh /opt/venv

# Etapa 2: el código del proyecto, instalado aparte con la misma estructura que el entorno
# (/opt/app/lib/..., /opt/app/bin) para copiarlo encima como una capa propia.
FROM deps AS app
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-deps --prefix /opt/app .

# Etapa 3: solo Python, las dependencias y el código; sin uv ni fuentes.
FROM python:3.12-slim-bookworm
# libgomp1: OpenMP, que LightGBM necesita en Linux.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --home-dir /tmp app
# Dos capas: las dependencias (cientos de MB, casi nunca cambian) y el código (KB, cambia en
# cada commit). Al desplegar, el clúster solo descarga la segunda.
COPY --link --from=deps /opt/venv /opt/venv
COPY --link --from=app /opt/app /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HOME=/tmp
USER 1000
EXPOSE 8080
CMD ["uvicorn", "lima_rent_mlops.serving.api:app", "--host", "0.0.0.0", "--port", "8080"]
# Al final: el commit cambia en cada construcción y no debe invalidar las capas de arriba.
ARG VCS_REF=dev
LABEL org.opencontainers.image.source=https://github.com/RenzoAL7/lima-rent-mlops \
      org.opencontainers.image.revision=$VCS_REF
