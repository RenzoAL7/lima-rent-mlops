"""El modelo: tres LightGBM de regresión por cuantiles sobre log(precio).

- p50 es la estimación puntual (mediana).
- p10 y p90 forman un intervalo del 80%: la página Predictor lo muestra y sirve para decir si
  un aviso está "caro" (sobre p90) o "barato" (bajo p10).

Se guarda como archivos de texto (un booster por cuantil + meta.json): la API los carga sin
depender de MLflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..processing.features import CATEGORICAL, FEATURES, TARGET, to_model_frame

QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
BASE_PARAMS = {"verbosity": -1, "seed": 42, "deterministic": True, "num_threads": 2}


@dataclass
class RentModel:
    boosters: dict[str, lgb.Booster]
    districts: list[str]
    meta: dict = field(default_factory=dict)

    @classmethod
    def fit(cls, df: pd.DataFrame, params: dict, num_boost_round: int) -> RentModel:
        districts = sorted(df["distrito"].dropna().unique().tolist())
        X = to_model_frame(df, districts)
        y = np.log(df[TARGET].to_numpy(dtype=float))
        boosters = {}
        for name, alpha in QUANTILES.items():
            dataset = lgb.Dataset(X, y, categorical_feature=CATEGORICAL, free_raw_data=False)
            boosters[name] = lgb.train(
                {**BASE_PARAMS, **params, "objective": "quantile", "alpha": alpha},
                dataset,
                num_boost_round=num_boost_round,
            )
        meta = {
            "features": FEATURES,
            "target": TARGET,
            "quantiles": QUANTILES,
            "params": params,
            "num_boost_round": num_boost_round,
            "n_train": len(df),
        }
        return cls(boosters, districts, meta)

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        X = to_model_frame(df, self.districts)
        raw = np.column_stack([self.boosters[n].predict(X) for n in QUANTILES])
        # Los cuantiles se entrenan por separado y pueden cruzarse: se ordenan por fila.
        raw = np.sort(raw, axis=1)
        return pd.DataFrame(np.exp(raw), columns=list(QUANTILES), index=df.index)

    # --- persistencia -----------------------------------------------------------------
    def to_files(self) -> dict[str, bytes]:
        files = {f"{n}.txt": b.model_to_string().encode() for n, b in self.boosters.items()}
        meta = {**self.meta, "districts": self.districts}
        files["meta.json"] = json.dumps(meta, ensure_ascii=False, indent=2, default=str).encode()
        return files

    @classmethod
    def from_files(cls, files: dict[str, bytes]) -> RentModel:
        meta = json.loads(files["meta.json"])
        boosters = {n: lgb.Booster(model_str=files[f"{n}.txt"].decode()) for n in QUANTILES}
        return cls(boosters, meta.pop("districts"), meta)
