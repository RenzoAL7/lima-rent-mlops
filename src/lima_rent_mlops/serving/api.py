"""API de AlquiLima.

Carga el champion desde models/champion/ del lago de datos (no depende de MLflow) y revisa
cada MODEL_RELOAD_SECONDS si se promovió otra versión: un reentrenamiento llega a producción
sin redesplegar la API.

Todas las rutas cuelgan de /api para compartir dominio con el dashboard detrás de Traefik.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .. import __version__
from ..config import get_settings
from ..storage import Storage
from ..training.champion import CHAMPION_PREFIX, load_champion
from ..training.model import RentModel

log = logging.getLogger(__name__)


class ModelHolder:
    def __init__(self):
        self.settings = get_settings()
        self.storage = Storage(self.settings)
        self.model: RentModel | None = None
        self.checked_at = 0.0
        self.lock = threading.Lock()

    def get(self) -> RentModel | None:
        if time.monotonic() - self.checked_at > self.settings.model_reload_seconds:
            with self.lock:
                if time.monotonic() - self.checked_at > self.settings.model_reload_seconds:
                    self._refresh()
        return self.model

    def _refresh(self) -> None:
        self.checked_at = time.monotonic()
        try:
            meta = self.storage.read_json(CHAMPION_PREFIX + "meta.json")
            if meta is None:
                return
            current = self.model.meta.get("version") if self.model else None
            if self.model is None or meta.get("version") != current:
                self.model = load_champion(self.storage)
                log.info("Champion cargado: versión %s", self.model.meta.get("version"))
        except Exception:  # sin red o sin bucket: se sigue sirviendo el modelo en memoria
            log.exception("No se pudo revisar el champion")


holder = ModelHolder()
router = APIRouter(prefix="/api")


class PredictRequest(BaseModel):
    distrito: str = Field(examples=["Miraflores"])
    area_m2: Annotated[float, Field(ge=15, le=600, examples=[70])]
    dormitorios: Annotated[int, Field(ge=0, le=8, examples=[2])]
    banos: Annotated[int, Field(ge=0, le=8, examples=[2])]
    cocheras: Annotated[int, Field(ge=0, le=6, examples=[1])] = 0
    piso: Annotated[int | None, Field(ge=0, le=80, examples=[5])] = None
    precio_publicado: Annotated[float | None, Field(gt=0, description="S/ al mes")] = None


class PredictResponse(BaseModel):
    moneda: str = "PEN"
    estimado: float
    intervalo_80: tuple[float, float]
    veredicto: str | None = None
    diferencia_pct: float | None = None
    version_modelo: str | None


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version_api": __version__}


@router.get("/ready")
def ready() -> dict:
    model = holder.get()
    if model is None:
        raise HTTPException(503, "Todavía no hay un modelo champion")
    return {"status": "ready", "version_modelo": model.meta.get("version")}


@router.get("/model")
def model_info() -> dict:
    model = _require_model()
    keep = ("version", "razon", "trained_until", "promovido_en", "holdout_metrics", "n_train",
            "features", "params", "num_boost_round")
    return {**{k: model.meta.get(k) for k in keep}, "distritos": model.districts}


@router.get("/districts")
def districts() -> list[str]:
    return _require_model().districts


@router.post("/predict")
def predict(request: PredictRequest) -> PredictResponse:
    model = _require_model()
    if request.distrito not in model.districts:
        raise HTTPException(422, f"Distrito sin datos suficientes. Opciones: {model.districts}")
    row = pd.DataFrame([request.model_dump(exclude={"precio_publicado"})])
    p10, p50, p90 = (float(v) for v in model.predict(row).iloc[0])
    response = PredictResponse(estimado=round(p50, -1), intervalo_80=(round(p10, -1),
                               round(p90, -1)), version_modelo=model.meta.get("version"))
    if request.precio_publicado:
        price = request.precio_publicado
        response.diferencia_pct = round((price - p50) / p50, 4)
        response.veredicto = "caro" if price > p90 else "barato" if price < p10 else "en rango"
    return response


@router.get("/status")
def status() -> dict:
    """Resumen de la última corrida semanal: lo usa el monitor de GitHub Actions."""
    last = holder.storage.read_json("monitoring/last_run.json", default={}) or {}
    age = None
    if last.get("fin"):
        age = (datetime.now(UTC) - datetime.fromisoformat(last["fin"])).total_seconds() / 86400
    return {**last, "dias_desde_ultima_corrida": None if age is None else round(age, 2)}


def _require_model() -> RentModel:
    model = holder.get()
    if model is None:
        raise HTTPException(503, "Todavía no hay un modelo champion")
    return model


app = FastAPI(title="AlquiLima API", version=__version__, docs_url="/api/docs",
              openapi_url="/api/openapi.json")
app.include_router(router)
