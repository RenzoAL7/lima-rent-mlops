"""Página 5: calidad de datos del scraping semanal."""

from __future__ import annotations

import altair as alt
import streamlit as st

from lima_rent_mlops.dashboard.data import document, empty_state, table

st.title("Calidad de datos")
st.caption("Qué llegó del portal cada semana y cuánto se descartó en la limpieza.")

last = document("monitoring/last_run.json", default={}) or {}
if last:
    state = last.get("estado")
    (st.success if state == "ok" else st.error)(
        f"Última corrida: **{state}** · {last.get('fin', '?')} · semana {last.get('semana', '?')}"
        + (f" · {last['error']}" if last.get("error") else ""))

quality = table("monitoring/quality.parquet")
if quality.empty:
    empty_state("Todavía no hay corridas del pipeline.")
    st.stop()

quality = quality.sort_values("semana")
last_row = quality.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Avisos en el portal", f"{int(last_row['avisos_crudos']):,}")
c2.metric("Válidos", f"{int(last_row['avisos_validos']):,}")
c3.metric("Nuevos", f"{int(last_row['avisos_nuevos']):,}")
c4.metric("Duplicados", f"{int(last_row.get('duplicados', 0)):,}")

st.subheader("Avisos por semana")
counts = quality.melt(id_vars="semana", value_vars=["avisos_crudos", "avisos_validos",
                                                    "avisos_nuevos"],
                      var_name="serie", value_name="avisos")
st.altair_chart(alt.Chart(counts).mark_line(point=True).encode(
    x=alt.X("semana:N", title=None), y="avisos:Q", color=alt.Color("serie:N", title=None))
    .properties(height=260), use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("Descartes de la última semana")
    rules = [c for c in quality.columns if c.startswith(("fuera_", "sin_", "no_es", "duplicados"))]
    dropped = last_row[rules].rename("avisos").reset_index().rename(columns={"index": "regla"})
    st.altair_chart(alt.Chart(dropped).mark_bar().encode(
        y=alt.Y("regla:N", sort="-x", title=None), x="avisos:Q").properties(height=240),
        use_container_width=True)
with right:
    st.subheader("Nulos por campo")
    nulls = [c for c in quality.columns if c.startswith("nulos_")]
    view = quality.melt(id_vars="semana", value_vars=nulls, var_name="campo", value_name="pct")
    view["campo"] = view["campo"].str.removeprefix("nulos_")
    st.altair_chart(alt.Chart(view).mark_line(point=True).encode(
        x=alt.X("semana:N", title=None), y=alt.Y("pct:Q", axis=alt.Axis(format="%"), title=None),
        color=alt.Color("campo:N", title=None)).properties(height=240), use_container_width=True)
