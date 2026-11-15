"""Performance con ground truth: el champion predice los avisos nuevos y se compara con su
precio publicado, que el modelo nunca vio. Así se mide el error real semana a semana."""

from __future__ import annotations

import pandas as pd

from ..training.evaluate import metrics_by_district
from ..training.model import RentModel


def evaluate_new_listings(model: RentModel, new: pd.DataFrame, week: str):
    """Devuelve (predicciones por aviso, métricas por distrito y total)."""
    predictions = new[["id", "distrito", "area_m2", "dormitorios", "banos", "cocheras", "piso",
                       "precio_pen", "precio_m2_pen", "latitud", "longitud"]].copy()
    predictions = predictions.join(model.predict(new))
    predictions["error"] = predictions["p50"] - predictions["precio_pen"]
    predictions["error_pct"] = predictions["error"] / predictions["precio_pen"]
    predictions["semana"] = week
    predictions["version_modelo"] = model.meta.get("version")
    perf = metrics_by_district(predictions)
    perf["semana"] = week
    perf["version_modelo"] = model.meta.get("version")
    return predictions, perf
