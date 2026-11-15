"""Drift: ¿los avisos nuevos se parecen a los que vio el modelo al entrenar?

- PSI (Population Stability Index): compara la distribución de una variable en la referencia
  (entrenamiento del champion) y en los avisos nuevos. Regla usual: < 0.1 estable,
  0.1–0.2 cambio moderado, > 0.2 cambio importante.
- Prueba KS (Kolmogorov–Smirnov) para variables numéricas: un p-valor bajo indica que las dos
  muestras probablemente vienen de distribuciones distintas. Con muestras grandes casi todo
  sale "significativo", por eso la decisión de reentrenar usa el PSI.

Se implementa a mano (unas 40 líneas) en vez de con Evidently para que se vea qué se mide y
para no sumar cientos de MB a la imagen del pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ..processing.features import CATEGORICAL, NUMERIC

EPS = 1e-4


def psi_numeric(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    ref, cur = reference.dropna().to_numpy(float), current.dropna().to_numpy(float)
    if len(ref) == 0 or len(cur) == 0:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # variable casi constante: compara por valores
        return psi_categorical(reference.astype(str), current.astype(str))
    edges[0], edges[-1] = -np.inf, np.inf
    ref_pct = np.histogram(ref, edges)[0] / len(ref)
    cur_pct = np.histogram(cur, edges)[0] / len(cur)
    return _psi(ref_pct, cur_pct)


def psi_categorical(reference: pd.Series, current: pd.Series) -> float:
    ref = reference.astype(str).value_counts(normalize=True)
    cur = current.astype(str).value_counts(normalize=True)
    categories = ref.index.union(cur.index)
    return _psi(ref.reindex(categories, fill_value=0).to_numpy(),
                cur.reindex(categories, fill_value=0).to_numpy())


def _psi(ref_pct: np.ndarray, cur_pct: np.ndarray) -> float:
    ref_pct, cur_pct = np.clip(ref_pct, EPS, None), np.clip(cur_pct, EPS, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def feature_drift(reference: pd.DataFrame, current: pd.DataFrame, threshold: float,
                  week: str) -> pd.DataFrame:
    """Una fila por variable: PSI, p-valor KS y si supera el umbral de drift."""
    rows = []
    for column in NUMERIC + ["precio_m2_pen", "p50"]:
        if column not in reference or column not in current:
            continue
        ks = stats.ks_2samp(reference[column].dropna(), current[column].dropna())
        rows.append({"variable": column, "psi": psi_numeric(reference[column], current[column]),
                     "ks_pvalor": float(ks.pvalue)})
    for column in CATEGORICAL:
        rows.append({"variable": column, "ks_pvalor": float("nan"),
                     "psi": psi_categorical(reference[column], current[column])})
    df = pd.DataFrame(rows)
    df["tipo"] = df["variable"].map(
        lambda v: "target" if v == "precio_m2_pen" else "prediccion" if v == "p50" else "feature")
    df["drift"] = df["psi"] > threshold
    df["semana"] = week
    df["n_referencia"], df["n_actual"] = len(reference), len(current)
    return df


def target_by_week(history: pd.DataFrame) -> pd.DataFrame:
    """Mediana del precio por m² de los avisos nuevos, por semana y distrito."""
    df = history.copy()
    df["semana"] = df["primera_vez_visto"].map(week_label)
    by_district = (df.groupby(["semana", "distrito"], observed=True)["precio_m2_pen"]
                   .agg(mediana_precio_m2="median", n="size").reset_index())
    total = (df.groupby("semana")["precio_m2_pen"]
             .agg(mediana_precio_m2="median", n="size").reset_index().assign(distrito="Total"))
    return pd.concat([total, by_district], ignore_index=True)


def week_label(ts) -> str:
    iso = pd.Timestamp(ts).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
