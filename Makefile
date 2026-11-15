.PHONY: install check test smoke render up down demo weekly
COMPOSE = docker compose -f deploy/compose/docker-compose.yml

install:  ## Entorno local con todas las dependencias (pipeline, api, dashboard, dev)
	uv sync --all-extras

check:  ## Lint
	uv run ruff check src tests scripts

test:  ## Pruebas unitarias y de punta a punta (datos sintéticos, sin internet)
	MLFLOW_DISABLE_AGENT_HINT=1 uv run pytest -q

smoke:  ## Dos semanas simuladas en una carpeta temporal
	rm -rf .smoke && mkdir -p .smoke
	DATA_URI=.smoke/data MLFLOW_TRACKING_URI=sqlite:///.smoke/mlflow.db OPTUNA_TRIALS=3 \
		uv run lima-rent weekly --fixture 800 --fixture-days-ago 7
	DATA_URI=.smoke/data MLFLOW_TRACKING_URI=sqlite:///.smoke/mlflow.db OPTUNA_TRIALS=3 \
		uv run lima-rent weekly --fixture 300 --fixture-seed 1 --fixture-shift 0.4
	test -s .smoke/data/models/champion/meta.json
	test -s .smoke/data/monitoring/drift.parquet

render:  ## Valida que los manifiestos de Kubernetes rendericen
	kubectl kustomize deploy/k3s/overlays/prod > /dev/null

up:  ## Todo el sistema en Docker (SeaweedFS imita a OCI Object Storage)
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

demo:  ## Corre dos semanas sintéticas dentro de Docker Compose
	$(COMPOSE) run --rm pipeline lima-rent weekly --fixture 800 --fixture-days-ago 7
	$(COMPOSE) run --rm pipeline lima-rent weekly --fixture 300 --fixture-seed 1 --fixture-shift 0.4

weekly:  ## Corrida real (scraping de Infocasas) contra el lago configurado en .env
	uv run lima-rent weekly
