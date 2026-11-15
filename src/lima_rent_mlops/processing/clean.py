"""De avisos crudos (bronze) a la tabla de entrenamiento (silver).

Cada regla de limpieza cuenta cuántas filas descarta: ese conteo alimenta la página
"Calidad de datos" del dashboard.
"""

from __future__ import annotations

import pandas as pd

from ..districts import normalize
from . import schemas

RANGES = {
    "area_m2": (15, 600),
    "precio_pen": (300, 60_000),
    "precio_m2_pen": (5, 250),
    "dormitorios": (0, 8),
    "banos": (0, 8),
}


def clean_snapshot(raw: pd.DataFrame, fx: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Limpia una foto del portal. Devuelve (avisos válidos, conteo de descartes por regla)."""
    schemas.RAW.validate(raw, lazy=True)
    report: dict[str, int] = {"avisos_crudos": len(raw)}
    df = raw.copy()

    def drop(mask: pd.Series, rule: str) -> None:
        nonlocal df
        report[rule] = int((~mask).sum())
        df = df[mask]

    drop(df["operacion"].eq("Alquiler") & df["tipo"].eq("Departamento"), "no_es_alquiler_depa")
    drop(~df["precio_oculto"].fillna(False).astype(bool) & df["precio"].fillna(0).gt(0),
         "sin_precio")
    df = df.assign(distrito=df["distrito_portal"].map(normalize))
    drop(df["distrito"].notna(), "fuera_de_lima")

    # Precio en soles con el tipo de cambio del día del scraping.
    df["fecha_scraping"] = (pd.to_datetime(df["fecha_scraping"], utc=True).dt.tz_localize(None)
                            .astype("datetime64[ns]"))
    df["dia"] = df["fecha_scraping"].dt.normalize()
    rates = fx[["fecha", "tc_venta"]].dropna().sort_values("fecha")
    rates["fecha"] = pd.to_datetime(rates["fecha"]).astype("datetime64[ns]")
    df = pd.merge_asof(df.sort_values("dia"), rates, left_on="dia", right_on="fecha",
                       direction="backward").drop(columns=["fecha"])
    df["tc_venta"] = df["tc_venta"].fillna(rates["tc_venta"].iloc[-1])
    usd = df["moneda"].eq("USD")
    df["precio_pen"] = df["precio"].astype(float).where(~usd, df["precio"] * df["tc_venta"])
    df["area_m2"] = pd.to_numeric(df["area_m2"], errors="coerce")
    df["precio_m2_pen"] = df["precio_pen"] / df["area_m2"]
    df["cocheras"] = df["cocheras"].fillna(0).clip(0, 6)
    # Un piso imposible es un error de tipeo: se trata como dato faltante, no se descarta el aviso.
    df["piso"] = pd.to_numeric(df["piso"], errors="coerce")
    df["piso"] = df["piso"].where(df["piso"].between(0, 80))

    for column, (low, high) in RANGES.items():
        drop(df[column].between(low, high), f"fuera_de_rango_{column}")
    before = len(df)
    df = df.drop_duplicates(subset="id", keep="first")
    report["duplicados"] = before - len(df)
    report["avisos_validos"] = len(df)

    df["fecha_publicacion"] = pd.to_datetime(df["fecha_publicacion"], errors="coerce")
    columns = [
        "id", "distrito", "area_m2", "dormitorios", "banos", "cocheras", "piso", "amoblado",
        "precio_pen", "precio_m2_pen", "moneda", "precio", "tc_venta", "latitud", "longitud",
        "fecha_publicacion", "fecha_scraping",
    ]  # fmt: skip
    return df[columns].reset_index(drop=True), report


def update_history(
    history: pd.DataFrame, snapshot: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Acumula los avisos vistos. Devuelve (historial completo, avisos nuevos de esta foto).

    El ground truth semanal son los avisos nuevos: el modelo vigente nunca los vio y su precio
    se conoce recién ahora. Se conserva la primera observación de cada aviso.
    """
    snapshot = snapshot.copy()
    seen_at = snapshot["fecha_scraping"].max()
    if history.empty:
        snapshot["primera_vez_visto"] = snapshot["fecha_scraping"]
        snapshot["ultima_vez_visto"] = snapshot["fecha_scraping"]
        snapshot = schemas.SILVER.validate(snapshot, lazy=True)
        return snapshot, snapshot
    known = set(history["id"])
    new = snapshot[~snapshot["id"].isin(known)].copy()
    new["primera_vez_visto"] = new["fecha_scraping"]
    new["ultima_vez_visto"] = new["fecha_scraping"]
    history = history.copy()
    history.loc[history["id"].isin(set(snapshot["id"])), "ultima_vez_visto"] = seen_at
    merged = pd.concat([history, new], ignore_index=True)
    merged = schemas.SILVER.validate(merged, lazy=True)
    return merged, schemas.SILVER.validate(new, lazy=True) if len(new) else new


def quality_summary(raw: pd.DataFrame, report: dict, new_count: int, week: str) -> pd.DataFrame:
    """Una fila por corrida para la página de calidad de datos."""
    nulls = raw[["precio", "area_m2", "dormitorios", "banos", "piso", "distrito_portal"]].isna()
    row = {
        "semana": week,
        **report,
        "avisos_nuevos": new_count,
        **{f"nulos_{c}": round(float(v), 4) for c, v in nulls.mean().items()},
    }
    return pd.DataFrame([row])
