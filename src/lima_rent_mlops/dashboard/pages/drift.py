"""Página 3: drift de features, del target y de las predicciones; contexto BCRP e INEI."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from lima_rent_mlops.config import get_settings
from lima_rent_mlops.dashboard.data import empty_state, latest_week, table

st.title("Drift")
st.caption("¿Los avisos nuevos se parecen a los que vio el modelo al entrenar? PSI < 0.1 "
           "estable · 0.1–0.2 moderado · > 0.2 importante.")

threshold = get_settings().psi_threshold
drift = table("monitoring/drift.parquet")
if drift.empty:
    empty_state("El drift se mide desde la segunda semana, cuando hay avisos nuevos que comparar.")
else:
    week = latest_week(drift)
    current = drift[drift["semana"] == week].sort_values("psi", ascending=False)
    st.subheader(f"Semana {week}")
    flagged = current[current["drift"]]
    if len(flagged):
        st.warning("Drift en: " + ", ".join(flagged["variable"]), icon=":material/warning:")
    else:
        st.success("Sin drift importante esta semana.", icon=":material/check_circle:")
    bars = alt.Chart(current).mark_bar().encode(
        y=alt.Y("variable:N", sort="-x", title=None), x=alt.X("psi:Q", title="PSI"),
        color=alt.Color("tipo:N", title="Tipo"),
        tooltip=["variable", "tipo", alt.Tooltip("psi:Q", format=".3f"),
                 alt.Tooltip("ks_pvalor:Q", format=".3f")])
    rule = alt.Chart().mark_rule(strokeDash=[5, 4], color="#c2410c").encode(x=alt.datum(threshold))
    st.altair_chart((bars + rule).properties(height=260), use_container_width=True)

    st.subheader("PSI en el tiempo")
    lines = alt.Chart(drift).mark_line(point=True).encode(
        x=alt.X("semana:N", title=None), y=alt.Y("psi:Q", title="PSI"),
        color=alt.Color("variable:N", title=None), tooltip=["semana", "variable", "psi"])
    st.altair_chart(lines.properties(height=240), use_container_width=True)

st.subheader("Drift del target: precio por m²")
target = table("monitoring/target_drift.parquet")
if target.empty:
    empty_state("Sin datos todavía.")
else:
    top = (target[target["distrito"] != "Total"].groupby("distrito")["n"].sum()
           .nlargest(6).index.tolist())
    choice = st.multiselect("Distritos", sorted(target["distrito"].unique()),
                            default=["Total", *top[:4]])
    view = target[target["distrito"].isin(choice)]
    chart = alt.Chart(view).mark_line(point=True).encode(
        x=alt.X("semana:N", title=None),
        y=alt.Y("mediana_precio_m2:Q", title="S/ por m² al mes (mediana de avisos nuevos)"),
        color=alt.Color("distrito:N", title=None), tooltip=["semana", "distrito", "n",
                                                            "mediana_precio_m2"])
    st.altair_chart(chart.properties(height=280), use_container_width=True)

st.subheader("Contexto de largo plazo")
left, right = st.columns(2)
bcrp = table("silver/bcrp_alquiler_m2.parquet")
with left:
    st.markdown("**BCRP**: alquiler mensual por m² (US$), trimestral")
    if bcrp.empty:
        empty_state("Corre `lima-rent context` para traer la serie.")
    else:
        chart = alt.Chart(bcrp).mark_line().encode(
            x=alt.X("fecha:T", title=None), y=alt.Y("alquiler_mensual_usd_m2:Q", title="US$/m²"),
            color=alt.Color("distrito:N", title=None),
            tooltip=["trimestre", "distrito", alt.Tooltip("alquiler_mensual_usd_m2:Q",
                                                          format=".1f")])
        st.altair_chart(chart.properties(height=280), use_container_width=True)
        st.caption("Venta por m² ÷ PER ÷ 12. Fuente: BCRP (avisos procesados por el BCRP).")
enaho = table("silver/enaho_alquileres.parquet")
with right:
    st.markdown("**INEI – ENAHO**: alquiler mensual *pagado* por los hogares (S/)")
    if enaho.empty:
        empty_state("Corre `lima-rent context` para traer la ENAHO.")
    else:
        deptos = enaho[enaho["tipo_vivienda"] == "departamento"]
        yearly = (deptos.groupby("anio")["alquiler_mensual_pen"].median().reset_index()
                  .assign(serie="Departamentos"))
        all_homes = (enaho.groupby("anio")["alquiler_mensual_pen"].median().reset_index()
                     .assign(serie="Todas las viviendas"))
        chart = alt.Chart(pd.concat([yearly, all_homes])).mark_line(point=True).encode(
            x=alt.X("anio:O", title=None), y=alt.Y("alquiler_mensual_pen:Q", title="S/ (mediana)"),
            color=alt.Color("serie:N", title=None))
        st.altair_chart(chart.properties(height=280), use_container_width=True)
        st.caption("Precio pagado, no pedido: suele ser bastante menor que el de los avisos.")
