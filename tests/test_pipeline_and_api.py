"""Prueba de punta a punta: dos semanas simuladas y la API sirviendo el champion resultante."""

import importlib
from datetime import timedelta

from fastapi.testclient import TestClient

from lima_rent_mlops.config import Settings
from lima_rent_mlops.fixture import make_fx, make_raw
from lima_rent_mlops.pipeline import run_weekly
from lima_rent_mlops.storage import Storage


def test_two_weeks_then_api(env, scraped_at):
    settings = Settings()
    fx = make_fx(scraped_at.date() - timedelta(days=30), scraped_at.date() + timedelta(days=10))

    first = run_weekly(settings, raw=make_raw(600, seed=0, scraped_at=scraped_at), fx=fx)
    assert first["estado"] == "ok" and first["decision"] == "promovido"
    assert first["reentrenamiento"] == "modelo inicial"

    later = scraped_at + timedelta(days=7)
    drifted = make_raw(250, seed=1, scraped_at=later, shift=0.5, id_offset=100_000)
    second = run_weekly(settings, raw=drifted, fx=fx)
    assert second["avisos_nuevos"] > 200
    assert "drift" in second["reentrenamiento"]

    storage = Storage(settings)
    assert len(storage.read_json("models/history.json")) == 2
    assert not storage.read_parquet("monitoring/performance.parquet").empty
    assert storage.read_parquet("monitoring/drift.parquet")["drift"].any()

    from lima_rent_mlops.serving import api

    importlib.reload(api)  # vuelve a leer la configuración del entorno de la prueba
    client = TestClient(api.app)
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/ready").status_code == 200
    body = {"distrito": "Miraflores", "area_m2": 70, "dormitorios": 2, "banos": 2,
            "cocheras": 1, "piso": 5, "precio_publicado": 50_000}
    assert client.post("/api/predict", json={**body, "area_m2": 5}).status_code == 422
    data = client.post("/api/predict", json=body).json()
    low, high = data["intervalo_80"]
    assert low <= data["estimado"] <= high and data["veredicto"] == "caro"
    assert client.post("/api/predict", json={**body, "distrito": "Arequipa"}).status_code == 422
    assert client.get("/api/status").json()["estado"] == "ok"
