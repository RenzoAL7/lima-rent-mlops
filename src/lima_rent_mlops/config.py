"""Configuración leída de variables de entorno.

Toda la configuración vive aquí para que el mismo código corra en el Mac, en CI, en Docker
Compose y en K3s cambiando solo variables de entorno (ver .env.example).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


@dataclass(frozen=True)
class Settings:
    # Dónde vive el lago de datos: una carpeta local o s3://bucket.
    data_uri: str = field(default_factory=lambda: _env("DATA_URI", "data"))
    s3_endpoint_url: str = field(default_factory=lambda: _env("S3_ENDPOINT_URL"))
    s3_region: str = field(default_factory=lambda: _env("S3_REGION", "us-ashburn-1"))
    s3_access_key_id: str = field(default_factory=lambda: _env("S3_ACCESS_KEY_ID"))
    s3_secret_access_key: str = field(default_factory=lambda: _env("S3_SECRET_ACCESS_KEY"))

    # MLflow: servidor en el clúster, o SQLite local mientras se desarrolla.
    mlflow_tracking_uri: str = field(
        default_factory=lambda: _env("MLFLOW_TRACKING_URI", "sqlite:///data/mlflow.db")
    )
    mlflow_experiment: str = field(default_factory=lambda: _env("MLFLOW_EXPERIMENT", "lima-rent"))
    model_name: str = field(default_factory=lambda: _env("MODEL_NAME", "lima-rent"))

    # Scraping: lento a propósito (ver docs/datos.md).
    scrape_delay_seconds: float = field(default_factory=lambda: _float("SCRAPE_DELAY_SECONDS", 4.0))
    scrape_max_pages: int = field(default_factory=lambda: _int("SCRAPE_MAX_PAGES", 300))
    user_agent: str = field(
        default_factory=lambda: _env(
            "SCRAPE_USER_AGENT",
            "lima-rent-mlops/0.1 (proyecto educativo; +https://github.com/RenzoAL7/lima-rent-mlops)",
        )
    )

    # Entrenamiento.
    optuna_trials: int = field(default_factory=lambda: _int("OPTUNA_TRIALS", 30))
    holdout_fraction: float = field(default_factory=lambda: _float("HOLDOUT_FRACTION", 0.15))

    # Reglas de reentrenamiento y promoción.
    psi_threshold: float = field(default_factory=lambda: _float("PSI_THRESHOLD", 0.2))
    mape_threshold: float = field(default_factory=lambda: _float("MAPE_THRESHOLD", 0.25))
    min_new_listings: int = field(default_factory=lambda: _int("MIN_NEW_LISTINGS", 30))
    min_improvement: float = field(default_factory=lambda: _float("MIN_IMPROVEMENT", 0.01))

    # Servicios.
    api_url: str = field(default_factory=lambda: _env("API_URL", "http://localhost:8080"))
    model_reload_seconds: int = field(default_factory=lambda: _int("MODEL_RELOAD_SECONDS", 300))

    @property
    def is_s3(self) -> bool:
        return self.data_uri.startswith("s3://")


def get_settings() -> Settings:
    return Settings()
