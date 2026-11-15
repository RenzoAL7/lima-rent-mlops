from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lima_rent_mlops.fixture import make_fx, make_raw


@pytest.fixture
def scraped_at():
    return datetime(2026, 11, 2, 12, tzinfo=UTC)


@pytest.fixture
def raw(scraped_at):
    return make_raw(500, seed=0, scraped_at=scraped_at)


@pytest.fixture
def fx(scraped_at):
    return make_fx(scraped_at.date() - timedelta(days=60), scraped_at.date())


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Lago de datos y MLflow en una carpeta temporal; pocas pruebas de Optuna."""
    monkeypatch.setenv("DATA_URI", str(tmp_path / "data"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/mlflow.db")
    monkeypatch.setenv("OPTUNA_TRIALS", "2")
    monkeypatch.setenv("MODEL_RELOAD_SECONDS", "0")
    monkeypatch.chdir(tmp_path)
    return tmp_path
