"""Página 4: historial de modelos v1 → v2 → v3 y por qué se reentrenó cada uno."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lima_rent_mlops.dashboard.data import document, empty_state, model_info

st.title("Historial de modelos")
st.caption("Cada reentrenamiento produce un *challenger*. Solo reemplaza al *champion* si "
           "mejora su error sobre los mismos avisos de prueba.")

history = document("models/history.json", default=[]) or []
if not history:
    empty_state("Todavía no se entrenó ningún modelo.")
    st.stop()

info = model_info()
if info:
    m = info.get("holdout_metrics") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Champion actual", f"v{info.get('version')}")
    c2.metric("MAE de prueba", f"S/ {m.get('mae', 0):,.0f}")
    c3.metric("MAPE de prueba", f"{m.get('mape', 0):.1%}")
    c4.metric("Entrenado con", f"{info.get('n_train', 0):,} avisos")

for event in reversed(history):
    promoted = event["decision"] == "promovido"
    icon = ":material/workspace_premium:" if promoted else ":material/block:"
    with st.container(border=True):
        a, b = st.columns([1, 4])
        a.markdown(f"### v{event['version']}")
        a.caption(pd.Timestamp(event["fecha"]).strftime("%d/%m/%Y"))
        b.markdown(f"{icon} **{event['decision'].capitalize()}** · {event['detalle']}")
        b.markdown(f"**Por qué se reentrenó:** {event['razon_reentrenamiento']}")
        b.caption(f"MAE {event.get('mae_holdout', 0):,.0f} · MAPE "
                  f"{event.get('mape_holdout', 0):.1%} · cobertura "
                  f"{event.get('cobertura_holdout', 0):.0%} · {event.get('n_train', 0):,} "
                  "avisos de entrenamiento")
