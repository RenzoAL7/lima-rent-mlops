"""Contratos de datos con Pandera.

- RAW: lo que devuelve el scraper. Laxo: solo exige lo mínimo para poder limpiar.
- SILVER: la tabla con la que se entrena. Estricto: si algo cambia en el portal o en la
  limpieza, el pipeline se detiene antes de entrenar con datos raros.
"""

from __future__ import annotations

import pandera.pandas as pa

from ..districts import DISTRICTS

RAW = pa.DataFrameSchema(
    {
        "id": pa.Column(str, unique=True),
        "precio": pa.Column(float, pa.Check.ge(0), nullable=True, coerce=True),
        "moneda": pa.Column(str, pa.Check.isin(["PEN", "USD"]), nullable=True),
        "area_m2": pa.Column(float, pa.Check.ge(0), nullable=True, coerce=True),
        "distrito_portal": pa.Column(str, nullable=True),
        "fecha_scraping": pa.Column(str),
    },
    strict=False,
)

SILVER = pa.DataFrameSchema(
    {
        "id": pa.Column(str, unique=True),
        "distrito": pa.Column(str, pa.Check.isin(DISTRICTS)),
        "area_m2": pa.Column(float, pa.Check.in_range(15, 600)),
        "dormitorios": pa.Column(float, pa.Check.in_range(0, 8)),
        "banos": pa.Column(float, pa.Check.in_range(0, 8)),
        "cocheras": pa.Column(float, pa.Check.in_range(0, 6)),
        "piso": pa.Column(float, pa.Check.in_range(0, 80), nullable=True),
        "precio_pen": pa.Column(float, pa.Check.in_range(300, 60_000)),
        "precio_m2_pen": pa.Column(float, pa.Check.in_range(5, 250)),
        "primera_vez_visto": pa.Column("datetime64[ns]"),
    },
    strict=False,
    coerce=True,
)
