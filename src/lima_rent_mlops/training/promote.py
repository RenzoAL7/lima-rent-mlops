"""Champion vs challenger: el nuevo modelo solo se promueve si mejora sobre los mismos datos.

Ambos se evalúan en el holdout del challenger (avisos que ninguno de los dos usó para entrenar,
salvo que el champion sea anterior: entonces son incluso más "futuros" para él).
Al promover se actualiza el alias en MLflow y se exporta el modelo a models/champion/ del
lago de datos, desde donde lo carga la API.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from ..config import Settings
from ..processing.features import FEATURES, TARGET
from ..storage import Storage
from .champion import CHAMPION_PREFIX, HISTORY_KEY, load_champion
from .evaluate import metrics
from .model import RentModel
from .train import TrainResult

log = logging.getLogger(__name__)
REFERENCE_ROWS = 5000


def decide(result: TrainResult, champion: RentModel | None, settings: Settings) -> dict:
    challenger = result.holdout_metrics
    if champion is None:
        return {"promover": True, "motivo": "no hay champion", "mae_champion": None}
    champion_metrics = metrics(result.holdout[TARGET], champion.predict(result.holdout))
    threshold = champion_metrics["mae"] * (1 - settings.min_improvement)
    better = challenger["mae"] < threshold
    motivo = (
        f"MAE {challenger['mae']:.0f} vs {champion_metrics['mae']:.0f} del champion"
        + (" (mejora)" if better else f" (no mejora el {settings.min_improvement:.0%} exigido)")
    )
    return {"promover": better, "motivo": motivo, "mae_champion": champion_metrics["mae"],
            "mape_champion": champion_metrics["mape"]}


def promote(result: TrainResult, storage: Storage, settings: Settings, reason: str) -> dict:
    champion = load_champion(storage)
    decision = decide(result, champion, settings)
    event = {
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": result.version,
        "razon_reentrenamiento": reason,
        "decision": "promovido" if decision["promover"] else "rechazado",
        "detalle": decision["motivo"],
        "version_anterior": champion.meta.get("version") if champion else None,
        "n_train": len(result.train),
        **{f"{k}_holdout": v for k, v in result.holdout_metrics.items()},
        "mae_champion_anterior": decision.get("mae_champion"),
    }
    if decision["promover"]:
        _export(result, storage)
        _set_alias(settings, result.version)
        log.info("Promovido %s: %s", result.version, decision["motivo"])
    else:
        log.info("Challenger %s rechazado: %s", result.version, decision["motivo"])
    history = storage.read_json(HISTORY_KEY, default=[])
    storage.write_json([*history, event], HISTORY_KEY)
    return event


def _export(result: TrainResult, storage: Storage) -> None:
    meta_extra = {"promovido_en": datetime.now(UTC).isoformat(timespec="seconds")}
    result.model.meta.update(meta_extra)
    for name, data in result.model.to_files().items():
        storage.write_bytes(CHAMPION_PREFIX + name, data)
    # Muestra del entrenamiento: es la referencia contra la que se mide el drift.
    reference = result.train[[*FEATURES, TARGET, "precio_m2_pen"]].copy()
    reference = reference.sample(min(len(reference), REFERENCE_ROWS), random_state=42)
    reference = reference.join(result.model.predict(reference)[["p50"]])
    storage.write_parquet(reference.reset_index(drop=True), CHAMPION_PREFIX + "reference.parquet")


def _set_alias(settings: Settings, version: str | None) -> None:
    if not version:
        return
    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    MlflowClient().set_registered_model_alias(settings.model_name, "champion", version)
