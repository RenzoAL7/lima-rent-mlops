import numpy as np
import pandas as pd

from lima_rent_mlops.config import Settings
from lima_rent_mlops.fixture import make_raw
from lima_rent_mlops.monitoring.drift import feature_drift, psi_categorical, psi_numeric
from lima_rent_mlops.processing.clean import clean_snapshot, update_history
from lima_rent_mlops.training.model import RentModel
from lima_rent_mlops.training.train import fit_challenger, temporal_split


def _silver(raw, fx):
    clean, _ = clean_snapshot(raw, fx)
    history, _ = update_history(pd.DataFrame(), clean)
    return history


def test_model_quantiles_are_ordered_and_roundtrip(raw, fx):
    silver = _silver(raw, fx)
    model = RentModel.fit(silver, {"learning_rate": 0.1, "num_leaves": 15}, 80)
    pred = model.predict(silver.head(50))
    assert (pred["p10"] <= pred["p50"]).all() and (pred["p50"] <= pred["p90"]).all()
    restored = RentModel.from_files(model.to_files())
    pd.testing.assert_frame_equal(pred, restored.predict(silver.head(50)))
    unknown = silver.head(1).assign(distrito="Distrito Nuevo")
    assert np.isfinite(model.predict(unknown).to_numpy()).all()


def test_temporal_split_keeps_latest_for_holdout(raw, fx):
    silver = _silver(raw, fx)
    train, holdout = temporal_split(silver, 0.2)
    assert train["fecha_publicacion"].max() <= holdout["fecha_publicacion"].min()


def test_challenger_beats_naive_baseline(raw, fx, monkeypatch):
    monkeypatch.setenv("OPTUNA_TRIALS", "3")
    result = fit_challenger(_silver(raw, fx), Settings())
    naive = (result.holdout["precio_pen"] - result.train["precio_pen"].median()).abs().mean()
    assert result.holdout_metrics["mae"] < naive


def test_psi_detects_shift():
    rng = np.random.default_rng(0)
    a = pd.Series(rng.normal(70, 15, 2000))
    assert psi_numeric(a, pd.Series(rng.normal(70, 15, 2000))) < 0.05
    assert psi_numeric(a, pd.Series(rng.normal(95, 15, 2000))) > 0.2
    cats = pd.Series(["Miraflores"] * 50 + ["Lince"] * 50)
    assert psi_categorical(cats, pd.Series(["Miraflores"] * 95 + ["Lince"] * 5)) > 0.2


def test_feature_drift_flags_shifted_area(raw, fx, scraped_at):
    reference = _silver(raw, fx)
    shifted = _silver(make_raw(300, seed=3, scraped_at=scraped_at, shift=0.5), fx)
    report = feature_drift(reference, shifted, threshold=0.2, week="2026-W45")
    flags = report.set_index("variable")["drift"]
    assert flags["area_m2"] and not flags["cocheras"]
