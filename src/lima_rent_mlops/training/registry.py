"""Envoltorio MLflow pyfunc: permite cargar el modelo con `mlflow.pyfunc.load_model`."""

from __future__ import annotations

from pathlib import Path

import mlflow.pyfunc
import pandas as pd

from .model import QUANTILES, RentModel


class RentPyfunc(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        bundle = Path(context.artifacts["bundle"])
        files = {p.name: p.read_bytes() for p in bundle.iterdir() if p.is_file()}
        self.model = RentModel.from_files(files)

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        return self.model.predict(model_input)[list(QUANTILES)]
