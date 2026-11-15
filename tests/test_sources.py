import json
from datetime import date

import pandas as pd

from lima_rent_mlops.districts import normalize
from lima_rent_mlops.sources import bcrp, enaho, infocasas

ITEM = {
    "id": 123,
    "created_at": "2026-05-28",
    "updated_at": "2026-10-20",
    "title": "No se guarda",
    "description": "No se guarda",
    "owner": {"name": "Persona", "whatsapp_phone": "+51999999999"},
    "operation_type": {"id": 2, "name": "Alquiler"},
    "property_type": {"id": 2, "name": "Departamento"},
    "price": {"amount": 2600, "hidePrice": False, "currency": {"name": "S/"}},
    "m2": 88,
    "m2Built": 88,
    "latitude": -12.08,
    "longitude": -77.07,
    "locations": {"neighbourhood": [{"name": "Santiago De Surco"}]},
    "facilities": [{"name": "Garaje"}, {"name": "Amueblada"}],
    "technicalSheet": [
        {"field": "bathrooms", "value": "2"},
        {"field": "bedrooms", "value": "3"},
        {"field": "garage", "value": "1"},
        {"field": "floor", "value": "4"},
        {"field": "commonExpenses", "value": "S/ 150"},
    ],
}


def test_flatten_keeps_numbers_and_drops_personal_data():
    row = infocasas.flatten(ITEM)
    assert row["precio"] == 2600 and row["moneda"] == "PEN"
    assert (row["dormitorios"], row["banos"], row["cocheras"], row["piso"]) == (3, 2, 1, 4)
    assert row["mantenimiento"] == 150 and row["amoblado"] is True
    assert normalize(row["distrito_portal"]) == "Santiago de Surco"
    text = json.dumps(row)
    assert "Persona" not in text and "999999" not in text and "No se guarda" not in text


def test_parse_page_reads_next_data():
    payload = {"props": {"pageProps": {"fetchResult": {"searchFast": {
        "data": [ITEM], "paginatorInfo": {"lastPage": 3, "hasMorePages": True}}}}}}
    script = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    html = f"<html>{script}"
    rows, paginator = infocasas.parse_page(html)
    assert len(rows) == 1 and paginator["lastPage"] == 3
    assert infocasas.page_url(1).endswith("/lima") and infocasas.page_url(4).endswith("/pagina4")


def test_district_aliases():
    assert normalize("Jesus Maria") == "Jesús María"
    assert normalize("Ate Vitarte") == "Ate"
    assert normalize("Magdalena Del Mar") == "Magdalena del Mar"
    assert normalize("Arequipa") is None


def test_bcrp_period_parsers():
    assert str(bcrp.parse_quarter("T4.07")) == "2007Q4"
    assert bcrp.parse_day("12.Nov.26") == date(2026, 11, 12)
    assert bcrp.parse_day("03.Set.25") == date(2025, 9, 3)


def test_enaho_extracts_only_lima_renters():
    raw = pd.DataFrame({
        "AÑO": ["2024"] * 4, "MES": ["01", "02", "03", "04"],
        "UBIGEO": ["150122", "150122", "040101", "70101"],
        "P101": ["2", "1", "2", "2"], "P104": ["3", "2", "2", "4"],
        "P105A": ["1", "2", "1", "1"], "P105B": ["1500", "", "800", "99999"],
        "FACTOR07": ["100", "100", "100", "100"],
    })
    out = enaho.extract_rentals(raw, 2024)
    assert out["distrito"].tolist() == ["Miraflores"]
    assert out["tipo_vivienda"].iloc[0] == "departamento"
