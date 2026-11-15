"""API de series estadísticas del BCRP (https://estadisticas.bcrp.gob.pe).

- Tipo de cambio diario (S/ por US$, venta) para convertir avisos en dólares a soles.
- Precio de venta por m² y PER por distrito (trimestral): con ambos se obtiene el alquiler
  por m², una serie larga que sirve de contexto para el drift del target.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
import pandas as pd

from ..districts import BCRP_SERIES

log = logging.getLogger(__name__)
BASE = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
FX_SELL = "PD04640PD"  # TC Sistema bancario SBS (S/ por US$) - Venta
_MONTHS = {
    "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12,
}  # fmt: skip


def fetch_series(code: str, start: str, end: str, client: httpx.Client | None = None):
    """Devuelve (nombre, DataFrame[periodo, valor]). Los 'n.d.' quedan como NaN."""
    url = f"{BASE}/{code}/json/{start}/{end}"
    own = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
    finally:
        if own:
            client.close()
    name = data["config"]["series"][0]["name"]
    rows = [(p["name"], p["values"][0]) for p in data.get("periods", [])]
    df = pd.DataFrame(rows, columns=["periodo", "valor"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return name, df


def parse_quarter(label: str) -> pd.Period:
    """'T4.07' -> Period('2007Q4')."""
    quarter, year = label.removeprefix("T").split(".")
    return pd.Period(f"{2000 + int(year)}Q{int(quarter)}", freq="Q")


def parse_day(label: str) -> date:
    """'12.Nov.26' -> date(2026, 11, 12)."""
    day, month, year = label.split(".")
    return date(2000 + int(year), _MONTHS[month[:3].title()], int(day))


def fx_usd_pen(start: date, end: date, client: httpx.Client | None = None) -> pd.DataFrame:
    """Tipo de cambio venta por día, con los feriados rellenados con el último valor."""
    _, df = fetch_series(FX_SELL, start.isoformat(), end.isoformat(), client)
    df["fecha"] = pd.to_datetime(df["periodo"].map(parse_day))
    df = df.dropna(subset=["valor"]).rename(columns={"valor": "tc_venta"})
    days = pd.DataFrame({"fecha": pd.date_range(df["fecha"].min(), end, freq="D")})
    out = pd.merge_asof(days, df[["fecha", "tc_venta"]].sort_values("fecha"), on="fecha")
    return out


def rent_m2_by_district(start: str = "2010-1", end: str = "2030-4") -> pd.DataFrame:
    """Alquiler mensual por m² (US$) por distrito y trimestre = venta / PER / 12."""
    frames = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for district, (sale_code, per_code) in BCRP_SERIES.items():
            _, sale = fetch_series(sale_code, start, end, client)
            _, per = fetch_series(per_code, start, end, client)
            df = sale.merge(per, on="periodo", suffixes=("_venta", "_per"))
            df["distrito"] = district
            frames.append(df)
            log.info("BCRP %s: %d trimestres", district, len(df))
    df = pd.concat(frames, ignore_index=True)
    df["trimestre"] = df["periodo"].map(parse_quarter)
    df["fecha"] = df["trimestre"].dt.start_time
    df["trimestre"] = df["trimestre"].astype(str)
    df = df.rename(columns={"valor_venta": "venta_usd_m2", "valor_per": "per"})
    df["alquiler_mensual_usd_m2"] = df["venta_usd_m2"] / df["per"] / 12
    columns = ["trimestre", "fecha", "distrito", "venta_usd_m2", "per", "alquiler_mensual_usd_m2"]
    return df[columns].dropna(subset=["alquiler_mensual_usd_m2"]).reset_index(drop=True)
