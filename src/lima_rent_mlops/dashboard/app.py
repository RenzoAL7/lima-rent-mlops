"""AlquiLima: dashboard del modelo de alquileres de Lima (Streamlit)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent

st.set_page_config(page_title="AlquiLima", page_icon=":material/apartment:", layout="wide")

pages = [
    st.Page(HERE / "pages" / "predictor.py", title="Predictor", icon=":material/calculate:",
            default=True),
    st.Page(HERE / "pages" / "salud.py", title="Salud del modelo",
            icon=":material/monitor_heart:"),
    st.Page(HERE / "pages" / "drift.py", title="Drift", icon=":material/insights:"),
    st.Page(HERE / "pages" / "historial.py", title="Historial de modelos",
            icon=":material/history:"),
    st.Page(HERE / "pages" / "calidad.py", title="Calidad de datos",
            icon=":material/fact_check:"),
]

with st.sidebar:
    st.markdown("## AlquiLima")
    st.caption("Alquiler de departamentos en Lima Metropolitana, con el modelo vigilado "
               "semana a semana.")

st.navigation(pages).run()

with st.sidebar:
    st.divider()
    st.caption("Proyecto educativo de MLOps · datos de avisos públicos, BCRP e INEI. "
               "No es una tasación.")
