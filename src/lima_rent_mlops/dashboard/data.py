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
def _model_info() -> dict:
    return api("GET", "/api/model")


def model_info() -> dict | None:
    """Datos del modelo vigente, o None si la API aún no tiene uno. Solo se cachea el éxito:
    así el formulario se habilita apenas aparece el primer modelo, sin esperar a que venza
    la caché."""
    try:
        return _model_info()
    except Exception:
        return None


def api_error_message(error: Exception) -> str:
    """Explica un fallo de la API sin mostrar direcciones internas del clúster."""
    if isinstance(error, httpx.HTTPStatusError):
        try:
            detail = error.response.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, str) and detail:
            return detail
        return f"La API respondió con un error ({error.response.status_code})."
    return "No se pudo conectar con la API. Intenta de nuevo en unos minutos."


def empty_state(message: str) -> None:
    st.info(message, icon=":material/hourglass_empty:")


def latest_week(df: pd.DataFrame) -> str | None:
    return None if df.empty else sorted(df["semana"].unique())[-1]
