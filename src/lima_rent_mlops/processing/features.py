"""Variables del modelo. Son exactamente los campos que pide la página Predictor."""

from __future__ import annotations

import pandas as pd

NUMERIC = ["area_m2", "dormitorios", "banos", "cocheras", "piso"]
CATEGORICAL = ["distrito"]
FEATURES = CATEGORICAL + NUMERIC
TARGET = "precio_pen"


def to_model_frame(df: pd.DataFrame, districts: list[str]) -> pd.DataFrame:
    """Prepara X con tipos estables: el distrito como categoría con la lista del entrenamiento.

    Un distrito que el modelo no vio queda como NaN y LightGBM lo trata como faltante.
    """
    X = pd.DataFrame(index=df.index)
    X["distrito"] = pd.Categorical(df["distrito"], categories=districts)
    for column in NUMERIC:
        X[column] = pd.to_numeric(df.get(column), errors="coerce").astype("float64")
    return X[FEATURES]
