"""Lima Rent MLOps: dashboard del modelo de alquileres de Lima (Streamlit)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
REPO_URL = "https://github.com/RenzoAL7/lima-rent-mlops"

# Iconos (viewBox de 24): luna, sol y la marca de GitHub. Usan currentColor para tomar el
# color de texto del tema activo.
MOON = '<path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 0 1-4.4 2.26 5.4 5.4 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z"/>'  # noqa: E501
SUN = '<path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM2 13h2a1 1 0 0 0 0-2H2a1 1 0 0 0 0 2zm18 0h2a1 1 0 0 0 0-2h-2a1 1 0 0 0 0 2zM11 2v2a1 1 0 0 0 2 0V2a1 1 0 0 0-2 0zm0 18v2a1 1 0 0 0 2 0v-2a1 1 0 0 0-2 0zM5.99 4.58a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41L5.99 4.58zm12.37 12.37a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41l-1.06-1.06zm1.06-10.96a1 1 0 0 0-1.41-1.41l-1.06 1.06a1 1 0 0 0 1.41 1.41l1.06-1.06zM7.05 18.36a1 1 0 0 0-1.41-1.41l-1.06 1.06a1 1 0 0 0 1.41 1.41l1.06-1.06z"/>'  # noqa: E501
GITHUB = '<path d="M12 .5a12 12 0 0 0-3.79 23.39c.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.33-1.76-1.33-1.76-1.09-.74.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.5 1 .11-.78.42-1.3.76-1.6-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.13-.3-.54-1.52.11-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6 0c2.29-1.55 3.3-1.23 3.3-1.23.65 1.66.24 2.88.12 3.18.77.84 1.23 1.91 1.23 3.22 0 4.61-2.8 5.63-5.48 5.92.43.37.81 1.1.81 2.22v3.29c0 .32.22.7.83.58A12 12 0 0 0 12 .5z"/>'  # noqa: E501


def _mask(path: str) -> str:
    """El icono como imagen de máscara CSS: st.html descarta las etiquetas <svg> en línea."""
    path = path.replace('"', "'")
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>{path}</svg>"
    return "url(\"data:image/svg+xml," + svg.replace("<", "%3C").replace(">", "%3E") + "\")"


def toolbar(page_paths: list[str]) -> None:
    """Dos iconos en la barra lateral: cambiar entre tema claro y oscuro, y el repositorio.

    Streamlit no tiene una API para cambiar el tema desde el código. Guarda la elección de cada
    visitante en el localStorage del navegador (la misma clave que usa su menú Settings), una
    por ruta. El botón escribe esa clave para todas las páginas y recarga: el cambio es solo
    para quien hace clic, no para el resto de visitantes.
    """
    paths = sorted({"/"} | {f"/{path}" for path in page_paths if path})
    st.html(
        f"""
        <style>
          .lr-toolbar {{ display: flex; gap: .25rem; margin-bottom: .25rem; }}
          .lr-toolbar a, .lr-toolbar button {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 2.25rem; height: 2.25rem; padding: 0; border: 0; border-radius: .5rem;
            background: transparent; color: inherit; cursor: pointer; opacity: .7; }}
          .lr-toolbar a:hover, .lr-toolbar button:hover {{
            opacity: 1; background: rgba(128, 128, 128, .18); }}
          .lr-toolbar span {{
            width: 1.25rem; height: 1.25rem; background: currentColor;
            -webkit-mask: var(--icon) center / contain no-repeat;
            mask: var(--icon) center / contain no-repeat; }}
          #lr-theme span {{ --icon: {_mask(MOON)}; }}
          #lr-theme[data-dark="1"] span {{ --icon: {_mask(SUN)}; }}
          #lr-github span {{ --icon: {_mask(GITHUB)}; }}
        </style>
        <div class="lr-toolbar">
          <button id="lr-theme" type="button" title="Cambiar entre tema claro y oscuro"
                  aria-label="Cambiar entre tema claro y oscuro"><span></span></button>
          <a id="lr-github" href="{REPO_URL}" target="_blank" rel="noopener"
             title="Código en GitHub" aria-label="Código en GitHub"><span></span></a>
        </div>
        <script>
          (() => {{
            const button = document.getElementById("lr-theme");
            // El tema activo se deduce del fondo real de la app: oscuro si su luminancia es baja.
            const [r, g, b] = getComputedStyle(document.querySelector(".stApp"))
              .backgroundColor.match(/\\d+/g).map(Number);
            const dark = 0.299 * r + 0.587 * g + 0.114 * b < 128;
            button.dataset.dark = dark ? "1" : "0";
            button.onclick = () => {{
              const value = JSON.stringify(dark ? "Light" : "Dark");
              for (const path of {paths!r}) {{
                window.localStorage.setItem(`stActiveTheme-${{path}}-v2`, value);
              }}
              window.location.reload();
            }};
          }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


st.set_page_config(page_title="Lima Rent MLOps", page_icon=":material/apartment:", layout="wide")

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
    toolbar([page.url_path for page in pages])
    st.markdown("## Lima Rent MLOps")
    st.caption("Alquiler de departamentos en Lima Metropolitana, con el modelo vigilado "
               "semana a semana.")

st.navigation(pages).run()

with st.sidebar:
    st.divider()
    st.caption("Proyecto educativo de MLOps · datos de avisos públicos, BCRP e INEI. "
               "No es una tasación.")
