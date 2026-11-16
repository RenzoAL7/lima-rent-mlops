"""Página 1: estimar el alquiler de un departamento y decir si un aviso está caro o barato."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from lima_rent_mlops.dashboard.data import api, api_error_message, empty_state, model_info
from lima_rent_mlops.districts import DISTRICTS

st.title("Predictor")
st.caption("Ingresa las características del departamento. El modelo devuelve el alquiler "
           "mensual estimado y un rango donde cae el 80% de los avisos parecidos.")

info = model_info()
districts = info["distritos"] if info else DISTRICTS
if info is None:
    empty_state("Todavía no hay un modelo entrenado. El formulario se habilita cuando el "
                "pipeline publique el primero.")

with st.form("predictor"):
    c1, c2, c3 = st.columns(3)
    distrito = c1.selectbox("Distrito", districts,
                            index=districts.index("Miraflores") if "Miraflores" in districts else 0)
    area = c2.number_input("Área (m²)", 15, 600, 70, step=5)
    piso = c3.number_input("Piso", 0, 80, 5)
    c4, c5, c6 = st.columns(3)
    dormitorios = c4.number_input("Dormitorios", 0, 8, 2)
    banos = c5.number_input("Baños", 0, 8, 2)
    cocheras = c6.number_input("Cocheras", 0, 6, 1)
    precio = st.number_input("Precio del aviso (opcional, S/ al mes)", 0, 60_000, 0, step=100,
                             help="Si lo llenas, te digo si el aviso está caro, barato o en rango.")
    submitted = st.form_submit_button("Estimar", type="primary", use_container_width=True,
                                      disabled=info is None)

if submitted:
    body = {"distrito": distrito, "area_m2": area, "dormitorios": dormitorios, "banos": banos,
            "cocheras": cocheras, "piso": piso, "precio_publicado": precio or None}
    try:
        result = api("POST", "/api/predict", json=body)
    except Exception as error:
        st.error(f"No se pudo obtener la predicción. {api_error_message(error)}")
        st.stop()
    low, high = result["intervalo_80"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Alquiler estimado", f"S/ {result['estimado']:,.0f}")
    m2.metric("Rango (80%)", f"S/ {low:,.0f} – {high:,.0f}")
    m3.metric("Por m²", f"S/ {result['estimado'] / area:,.0f}")
    if result.get("veredicto"):
        tone = {"caro": "error", "barato": "success", "en rango": "info"}[result["veredicto"]]
        getattr(st, tone)(f"El aviso está **{result['veredicto']}**: "
                          f"{result['diferencia_pct']:+.0%} respecto a la estimación.")
    points = pd.DataFrame({"valor": [low, result["estimado"], high],
                           "etiqueta": ["p10", "estimado", "p90"]})
    scale = alt.Scale(zero=False, padding=30)
    band = alt.Chart(pd.DataFrame({"low": [low], "high": [high]})).mark_bar(
        height=18, opacity=0.25, cornerRadius=9).encode(x=alt.X("low:Q", scale=scale), x2="high:Q")
    dots = alt.Chart(points).mark_point(filled=True, size=140).encode(
        x=alt.X("valor:Q", title="S/ al mes", scale=scale), tooltip=["etiqueta", "valor"])
    layers = [band, dots]
    if precio:
        layers.append(alt.Chart(pd.DataFrame({"x": [precio]})).mark_rule(
            strokeDash=[4, 3], strokeWidth=2).encode(x="x:Q"))
    st.altair_chart(alt.layer(*layers).properties(height=90), use_container_width=True)
    st.caption(f"Modelo versión {result['version_modelo']}. Basado en avisos publicados (precio "
               "pedido), no en contratos cerrados.")
