"""Métricas de error. Se usan igual al entrenar (holdout) y cada semana (ground truth)."""

from __future__ import annotations

import numpy as np
import pandas as pd

TOTAL = "Total"


def metrics(y: pd.Series, pred: pd.DataFrame) -> dict[str, float]:
    y = y.to_numpy(dtype=float)
    p50 = pred["p50"].to_numpy()
    error = np.abs(y - p50)
    inside = (y >= pred["p10"].to_numpy()) & (y <= pred["p90"].to_numpy())
    return {
        "n": int(len(y)),
        "mae": float(error.mean()) if len(y) else float("nan"),
        "mape": float((error / y).mean()) if len(y) else float("nan"),
        "mdape": float(np.median(error / y)) if len(y) else float("nan"),
        # Fracción de precios reales dentro del intervalo p10–p90 (ideal: cerca de 0.80).
        "cobertura": float(inside.mean()) if len(y) else float("nan"),
    }


def metrics_by_district(df: pd.DataFrame, y_col: str = "precio_pen") -> pd.DataFrame:
    """Métricas totales y por distrito para un DataFrame que ya trae p10, p50 y p90."""
    rows = [{"distrito": TOTAL, **metrics(df[y_col], df)}]
    for district, group in df.groupby("distrito", observed=True):
        rows.append({"distrito": district, **metrics(group[y_col], group)})
    return pd.DataFrame(rows)
