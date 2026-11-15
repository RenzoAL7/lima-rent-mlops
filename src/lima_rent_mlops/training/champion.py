"""Dónde vive el champion en el lago de datos y cómo cargarlo.

Módulo liviano a propósito: la API lo importa y su imagen no trae MLflow ni Optuna, solo
LightGBM. Lo que entrena y promueve está en train.py y promote.py.
"""

from __future__ import annotations

import pandas as pd

from ..storage import Storage
from .model import RentModel

CHAMPION_PREFIX = "models/champion/"
HISTORY_KEY = "models/history.json"


def load_champion(storage: Storage) -> RentModel | None:
    if not storage.exists(CHAMPION_PREFIX + "meta.json"):
        return None
    files = {
        key.removeprefix(CHAMPION_PREFIX): storage.read_bytes(key)
        for key in storage.list(CHAMPION_PREFIX)
        if key.endswith((".txt", ".json"))
    }
    return RentModel.from_files(files)


def load_reference(storage: Storage) -> pd.DataFrame:
    return storage.read_parquet_or_empty(CHAMPION_PREFIX + "reference.parquet")
