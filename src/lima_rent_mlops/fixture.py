"""Datos sintéticos con la misma forma que el scraper. Para CI, tests y demos sin internet.

No son datos reales: los precios salen de una fórmula con ruido. `shift` encarece y agranda
los avisos para simular drift.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

# Precio de referencia por m² (S/ al mes) y coordenadas aproximadas, solo para la simulación.
_DISTRICTS = {
    "Miraflores": (60, -12.121, -77.030),
    "San Isidro": (62, -12.097, -77.036),
    "Barranco": (55, -12.149, -77.021),
    "Santiago De Surco": (45, -12.135, -76.991),
    "San Borja": (45, -12.100, -76.999),
    "Jesus Maria": (40, -12.077, -77.047),
    "Lince": (38, -12.085, -77.035),
    "Magdalena Del Mar": (40, -12.093, -77.071),
    "San Miguel": (36, -12.077, -77.091),
    "Pueblo Libre": (37, -12.074, -77.063),
    "Surquillo": (38, -12.113, -77.010),
    "La Molina": (40, -12.087, -76.940),
    "Chorrillos": (30, -12.170, -77.015),
    "Los Olivos": (22, -11.958, -77.070),
    "Ate Vitarte": (22, -12.026, -76.920),
}


def make_raw(n: int = 600, seed: int = 0, scraped_at: datetime | None = None,
             shift: float = 0.0, id_offset: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    scraped_at = scraped_at or datetime.now(UTC)
    names = list(_DISTRICTS)
    weights = np.linspace(2.0, 0.5, len(names))
    district = rng.choice(names, size=n, p=weights / weights.sum())
    base, lat, lon = (np.array([_DISTRICTS[d][i] for d in district]) for i in range(3))
    area = np.clip(rng.lognormal(np.log(75 * (1 + shift)), 0.4, n), 20, 400).round()
    bedrooms = np.clip((area / 35).round() + rng.integers(-1, 2, n), 1, 5)
    bathrooms = np.clip(bedrooms - rng.integers(0, 2, n), 1, 4)
    garage = (rng.random(n) < 0.55).astype(float)
    floor = np.where(rng.random(n) < 0.6, rng.integers(1, 20, n), np.nan)
    price_pen = (base * (1 + shift) * area * (1 + 0.08 * garage) * (1 + 0.01 * np.nan_to_num(floor))
                 * rng.lognormal(0, 0.15, n))
    usd = rng.random(n) < 0.4
    price = np.where(usd, price_pen / 3.4, price_pen).round(-1)
    published = [scraped_at - timedelta(days=int(d)) for d in rng.integers(0, 365, n)]
    df = pd.DataFrame({
        "id": [f"F{id_offset + i}" for i in range(n)],
        "fecha_publicacion": [d.date().isoformat() for d in published],
        "fecha_actualizacion": scraped_at.date().isoformat(),
        "operacion": "Alquiler",
        "tipo": "Departamento",
        "distrito_portal": district,
        "latitud": lat + rng.normal(0, 0.006, n),
        "longitud": lon + rng.normal(0, 0.006, n),
        "precio": price,
        "moneda": np.where(usd, "USD", "PEN"),
        "precio_oculto": rng.random(n) < 0.02,
        "mantenimiento": np.where(rng.random(n) < 0.5, (area * 3).round(-1), np.nan),
        "moneda_mantenimiento": "PEN",
        "area_m2": area,
        "dormitorios": bedrooms,
        "banos": bathrooms,
        "cocheras": garage,
        "piso": floor,
        "amoblado": rng.random(n) < 0.2,
        "estado": "Buen estado",
        "fecha_scraping": scraped_at.isoformat(timespec="seconds"),
    })
    # Algunos avisos que la limpieza debe descartar.
    df.loc[df.sample(frac=0.02, random_state=seed).index, "distrito_portal"] = "Arequipa"
    df.loc[df.sample(frac=0.01, random_state=seed + 1).index, "area_m2"] = 3000
    return df


def make_fx(start: date, end: date, rate: float = 3.4) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"fecha": days, "tc_venta": rate})
