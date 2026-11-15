"""Lectura de datos para el dashboard: archivos de monitoreo del lago y la API de predicción."""

from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st

from lima_rent_mlops.config import get_settings
from lima_rent_mlops.storage import Storage

TTL = 300  # segundos: el pipeline corre una vez por semana, no hace falta leer más seguido


@st.cache_resource
def storage() -> Storage:
    return Storage(get_settings())


@st.cache_data(ttl=TTL, show_spinner=False)
def table(key: str) -> pd.DataFrame:
    try:
        return storage().read_parquet_or_empty(key)
    except Exception as error:  # sin credenciales o sin red: la página lo indica
        st.warning(f"No se pudo leer {key}: {error}")
        return pd.DataFrame()


@st.cache_data(ttl=TTL, show_spinner=False)
def document(key: str, default=None):
    try:
        return storage().read_json(key, default=default)
    except Exception as error:
        st.warning(f"No se pudo leer {key}: {error}")
        return default


def api(method: str, path: str, **kwargs):
    url = get_settings().api_url.rstrip("/") + path
    response = httpx.request(method, url, timeout=15, **kwargs)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=TTL, show_spinner=False)
def model_info() -> dict | None:
    try:
        return api("GET", "/api/model")
    except Exception:
        return None


def empty_state(message: str) -> None:
    st.info(message, icon=":material/hourglass_empty:")


def latest_week(df: pd.DataFrame) -> str | None:
    return None if df.empty else sorted(df["semana"].unique())[-1]
