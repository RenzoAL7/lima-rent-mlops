"""Scraper de avisos de alquiler de departamentos en Lima publicados en Infocasas.

Reglas (ver docs/datos.md):
- Solo rutas permitidas por robots.txt; se comprueba antes de empezar.
- Una página cada SCRAPE_DELAY_SECONDS segundos, con User-Agent que identifica el proyecto.
- Se guardan solo campos numéricos y de ubicación. Nunca títulos, descripciones, fotos ni datos
  del anunciante (nombre, teléfono): no se republica contenido del portal.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from urllib.robotparser import RobotFileParser

import httpx
import pandas as pd

from ..config import Settings

log = logging.getLogger(__name__)
SITE = "https://www.infocasas.com.pe"
LIST_PATH = "/alquiler/departamentos/lima"
CURRENCIES = {"S/": "PEN", "U$S": "USD", "US$": "USD"}


def page_url(page: int) -> str:
    return f"{SITE}{LIST_PATH}" if page == 1 else f"{SITE}{LIST_PATH}/pagina{page}"


def check_robots(user_agent: str, client: httpx.Client) -> None:
    parser = RobotFileParser()
    parser.parse(client.get(f"{SITE}/robots.txt").text.splitlines())
    for url in (page_url(1), page_url(2)):
        if not parser.can_fetch(user_agent, url):
            raise PermissionError(f"robots.txt no permite {url}")


def _next_data(html: str) -> dict:
    from selectolax.lexbor import LexborHTMLParser

    node = LexborHTMLParser(html).css_first("script#__NEXT_DATA__")
    if node is None:
        raise ValueError("La página no trae __NEXT_DATA__ (¿cambió el sitio?)")
    return json.loads(node.text())


def parse_page(html: str) -> tuple[list[dict], dict]:
    """Devuelve (avisos aplanados, info de paginación) de una página de resultados."""
    search = _next_data(html)["props"]["pageProps"]["fetchResult"]["searchFast"]
    return [flatten(item) for item in search.get("data", [])], search.get("paginatorInfo", {})


def _sheet(item: dict) -> dict[str, str]:
    return {f.get("field"): (f.get("value") or "") for f in item.get("technicalSheet") or []}


def _number(text) -> float | None:
    if text is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", str(text).replace(",", ""))
    return float(match.group()) if match else None


def _money(text: str) -> tuple[float | None, str | None]:
    """'S/ 150' -> (150.0, 'PEN'); 'U$S 1.200' -> (1200.0, 'USD')."""
    if not text:
        return None, None
    currency = next((code for sign, code in CURRENCIES.items() if sign in text), None)
    if currency is None and "$" in text:
        currency = "USD"
    digits = re.sub(r"[^\d]", "", text)
    return (float(digits) if digits else None), currency


def flatten(item: dict) -> dict:
    sheet = _sheet(item)
    price = item.get("price") or {}
    locations = item.get("locations") or {}
    neighbourhood = [n.get("name") for n in locations.get("neighbourhood") or []]
    facilities = {f.get("name") for f in item.get("facilities") or []}
    maintenance, maintenance_currency = _money(sheet.get("commonExpenses", ""))
    garage = _number(sheet.get("garage"))
    if garage is None:
        garage = 1.0 if facilities & {"Garaje", "Cochera"} else 0.0
    return {
        "id": str(item.get("id")),
        "fecha_publicacion": item.get("created_at"),
        "fecha_actualizacion": item.get("updated_at"),
        "operacion": (item.get("operation_type") or {}).get("name"),
        "tipo": (item.get("property_type") or {}).get("name"),
        "distrito_portal": neighbourhood[0] if neighbourhood else None,
        "latitud": item.get("latitude"),
        "longitud": item.get("longitude"),
        "precio": price.get("amount"),
        "moneda": CURRENCIES.get(((price.get("currency") or {}).get("name") or "").strip()),
        "precio_oculto": bool(price.get("hidePrice")),
        "mantenimiento": maintenance,
        "moneda_mantenimiento": maintenance_currency,
        "area_m2": item.get("m2Built") or item.get("m2"),
        "dormitorios": _number(sheet.get("bedrooms")),
        "banos": _number(sheet.get("bathrooms")),
        "cocheras": garage,
        "piso": _number(sheet.get("floor")),
        "amoblado": "Amueblada" in facilities,
        "estado": sheet.get("construction_state_name") or None,
    }


def scrape(settings: Settings, max_pages: int | None = None) -> pd.DataFrame:
    """Recorre las páginas de resultados y devuelve un DataFrame con un aviso por fila."""
    max_pages = max_pages or settings.scrape_max_pages
    headers = {"User-Agent": settings.user_agent, "Accept-Language": "es-PE,es;q=0.9"}
    rows: list[dict] = []
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as client:
        check_robots(settings.user_agent, client)
        page, last_page = 1, 1
        while page <= min(last_page, max_pages):
            html = _get_with_retries(client, page_url(page))
            listings, paginator = parse_page(html)
            rows += listings
            last_page = int(paginator.get("lastPage") or page)
            log.info("Infocasas página %d/%d: %d avisos", page, last_page, len(listings))
            if not paginator.get("hasMorePages"):
                break
            page += 1
            time.sleep(settings.scrape_delay_seconds)
    df = pd.DataFrame(rows).drop_duplicates(subset="id", keep="first")
    df["fecha_scraping"] = fetched_at
    return df


def _get_with_retries(client: httpx.Client, url: str, attempts: int = 4) -> str:
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url)
            if response.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("reintentable", request=response.request,
                                            response=response)
            response.raise_for_status()
            return response.text
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            if attempt == attempts:
                raise
            wait = 15 * attempt
            log.warning("Fallo %s (%s); reintento en %ds", url, error, wait)
            time.sleep(wait)
    raise RuntimeError("inalcanzable")
