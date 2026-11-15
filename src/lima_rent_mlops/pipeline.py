"""Corrida semanal completa. La ejecuta un CronJob de Kubernetes (o `lima-rent weekly`).

1. Scraping de Infocasas  ->  bronze/
2. Limpieza y validación   ->  silver/listings.parquet (historial con primera_vez_visto)
3. Ground truth: el champion predice los avisos nuevos y se mide su error real
4. Drift de features, target y predicciones contra la referencia del champion
5. ¿Reentrenar? Sí, si no hay champion, si hay drift o si el MAPE supera el umbral
6. Challenger -> comparación con el champion -> promoción solo si mejora
7. monitoring/last_run.json: resumen que leen la API, el dashboard y el monitor de GitHub
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from .config import Settings
from .monitoring.drift import feature_drift, target_by_week, week_label
from .monitoring.performance import evaluate_new_listings
from .processing.clean import clean_snapshot, quality_summary, update_history
from .storage import Storage
from .training.champion import load_champion, load_reference
from .training.evaluate import TOTAL
from .training.promote import promote
from .training.train import fit_challenger, log_to_mlflow

log = logging.getLogger(__name__)
SILVER = "silver/listings.parquet"
FX = "silver/fx_usd_pen.parquet"


def refresh_fx(storage: Storage, until: date) -> pd.DataFrame:
    """Tipo de cambio diario desde 2020; solo pide al BCRP lo que falta."""
    from .sources import bcrp

    fx = storage.read_parquet_or_empty(FX)
    start = date(2020, 1, 1) if fx.empty else (fx["fecha"].max() - timedelta(days=10)).date()
    try:
        fresh = bcrp.fx_usd_pen(start, until)
        fx = pd.concat([fx, fresh]).drop_duplicates("fecha", keep="last").sort_values("fecha")
        storage.write_parquet(fx.reset_index(drop=True), FX)
    except Exception as error:  # el BCRP a veces no responde: se usa lo último guardado
        if fx.empty:
            raise
        log.warning("BCRP no disponible (%s); se usa el tipo de cambio guardado", error)
    return fx


def refresh_context(storage: Storage) -> None:
    """Series de contexto: alquiler/m² del BCRP (trimestral) y ENAHO (anual)."""
    from .sources import bcrp, enaho

    try:
        storage.write_parquet(bcrp.rent_m2_by_district(), "silver/bcrp_alquiler_m2.parquet")
    except Exception as error:
        log.warning("No se pudo actualizar la serie del BCRP: %s", error)
    current = storage.read_parquet_or_empty("silver/enaho_alquileres.parquet")
    have = set(current["anio"].unique()) if len(current) else set()
    missing = [y for y in enaho.YEAR_CODES if y not in have]
    if missing:
        try:
            fresh = enaho.rentals(missing)
            merged = pd.concat([current, fresh], ignore_index=True)
            storage.write_parquet(merged, "silver/enaho_alquileres.parquet")
        except Exception as error:
            log.warning("No se pudo actualizar la ENAHO: %s", error)


def run_weekly(settings: Settings, raw: pd.DataFrame | None = None,
               fx: pd.DataFrame | None = None, max_pages: int | None = None,
               force_retrain: str | None = None) -> dict:
    storage = Storage(settings)
    now = datetime.now(UTC)
    summary: dict = {"inicio": now.isoformat(timespec="seconds"), "estado": "en curso"}
    try:
        # 1. Datos crudos
        if raw is None:
            from .sources import infocasas

            raw = infocasas.scrape(settings, max_pages)
        scraped_day = pd.Timestamp(raw["fecha_scraping"].iloc[0]).date()
        week = week_label(scraped_day)
        storage.write_parquet(raw, f"bronze/infocasas/fecha={scraped_day}/listings.parquet")

        # 2. Limpieza, validación e historial
        fx = fx if fx is not None else refresh_fx(storage, scraped_day)
        snapshot, report = clean_snapshot(raw, fx)
        history, new = update_history(storage.read_parquet_or_empty(SILVER), snapshot)
        storage.write_parquet(history, SILVER)
        quality = quality_summary(raw, report, len(new), week)
        storage.append_parquet(quality, "monitoring/quality.parquet", dedupe_on=["semana"])
        storage.write_parquet(target_by_week(history), "monitoring/target_drift.parquet")
        summary.update({"semana": week, "avisos_validos": len(snapshot),
                        "avisos_nuevos": len(new), "historial": len(history)})

        # 3 y 4. Ground truth y drift (solo si ya hay un champion)
        reasons: list[str] = []
        champion = load_champion(storage)
        if champion is None:
            reasons.append("modelo inicial")
        elif len(new):
            predictions, perf = evaluate_new_listings(champion, new, week)
            storage.write_parquet(predictions, f"monitoring/predictions/semana={week}.parquet")
            storage.append_parquet(perf, "monitoring/performance.parquet",
                                   dedupe_on=["semana", "distrito"])
            total = perf[perf["distrito"] == TOTAL].iloc[0]
            summary.update({"mae_semana": float(total["mae"]),
                            "mape_semana": float(total["mape"])})
            reference = load_reference(storage)
            current = new.join(predictions[["p50"]])
            drift = feature_drift(reference, current, settings.psi_threshold, week)
            storage.append_parquet(drift, "monitoring/drift.parquet",
                                   dedupe_on=["semana", "variable"])
            enough = len(new) >= settings.min_new_listings
            drifted = drift[drift["drift"] & drift["tipo"].eq("feature")]["variable"].tolist()
            if enough and drifted:
                reasons.append(f"drift en {', '.join(drifted)}")
            if enough and total["mape"] > settings.mape_threshold:
                reasons.append(f"MAPE semanal {total['mape']:.1%} > {settings.mape_threshold:.0%}")
        if force_retrain:
            reasons.append(force_retrain)

        # 5 y 6. Reentrenamiento y promoción
        if reasons:
            reason = "; ".join(reasons)
            result = log_to_mlflow(fit_challenger(history, settings), settings, reason)
            event = promote(result, storage, settings, reason)
            summary.update({"reentrenamiento": reason, "decision": event["decision"],
                            "detalle": event["detalle"], "version": result.version})
        else:
            summary["reentrenamiento"] = None
        summary["estado"] = "ok"
        return summary
    except Exception as error:
        summary.update({"estado": "error", "error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        summary["fin"] = datetime.now(UTC).isoformat(timespec="seconds")
        storage.write_json(summary, "monitoring/last_run.json")
        log.info("Resumen: %s", summary)
