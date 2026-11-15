"""Página 2: error real del modelo semana a semana (ground truth de los avisos nuevos)."""

from __future__ import annotations

import altair as alt
import streamlit as st

from lima_rent_mlops.config import get_settings
from lima_rent_mlops.dashboard.data import empty_state, latest_week, table

st.title("Salud del modelo")
st.caption("Cada semana el modelo vigente predice los avisos nuevos *antes* de usar su precio. "
           "Luego se compara con el precio publicado: es su error real, no uno de laboratorio.")

perf = table("monitoring/performance.parquet")
if perf.empty:
    empty_state("Aún no hay semanas evaluadas. La primera evaluación llega una semana después "
                "del primer modelo.")
    st.stop()

threshold = get_settings().mape_threshold
total = perf[perf["distrito"] == "Total"].sort_values("semana")
last = total.iloc[-1]
prev = total.iloc[-2] if len(total) > 1 else None
c1, c2, c3, c4 = st.columns(4)
c1.metric("MAE última semana", f"S/ {last['mae']:,.0f}",
          None if prev is None else f"{last['mae'] - prev['mae']:+,.0f}", delta_color="inverse")
c2.metric("MAPE", f"{last['mape']:.1%}",
          None if prev is None else f"{last['mape'] - prev['mape']:+.1%}", delta_color="inverse")
c3.metric("Cobertura del rango 80%", f"{last['cobertura']:.0%}")
c4.metric("Avisos evaluados", f"{int(last['n'])}")

base = alt.Chart(total).encode(x=alt.X("semana:N", title=None))
line = base.mark_line(point=True).encode(y=alt.Y("mape:Q", title="MAPE", axis=alt.Axis(format="%")),
                                         tooltip=["semana", "version_modelo",
                                                  alt.Tooltip("mape:Q", format=".1%"),
                                                  alt.Tooltip("mae:Q", format=",.0f"), "n"])
rule = alt.Chart().mark_rule(strokeDash=[5, 4], color="#c2410c").encode(y=alt.datum(threshold))
st.subheader("MAPE semanal")
st.altair_chart((line + rule).properties(height=260), use_container_width=True)
st.caption(f"La línea punteada es el umbral de reentrenamiento ({threshold:.0%}).")

week = latest_week(perf)
st.subheader(f"Error por distrito · {week}")
by_district = perf[(perf["semana"] == week) & (perf["distrito"] != "Total")]
listings = table("silver/listings.parquet")
left, right = st.columns([3, 2])
with left:
    if not listings.empty:
        centers = (listings.groupby("distrito")[["latitud", "longitud"]].median().reset_index())
        points = by_district.merge(centers, on="distrito")
        points["size"] = 150 + points["n"] * 12  # radio en metros
        points["color"] = points["mape"].map(
            lambda m: "#15803d" if m < 0.12 else "#ca8a04" if m < threshold else "#b91c1c")
        st.map(points, latitude="latitud", longitude="longitud", size="size", color="color",
               zoom=10)
        st.caption("Verde < 12% · ámbar hasta el umbral · rojo sobre el umbral. "
                   "Tamaño = avisos evaluados.")
with right:
    st.dataframe(by_district[["distrito", "n", "mae", "mape", "cobertura"]]
                 .sort_values("mape", ascending=False), hide_index=True,
                 column_config={"mae": st.column_config.NumberColumn("MAE", format="S/ %.0f"),
                                "mape": st.column_config.NumberColumn("MAPE", format="percent"),
                                "cobertura": st.column_config.NumberColumn(format="percent")})

st.subheader("Residuos de la última semana")
predictions = table(f"monitoring/predictions/semana={week}.parquet")
if not predictions.empty:
    hist = alt.Chart(predictions).mark_bar().encode(
        x=alt.X("error_pct:Q", bin=alt.Bin(maxbins=40), title="Error (predicción − real) / real",
                axis=alt.Axis(format="%")), y=alt.Y("count():Q", title="Avisos"))
    scatter = alt.Chart(predictions).mark_circle(opacity=0.5).encode(
        x=alt.X("precio_pen:Q", title="Precio real (S/)"),
        y=alt.Y("p50:Q", title="Predicción (S/)"), tooltip=["distrito", "precio_pen", "p50"])
    diagonal = alt.Chart(predictions).mark_line(color="#64748b", strokeDash=[4, 4]).encode(
        x="precio_pen:Q", y="precio_pen:Q")
    a, b = st.columns(2)
    a.altair_chart(hist.properties(height=260), use_container_width=True)
    b.altair_chart((scatter + diagonal).properties(height=260), use_container_width=True)
