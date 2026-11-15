"""ENAHO del INEI, módulo 100 (características de la vivienda).

La pregunta 105 registra el alquiler mensual que el hogar realmente paga (P105B). A diferencia
de los avisos (precio pedido), es un precio pagado. No trae m², pero sí distrito y número de
habitaciones: sirve como serie histórica anual de contexto.
"""

from __future__ import annotations

import io
import logging
import zipfile

import httpx
import pandas as pd

from ..districts import UBIGEO

log = logging.getLogger(__name__)
URL = "https://proyectos.inei.gob.pe/iinei/srienaho/descarga/CSV/{code}-Modulo01.zip"
# Código de descarga del INEI por año (ENAHO metodología actualizada, anual).
YEAR_CODES = {
    2014: 440, 2015: 498, 2016: 546, 2017: 603, 2018: 634, 2019: 687,
    2020: 737, 2021: 759, 2022: 784, 2023: 906, 2024: 966,
}  # fmt: skip
HOUSING_TYPE = {"1": "casa", "2": "departamento", "3": "quinta", "4": "vecindad"}


def download_module100(year: int, client: httpx.Client | None = None) -> pd.DataFrame:
    """Descarga el ZIP del año y devuelve el CSV del módulo 100 sin transformar (texto)."""
    url = URL.format(code=YEAR_CODES[year])
    own = client is None
    client = client or httpx.Client(timeout=300, follow_redirects=True)
    try:
        response = client.get(url)
        response.raise_for_status()
    finally:
        if own:
            client.close()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith("-100.csv")]
        member = next(n for n in names if "enaho01" in n.lower())
        with archive.open(member) as handle:
            return pd.read_csv(handle, encoding="latin-1", dtype=str, low_memory=False)


def extract_rentals(raw: pd.DataFrame, year: int) -> pd.DataFrame:
    """Hogares de Lima Metropolitana y Callao que alquilan, con el monto mensual pagado."""
    df = raw.rename(columns=str.upper)
    df["UBIGEO"] = df["UBIGEO"].str.strip().str.zfill(6)
    rented = df[df["UBIGEO"].isin(UBIGEO) & (df["P105A"].str.strip() == "1")].copy()
    rented["alquiler_mensual_pen"] = pd.to_numeric(rented["P105B"], errors="coerce")
    # 99999 y similares son códigos de "no sabe / no responde".
    rented = rented[rented["alquiler_mensual_pen"].between(1, 50_000)]
    out = pd.DataFrame(
        {
            "anio": year,
            "mes": pd.to_numeric(rented["MES"], errors="coerce").astype("Int64"),
            "ubigeo": rented["UBIGEO"],
            "distrito": rented["UBIGEO"].map(UBIGEO),
            "tipo_vivienda": rented["P101"].str.strip().map(HOUSING_TYPE).fillna("otro"),
            "habitaciones": pd.to_numeric(rented["P104"], errors="coerce").astype("Int64"),
            "alquiler_mensual_pen": rented["alquiler_mensual_pen"],
            "factor_expansion": pd.to_numeric(rented.get("FACTOR07"), errors="coerce"),
        }
    )
    return out.reset_index(drop=True)


def rentals(years: list[int]) -> pd.DataFrame:
    frames = []
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        for year in years:
            frame = extract_rentals(download_module100(year, client), year)
            log.info("ENAHO %d: %d hogares que alquilan en Lima/Callao", year, len(frame))
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
