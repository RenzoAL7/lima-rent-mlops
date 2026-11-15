"""Entrena un challenger: búsqueda con Optuna, ajuste final y registro en MLflow.

Validación temporal: los avisos más recientes quedan fuera del entrenamiento (holdout), igual
que en producción, donde el modelo siempre predice avisos posteriores a los que vio.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import optuna
import pandas as pd

from ..config import Settings
from ..processing.features import FEATURES, TARGET
from .evaluate import metrics, metrics_by_district
from .model import RentModel

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
log = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass
class TrainResult:
    model: RentModel
    holdout: pd.DataFrame  # avisos de prueba con p10/p50/p90
    holdout_metrics: dict
    by_district: pd.DataFrame
    train: pd.DataFrame
    run_id: str | None = None
    version: str | None = None


def temporal_split(df: pd.DataFrame, fraction: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ordena por cuándo se vio el aviso (y su fecha de publicación) y separa lo más reciente."""
    order = df.sort_values(["primera_vez_visto", "fecha_publicacion", "id"], na_position="first")
    cut = int(len(order) * (1 - fraction))
    return order.iloc[:cut].copy(), order.iloc[cut:].copy()


def _objective(train: pd.DataFrame, valid: pd.DataFrame):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 8, 64, log=True),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 5, 60),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 1.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
            "cat_smooth": trial.suggest_float("cat_smooth", 1.0, 30.0),
        }
        rounds = trial.suggest_int("num_boost_round", 100, 800, step=50)
        model = RentModel.fit(train, params, rounds)
        return metrics(valid[TARGET], model.predict(valid))["mae"]

    return objective


def fit_challenger(silver: pd.DataFrame, settings: Settings) -> TrainResult:
    train, holdout = temporal_split(silver, settings.holdout_fraction)
    inner_train, inner_valid = temporal_split(train, settings.holdout_fraction)
    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(_objective(inner_train, inner_valid), n_trials=settings.optuna_trials)
    best = dict(study.best_params)
    rounds = best.pop("num_boost_round")
    log.info("Optuna: MAE validación %.1f con %s", study.best_value, best)

    model = RentModel.fit(train, best, rounds)
    holdout = holdout.join(model.predict(holdout))
    result_metrics = metrics(holdout[TARGET], holdout)
    model.meta.update({
        "holdout_metrics": result_metrics,
        "optuna_best_valid_mae": study.best_value,
        "trained_until": str(train["primera_vez_visto"].max()),
    })
    return TrainResult(model, holdout, result_metrics, metrics_by_district(holdout), train)


def log_to_mlflow(result: TrainResult, settings: Settings, reason: str) -> TrainResult:
    """Registra parámetros, métricas y el modelo como nueva versión con alias 'challenger'."""
    import mlflow
    from mlflow import MlflowClient

    from .registry import RentPyfunc

    if settings.mlflow_tracking_uri.startswith("sqlite:///"):
        Path(settings.mlflow_tracking_uri.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True)
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    with mlflow.start_run(run_name=f"challenger: {reason}"[:250]) as run:
        mlflow.set_tags({"razon": reason, "features": ",".join(FEATURES)})
        mlflow.log_params({**result.model.meta["params"],
                           "num_boost_round": result.model.meta["num_boost_round"],
                           "n_train": len(result.train), "n_holdout": len(result.holdout)})
        mlflow.log_metrics({f"holdout_{k}": v for k, v in result.holdout_metrics.items()
                            if isinstance(v, float) and np.isfinite(v)})
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            bundle.mkdir()
            for name, data in result.model.to_files().items():
                (bundle / name).write_bytes(data)
            result.by_district.to_csv(Path(tmp) / "metricas_por_distrito.csv", index=False)
            mlflow.log_artifact(str(Path(tmp) / "metricas_por_distrito.csv"))
            info = mlflow.pyfunc.log_model(
                name="model",
                python_model=RentPyfunc(),
                artifacts={"bundle": str(bundle)},
                registered_model_name=settings.model_name,
                pip_requirements=["lightgbm>=4.6", "pandas>=2.2", "numpy>=2.2"],
                input_example=result.holdout[FEATURES].head(3),
            )
        result.run_id = run.info.run_id
        result.version = str(info.registered_model_version)
    client = MlflowClient()
    client.set_registered_model_alias(settings.model_name, "challenger", result.version)
    client.set_model_version_tag(settings.model_name, result.version, "razon", reason)
    result.model.meta.update({"mlflow_run_id": result.run_id, "version": result.version,
                              "razon": reason})
    log.info("MLflow: %s versión %s (challenger)", settings.model_name, result.version)
    return result
